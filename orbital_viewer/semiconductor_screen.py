"""Conservative voltage-headroom arithmetic, not a power-device qualification tool.

Catalog voltage classes only provide a necessary screen. Device-specific switching,
surge, temperature, lifetime and protection envelopes require separate evidence.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys


def number(value, name, *, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number, not a boolean")
    if value < 0 or (positive and value == 0):
        raise ValueError(f"{name} must be {'positive' if positive else 'nonnegative'}")
    return value


def references(value):
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ValueError("Evidence IDs must be a list of nonempty strings")
    return value


def voltage_headroom(stress, rating, max_rating_fraction):
    """Compare a sourced worst-case peak interval with a catalog voltage class.

    A pass covers this arithmetic only. Source IDs and conditions are declarations,
    not authenticated evidence. No universal derating fraction is supplied.
    """
    if not isinstance(rating, dict) or rating.get("unit") != "V" or rating.get("kind") != "catalog_voltage_class":
        raise ValueError("Rating must be a catalog_voltage_class in V")
    ceiling = number(rating.get("value"), "rating", positive=True)
    rating_refs = references(rating.get("source_ids"))
    if rating.get("classification") != "External knowledge":
        raise ValueError("Catalog rating must identify external evidence")
    if max_rating_fraction is not None:
        number(max_rating_fraction, "max_rating_fraction", positive=True)
        if max_rating_fraction >= 1:
            raise ValueError("A screening fraction must be strictly below 1")
    result = {"status": "unknown", "classification": "Derived", "headroom_interval_v": None,
              "scope": "catalog voltage headroom only; not an operating envelope"}
    if stress is None:
        return {**result, "reason": "Worst-case drain stress and voltage interpretation are unresolved"}
    if not isinstance(stress, dict) or stress.get("unit") != "V" or stress.get("kind") != "worst_case_drain_peak":
        raise ValueError("Stress must be worst_case_drain_peak in V, not nominal bus or band gap")
    peak = number(stress.get("value"), "stress", positive=True)
    uncertainty = stress.get("uncertainty_v")
    if uncertainty is not None:
        number(uncertainty, "uncertainty_v")
        if uncertainty > peak:
            raise ValueError("Stress interval must be nonnegative")
    refs = references(stress.get("evidence_ids"))
    if stress.get("classification") not in {"Observed", "Derived", "External knowledge", "Assumed"}:
        raise ValueError("Stress needs an evidence classification")
    conditions = stress.get("conditions")
    if conditions is not None and (not isinstance(conditions, str) or not conditions.strip()):
        raise ValueError("Conditions must be null or nonempty text")
    if (uncertainty is None or not refs or not rating_refs or not conditions
            or stress["classification"] == "Assumed"):
        return {**result, "reason": "Missing uncertainty, conditions or non-assumed provenance"}
    low, high = peak - uncertainty, peak + uncertainty
    if not math.isfinite(high):
        raise ValueError("Stress interval overflow")
    if low >= ceiling:
        return {**result, "status": "fail", "reason": "No positive headroom below the catalog class"}
    if max_rating_fraction is None:
        return {**result, "reason": "No explicit engineering derating policy"}
    limit = ceiling * max_rating_fraction
    interval = [limit - high, limit - low]
    status = "pass" if interval[0] >= 0 else "fail" if interval[1] < 0 else "unknown"
    return {**result, "status": status, "headroom_interval_v": interval,
            "formula": "rating * max_rating_fraction - (peak +/- uncertainty)",
            "evidence_ids": sorted(set(refs + rating_refs)),
            "reason": "Necessary arithmetic screen; switching/surge conditions and all other gates remain separate"}


def assess(design):
    if (not isinstance(design, dict) or design.get("schema_version") != "1"
            or design.get("benchmark_id") != "SEMI-01" or design.get("evidence_scope") != "engineering_screen"):
        raise ValueError("Expected SEMI-01 engineering_screen version 1")
    if design.get("release_allowed") is not False:
        raise ValueError("SEMI-01 must preserve release_allowed=false")
    interpretation = design["voltage_requirement"]["interpretation"]
    if interpretation not in {"unspecified", "device_class", "dc_bus"}:
        raise ValueError("Unknown voltage interpretation")
    candidates = design["candidates"]
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("At least one commercial comparator is required")
    ids = [item["id"] for item in candidates]
    if any(not isinstance(x, str) or not x.strip() for x in ids) or len(ids) != len(set(ids)):
        raise ValueError("Candidate IDs must be unique nonempty strings")
    results = []
    for candidate in candidates:
        gate = voltage_headroom(design["worst_case_drain_peak"], candidate["voltage_class"],
                                design["max_rating_fraction"])
        if interpretation == "unspecified":
            gate = {**gate, "status": "unknown", "headroom_interval_v": None,
                    "reason": "Resolve whether 650 V means DC bus or device voltage class first"}
        results.append({"id": candidate["id"], "catalog_voltage_headroom": gate,
                        "device_operating_envelope": "unknown", "loss_and_thermal": "unknown",
                        "protection_and_layout": "unknown", "procurement": "unknown",
                        "qualification": "unknown"})
    return {"schema_version": "1", "benchmark_id": "SEMI-01", "evidence_scope": "engineering_screen",
            "candidate_results": results, "engineering_decision": {
                "status": "blocked_pending_operating_point_and_device_validation",
                "provisional_technology": "SiC", "recommendation_classification": "Assumed",
                "recommendation_condition": "Hard-switched robotic motor-drive development baseline only",
                "selected_technology": None, "selected_part_number": None,
                "approved_bus_voltage_v": None, "approved_current_a": None,
                "approved_switching_frequency_hz": None, "predicted_loss_w": None,
                "predicted_junction_temperature_c": None, "release_allowed": False,
                "quantum_calculations_performed": False}}


def run(design_path, output):
    content = design_path.read_bytes()
    result = assess(json.loads(content))
    result.update(design_sha256=hashlib.sha256(content).hexdigest(),
                  implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  generated_at_utc=datetime.now(timezone.utc).isoformat())
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.design, args.output)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"Semiconductor screening input/output error: {exc}\n")
    print(json.dumps(result["engineering_decision"], indent=2))


if __name__ == "__main__":
    main()
