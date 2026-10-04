"""Reference-aware thermodynamic screening; never a battery release mechanism.

This module consumes explicitly sourced potentials; it does not compute molecular
energies, infer a voltage from a CUBE file, or qualify an electrolyte formulation.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

CLASSIFICATIONS = {"Observed", "Derived", "External knowledge", "Assumed"}


def finite_number(value, name, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number, not a boolean")
    if nonnegative and value < 0:
        raise ValueError(f"{name} must be nonnegative")
    return float(value)


def validate_potential(value):
    """Allow missing metadata but never treat it as a comparable potential."""
    if value is None:
        return
    if not isinstance(value, dict) or value.get("unit") != "V":
        raise ValueError("Potential must be an object with unit V")
    finite_number(value.get("value"), "potential")
    if value.get("classification") not in CLASSIFICATIONS:
        raise ValueError("Potential needs an evidence classification")
    if value.get("kind") not in {"operating_potential", "thermodynamic_redox"}:
        raise ValueError("Potential kind must distinguish operation from thermodynamic redox")
    for key in ("reference", "conditions_id"):
        if value.get(key) is not None and (not isinstance(value[key], str) or not value[key].strip()):
            raise ValueError(f"{key} must be null or a nonempty identifier")
    if value.get("uncertainty_v") is not None:
        finite_number(value["uncertainty_v"], "uncertainty_v", nonnegative=True)
    evidence = value.get("evidence_ids")
    if not isinstance(evidence, list) or any(not isinstance(x, str) or not x.strip() for x in evidence):
        raise ValueError("evidence_ids must be a list of nonempty identifiers")


def margin_gate(high, low, required_margin_v):
    """Test high - low >= margin using conservative uncertainty bounds.

Oxidation: high=solvent M+/M potential, low=cathode potential.
Reduction: high=anode potential, low=solvent M/M- potential.
An intrinsic reduction failure is NOT a passivation/SEI failure.
"""
    validate_potential(high)
    validate_potential(low)
    if required_margin_v is not None:
        finite_number(required_margin_v, "required_margin_v", nonnegative=True)
    result = {"status": "unknown", "classification": "Derived", "clearance_interval_v": None}
    if high is None or low is None or required_margin_v is None:
        return {**result, "reason": "Missing potential or engineering margin"}
    for item in (high, low):
        if (item.get("reference") is None or item.get("conditions_id") is None
                or item.get("uncertainty_v") is None or not item["evidence_ids"]
                or item["classification"] == "Assumed"):
            return {**result, "reason": "Missing reference, conditions, uncertainty, or non-assumed evidence"}
    if high["reference"] != low["reference"] or high["conditions_id"] != low["conditions_id"]:
        return {**result, "reason": "Different references or conditions require an explicit validated conversion"}
    center = high["value"] - low["value"] - required_margin_v
    radius = high["uncertainty_v"] + low["uncertainty_v"]
    lower, upper = center - radius, center + radius
    if not all(math.isfinite(x) for x in (center, radius, lower, upper)):
        raise ValueError("Potential interval arithmetic overflow")
    status = "pass" if lower >= 0 else "fail" if upper < 0 else "unknown"
    return {**result, "status": status, "clearance_interval_v": [lower, upper],
            "reason": "Intrinsic thermodynamic comparison only; not decomposition onset or formulation qualification",
            "formula": "high - low - margin +/- (uncertainty_high + uncertainty_low)",
            "evidence_ids": sorted(set(high["evidence_ids"] + low["evidence_ids"]))}


def assess(design):
    if not isinstance(design, dict) or design.get("schema_version") != "1":
        raise ValueError("Expected design schema_version 1")
    if design.get("evidence_scope") != "screening_plan":
        raise ValueError("Expected screening_plan, not a fixture or released specification")
    if design.get("release_allowed") is not False:
        raise ValueError("Screening plans must explicitly set release_allowed=false")
    target = design["target"]
    for key in ("cathode_potential", "anode_potential"):
        validate_potential(target[key])
        if target[key] is not None and target[key]["kind"] != "operating_potential":
            raise ValueError("Electrode targets must be operating potentials")
    candidates = design["candidates"]
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("At least one explicitly proposed candidate is required")
    identifiers = [c["id"] for c in candidates]
    if (any(not isinstance(x, str) or not x.strip() for x in identifiers)
            or len(set(identifiers)) != len(identifiers)):
        raise ValueError("Candidate identifiers must be unique nonempty strings")
    results = []
    for candidate in candidates:
        for key in ("oxidation_potential", "reduction_potential"):
            validate_potential(candidate[key])
            if candidate[key] is not None and candidate[key]["kind"] != "thermodynamic_redox":
                raise ValueError("Do not substitute orbital energies or measured onsets for thermodynamic redox potentials")
        results.append({"id": candidate["id"],
            "intrinsic_oxidation": margin_gate(candidate["oxidation_potential"], target["cathode_potential"], target["required_margin_v"]),
            "intrinsic_reduction": margin_gate(target["anode_potential"], candidate["reduction_potential"], target["required_margin_v"]),
            "formulation_qualification": "unknown"})
    return {"schema_version": "1", "benchmark_id": design["benchmark_id"],
            "evidence_scope": "screening_plan", "candidate_results": results,
            "engineering_decision": {"status": "blocked_pending_formulation_and_cell_validation",
                "release_allowed": False, "selected_electrolyte": None,
                "approved_terminal_charge_voltage_v": None,
                "reason": "Thermodynamic screening cannot establish SEI/CEI, transport, lifetime, or safety"}}


def run(design_path, output):
    content = design_path.read_bytes()
    result = assess(json.loads(content))
    result["design_sha256"] = hashlib.sha256(content).hexdigest()
    result["implementation_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result["engineering_decision"], indent=2))
    return 0  # Successful evidence processing is distinct from a blocked engineering decision.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        return run(args.design, args.output)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"Electrolyte screening input/output error: {exc}\n")


if __name__ == "__main__":
    sys.exit(main())
