"""SENSOR-01 arithmetic and evidence boundaries; no physical measurements."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from orbital_viewer.benchmark import empty_record, validate_plan
from orbital_viewer.sensor_design import derive_preview, photon_energy_ev

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "benchmarks/SENSOR-01/design.json"
PLAN = ROOT / "benchmarks/SENSOR-01/plan.json"


def design():
    return json.loads(DESIGN.read_text(encoding="utf-8"))


def plan():
    return json.loads(PLAN.read_text(encoding="utf-8"))


def test_photon_energy_is_not_a_material_transition():
    assert photon_energy_ev(300) == pytest.approx(4.13280661444, rel=1e-10)
    assert photon_energy_ev(600) == pytest.approx(photon_energy_ev(300) / 2)


@pytest.mark.parametrize("value", [0, -300, float("nan"), float("inf"), True, "300", None])
def test_invalid_wavelength_rejected(value):
    with pytest.raises(ValueError):
        photon_energy_ev(value)


def test_headroom_and_code_size_are_conditional_not_detection_limits():
    result = derive_preview(design())
    assert result["classification"] == "Derived"
    assert result["adc_voltage_per_code_v"] == pytest.approx(62.5e-6)
    assert result["usable_positive_excursion_v"] == pytest.approx(2.0)
    low, high = result["gain_options"]
    assert low["ideal_headroom_current_a"] == pytest.approx(2e-6)
    assert high["ideal_headroom_current_a"] == pytest.approx(200e-9)
    assert high["ideal_current_per_code_a"] == pytest.approx(6.25e-12)
    assert high["feedback_rc_pole_hz"] == pytest.approx(15.9154943092)
    decision = result["engineering_decision"]
    assert decision["release_allowed"] is False
    assert decision["quantum_results_generated"] is False
    assert decision["calibrated_irradiance_range_w_m2"] is None
    assert decision["measured_responsivity_at_300_a_w"] is None
    assert decision["measured_detection_limit_w_m2"] is None


def test_adc_limit_not_just_supply_limit():
    value = design()
    value["inputs"]["rail"]["value"] = 5.0
    value["inputs"]["output_ceiling"]["value"] = 4.5
    result = derive_preview(value)
    assert result["usable_positive_excursion_v"] == pytest.approx(2.048 - 62.5e-6)


@pytest.mark.parametrize("name,value", [("rail", 2.5), ("bias", 3.1), ("output_ceiling", 3.3),
                                         ("adc_bits", 12), ("adc_positive_full_scale", 4.096)])
def test_invalid_or_unmodelled_configuration_rejected(name, value):
    data = design()
    data["inputs"][name]["value"] = value
    with pytest.raises(ValueError):
        derive_preview(data)


@pytest.mark.parametrize("change", ["unit", "source", "conditions", "classification", "rationale", "gain"])
def test_units_and_provenance_cannot_disappear(change):
    data = design()
    if change == "unit": data["inputs"]["rail"]["unit"] = "mV"
    if change == "source": data["inputs"]["adc_bits"]["source_id"] = "missing"
    if change == "conditions": data["inputs"]["adc_bits"].pop("conditions")
    if change == "classification": data["inputs"]["rail"]["classification"] = "Observed"
    if change == "rationale": data["inputs"]["rail"].pop("rationale")
    if change == "gain": data["gain_options"][0]["feedback_ohm"] = 0
    with pytest.raises(ValueError):
        derive_preview(data)


def test_peak_and_fixture_data_never_fill_missing_calibration():
    data = design()
    data["manufacturer_evidence"]["detector_peak_responsivity"]["value"] = 999
    data["quantum_results"] = {"synthetic_fixture": [4.133, 10]}
    assert derive_preview(data)["engineering_decision"]["measured_responsivity_at_300_a_w"] is None
    assert all(value is None for value in design()["unknowns"].values())
    assert design()["proposed_ir"]["validation"]["production_release_allowed"] is False


def test_sensor_plan_reuses_all_tools_without_a_cure_decision():
    value = validate_plan(plan())
    decision = empty_record(value)["engineering_decision"]
    assert len(value["calls"]) == 7
    assert len({call["name"] for call in value["calls"]}) == 5
    assert decision["release_allowed"] is False
    assert "required_dose_j_cm2" not in decision
    assert all(decision[key] is None for key in value["unknown_quantities"])
    assert "SYNTHETIC" in empty_record(value)["warning"]


def test_legacy_process_plan_remains_compatible():
    value = plan()
    value.pop("unknown_quantities")
    value["benchmark_id"] = "PROCESS-01"
    decision = empty_record(validate_plan(value))["engineering_decision"]
    assert decision["required_dose_j_cm2"] is None
    assert decision["selected_wavelength_nm"] is None
    assert decision["release_allowed"] is False


@pytest.mark.parametrize("names", [[], "value", ["release_allowed"], ["status"], ["reason"],
                                    ["a", "a"], [None], [""], ["a/b"], ["_a"], {"r": 0.1}])
def test_unknown_quantities_cannot_override_release_or_supply_values(names):
    value = plan()
    value["unknown_quantities"] = names
    with pytest.raises(ValueError):
        validate_plan(value)
    with pytest.raises(ValueError):
        empty_record(value)


def test_preview_cli_records_hash_and_refuses_stale_output(tmp_path):
    output = tmp_path / "sizing.json"
    args = [sys.executable, "-m", "orbital_viewer.sensor_design", "--design", str(DESIGN), "--output", str(output)]
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    record = json.loads(output.read_text())
    assert record["input_sha256"] == hashlib.sha256(DESIGN.read_bytes()).hexdigest()
    assert record["engineering_decision"]["release_allowed"] is False
    before = output.read_bytes()
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=15)
    assert result.returncode == 2
    assert output.read_bytes() == before


def test_sensor_real_mcp_record_keeps_detector_unknowns(tmp_path):
    pytest.importorskip("mcp")
    output = tmp_path / "evidence"
    result = subprocess.run([sys.executable, "-m", "orbital_viewer.benchmark", "--plan", str(PLAN),
        "--data-dir", str(ROOT / "examples/mcp"), "--output", str(output)],
        cwd=ROOT, capture_output=True, text=True, timeout=150)
    assert result.returncode == 0, result.stdout + result.stderr
    record = json.loads((output / "run.json").read_text())
    assert record["benchmark_id"] == "SENSOR-01"
    assert record["tool_execution_status"] == "passed"
    assert len(record["calls"]) == 7
    assert all(c["status"] == "succeeded" for c in record["calls"])
    assert len(record["generated_artifacts"]) == 3
    for item in record["generated_artifacts"]:
        assert hashlib.sha256((output / item["path"]).read_bytes()).hexdigest() == item["sha256"]
    decision = record["engineering_decision"]
    assert decision["release_allowed"] is False
    assert all(decision[key] is None for key in plan()["unknown_quantities"])
