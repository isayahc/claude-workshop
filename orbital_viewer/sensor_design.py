"""Reproducible, uncalibrated electrical sizing for SENSOR-01; not a solver.

Manufacturer properties retain their source/conditions in design.json. This
module never substitutes peak responsivity for responsivity at the target.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

# Exact SI definitions; NIST source N1 in the benchmark design record.
H_J_S = 6.62607015e-34
C_M_S = 299792458.0
E_C = 1.602176634e-19


def positive(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric, not a boolean or string")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be finite and positive")
    return float(value)


def photon_energy_ev(wavelength_nm: float) -> float:
    return H_J_S * C_M_S / (positive(wavelength_nm, "wavelength_nm") * 1e-9 * E_C)


def quantity(design: dict, name: str, unit: str) -> float:
    item = design["inputs"][name]
    if item.get("unit") != unit:
        raise ValueError(f"{name}: expected unit {unit}")
    classification = item.get("classification")
    if classification not in {"External knowledge", "Assumed"}:
        raise ValueError(f"{name}: sizing input must preserve its external/assumed origin")
    if classification == "External knowledge":
        if item.get("source_id") not in design["sources"] or not item.get("conditions"):
            raise ValueError(f"{name}: source and conditions are required")
    elif not item.get("rationale"):
        raise ValueError(f"{name}: assumption needs a rationale")
    return positive(item.get("value"), name)


def derive_preview(design: dict) -> dict:
    """Calculate design arithmetic; do not invent calibration, noise or spectra."""
    if design.get("schema_version") != "1" or design.get("benchmark_id") != "SENSOR-01":
        raise ValueError("Expected SENSOR-01 design schema_version 1")
    wavelength = quantity(design, "target_wavelength", "nm")
    rail = quantity(design, "rail", "V")
    bias = quantity(design, "bias", "V")
    ceiling = quantity(design, "output_ceiling", "V")
    full_scale = quantity(design, "adc_positive_full_scale", "V")
    bits = quantity(design, "adc_bits", "bit")
    if bits != 16 or full_scale != 2.048:
        raise ValueError("This preview models ADS1115 at +/-2.048 V, 16 bits only")
    if not 0 < bias < ceiling < rail:
        raise ValueError("Require 0 < bias < output_ceiling < rail")
    lsb = 2 * full_scale / (2 ** int(bits))
    excursion = min(ceiling - bias, full_scale - lsb)
    choices = design.get("gain_options")
    if not isinstance(choices, list) or not choices:
        raise ValueError("At least one gain option is required")
    gains = []
    for choice in choices:
        if choice.get("classification") != "Assumed" or not choice.get("rationale"):
            raise ValueError("Gain choices must be explicit design assumptions")
        resistance = positive(choice.get("feedback_ohm"), "feedback_ohm")
        capacitance = positive(choice.get("feedback_f"), "feedback_f")
        gains.append({
            "feedback_ohm": resistance,
            "feedback_f": capacitance,
            "ideal_headroom_current_a": excursion / resistance,
            "ideal_current_per_code_a": lsb / resistance,
            "feedback_rc_pole_hz": 1 / (2 * math.pi * resistance * capacitance),
        })
    return {
        "schema_version": "1", "benchmark_id": "SENSOR-01",
        "classification": "Derived", "evidence_scope": "uncalibrated_design_arithmetic",
        "dependencies": {"inputs": design["inputs"], "gain_options": choices,
                         "constants_source_id": "N1"},
        "photon_energy_ev": photon_energy_ev(wavelength),
        "adc_voltage_per_code_v": lsb,
        "usable_positive_excursion_v": excursion,
        "gain_options": gains,
        "formulas": {
            "photon_energy_ev": "h*c/(wavelength_nm*1e-9*e)",
            "adc_voltage_per_code_v": "2*positive_full_scale/2**bits",
            "usable_positive_excursion_v": "min(output_ceiling-bias, positive_full_scale-lsb)",
            "ideal_headroom_current_a": "usable_positive_excursion_v/feedback_ohm",
            "ideal_current_per_code_a": "adc_voltage_per_code_v/feedback_ohm",
            "feedback_rc_pole_hz": "1/(2*pi*feedback_ohm*feedback_f)",
        },
        "engineering_decision": {
            "status": "prototype_candidate_not_calibrated",
            "release_allowed": False,
            "measured_responsivity_at_300_a_w": None,
            "measured_filter_transmission_at_300": None,
            "calibrated_irradiance_range_w_m2": None,
            "measured_detection_limit_w_m2": None,
            "measured_accuracy_percent": None,
            "quantum_results_generated": False,
        },
        "caveats": [
            "Headroom is conditional design arithmetic, not a measured optical range.",
            "ADC code size is not a noise floor, detection limit or effective resolution.",
            "Feedback RC pole alone does not establish closed-loop stability or system bandwidth.",
            "Peak responsivity at 280 nm is not used as responsivity at 300 nm.",
            "No CUBE, material transition list, DFT result or calibration is generated.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="New JSON file; an existing evidence file is never overwritten")
    args = parser.parse_args()
    try:
        raw = args.design.read_bytes()
        result = derive_preview(json.loads(raw))
        result["input_sha256"] = hashlib.sha256(raw).hexdigest()
        result["implementation_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"Sizing error: {exc}\n")
    print("Wrote uncalibrated design arithmetic; release_allowed=false")


if __name__ == "__main__":
    main()
