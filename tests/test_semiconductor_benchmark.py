"""SEMI-01 regressions: catalog ratings cannot become module qualification."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

from orbital_viewer.benchmark import fingerprint
from orbital_viewer.semiconductor_screen import assess, run, voltage_headroom

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "benchmarks/SEMI-01"
spec = importlib.util.spec_from_file_location("semi01_reproduce", CASE / "reproduce.py")
reproduce = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reproduce)


def design():
    return json.loads((CASE / "design.json").read_text())


def stress(value=400, uncertainty=10):
    # Artificial regression input, never a measured SEMI-01 operating point.
    return {"value": value, "unit": "V", "kind": "worst_case_drain_peak",
            "uncertainty_v": uncertainty, "classification": "Observed",
            "evidence_ids": ["ARTIFICIAL-TEST"], "conditions": "Artificial unit-test interval"}


def rating():
    return design()["candidates"][0]["voltage_class"]


def test_supplied_case_preserves_unresolved_device_and_material_evidence():
    data = reproduce.audit_inputs()
    value = data["design.json"]
    assert value["voltage_requirement"]["interpretation"] == "unspecified"
    assert all(v is None for v in value["operating_point"].values())
    assert value["worst_case_drain_peak"] is value["max_rating_fraction"] is None
    assert all(c["scientific_artifacts"] == [] for c in value["candidates"])
    result = assess(value)
    assert all(c["catalog_voltage_headroom"]["status"] == "unknown" for c in result["candidate_results"])
    decision = result["engineering_decision"]
    assert decision["provisional_technology"] == "SiC"
    assert decision["recommendation_classification"] == "Assumed"
    assert decision["selected_technology"] is decision["selected_part_number"] is None
    assert decision["predicted_loss_w"] is decision["predicted_junction_temperature_c"] is None
    assert decision["release_allowed"] is decision["quantum_calculations_performed"] is False


@pytest.mark.parametrize("peak,uncertainty,expected", [(400, 10, "pass"), (600, 10, "fail"), (520, 10, "unknown")])
def test_interval_headroom_does_not_hide_uncertainty(peak, uncertainty, expected):
    result = voltage_headroom(stress(peak, uncertainty), rating(), 0.8)
    assert result["status"] == expected
    assert result["headroom_interval_v"] == [520 - peak - uncertainty, 520 - peak + uncertainty]


@pytest.mark.parametrize("peak", [650, 700])
def test_650_v_device_has_no_headroom_at_650_v_bus_even_without_margin(peak):
    assert voltage_headroom(stress(peak, 0), rating(), None)["status"] == "fail"


@pytest.mark.parametrize("field,value", [("uncertainty_v", None), ("evidence_ids", []),
                                        ("conditions", None), ("classification", "Assumed")])
def test_unproven_stress_cannot_pass(field, value):
    item = stress()
    item[field] = value
    assert voltage_headroom(item, rating(), 0.8)["status"] == "unknown"


def test_missing_stress_margin_or_rating_source_is_unknown():
    assert voltage_headroom(None, rating(), 0.8)["status"] == "unknown"
    assert voltage_headroom(stress(), rating(), None)["status"] == "unknown"
    item = rating()
    item["source_ids"] = []
    assert voltage_headroom(stress(), item, 0.8)["status"] == "unknown"


@pytest.mark.parametrize("field,value", [("value", True), ("value", float("nan")),
    ("value", float("inf")), ("value", -1), ("uncertainty_v", -1), ("uncertainty_v", 401),
    ("kind", "nominal_bus"), ("unit", "eV"), ("evidence_ids", "S1"), ("conditions", "")])
def test_invalid_quantities_and_provenance_are_rejected(field, value):
    item = stress()
    item[field] = value
    with pytest.raises(ValueError):
        voltage_headroom(item, rating(), 0.8)


@pytest.mark.parametrize("fraction", [True, 0, -0.1, 1, 1.1, float("nan")])
def test_derating_must_be_explicit_finite_and_below_rating(fraction):
    with pytest.raises(ValueError):
        voltage_headroom(stress(), rating(), fraction)


def test_overflow_is_rejected():
    with pytest.raises(ValueError, match="overflow"):
        voltage_headroom(stress(1e308, 1e308), rating(), 0.8)


def test_voltage_pass_cannot_release_a_device_or_fill_losses():
    value = design()
    value["voltage_requirement"]["interpretation"] = "device_class"
    value["worst_case_drain_peak"] = stress()
    value["max_rating_fraction"] = 0.8
    result = assess(value)
    for item in result["candidate_results"]:
        assert item["catalog_voltage_headroom"]["status"] == "pass"
        assert item["device_operating_envelope"] == item["loss_and_thermal"] == item["qualification"] == "unknown"
    assert result["engineering_decision"]["release_allowed"] is False
    assert result["engineering_decision"]["selected_part_number"] is None
    assert result["engineering_decision"]["predicted_loss_w"] is None
    value["voltage_requirement"]["interpretation"] = "unspecified"
    assert all(c["catalog_voltage_headroom"]["status"] == "unknown" for c in assess(value)["candidate_results"])


def test_schema_proposal_keeps_unknowns_out_of_numeric_defaults():
    data = reproduce.audit_inputs()
    proposal = data["hardware-ir.proposed.json"]
    assert proposal["components"] == proposal["bom"] == []
    assert "requirements" not in proposal  # Would default operating_voltage to 3.3.
    assert "estimated_cost" not in proposal["overview"]
    assert proposal["assembly_metadata"]["semi01"]["module_cost"] is None
    assert data["mapping_check"]["pydantic_model_validation_performed"] is False
    assert data["mapping_check"]["caid_import_performed"] is False
    for key in ["production_release", "approved_bus_voltage_v"]:
        bad = deepcopy(proposal)
        if key == "production_release":
            bad["assembly_metadata"][key] = True
        else:
            bad["assembly_metadata"]["semi01"][key] = 650
        with pytest.raises(ValueError):
            reproduce.validate_proposal(bad, data["design.json"], data["requirements.json"])


def test_input_release_claim_and_duplicate_candidate_are_rejected():
    value = design()
    value["release_allowed"] = True
    with pytest.raises(ValueError):
        assess(value)
    value = design()
    value["candidates"].append(deepcopy(value["candidates"][0]))
    with pytest.raises(ValueError):
        assess(value)


def test_assessment_cli_records_provenance_and_refuses_overwrite(tmp_path):
    output = tmp_path / "assessment.json"
    result = run(CASE / "design.json", output)
    assert result["design_sha256"] == fingerprint(CASE / "design.json")["sha256"]
    assert result["implementation_sha256"] == fingerprint(ROOT / "orbital_viewer/semiconductor_screen.py")["sha256"]
    with pytest.raises(FileExistsError):
        run(CASE / "design.json", output)


def test_actual_mcp_bundle_and_tamper_detection(tmp_path):
    pytest.importorskip("mcp")
    output = tmp_path / "SEMI-01"
    result = reproduce.reproduce(output)
    assert result["engineering_decision"]["release_allowed"] is False
    record = reproduce.read(output / "run.json")
    assert [c["name"] for c in record["calls"]] == ["inspect_cube", "export_orbital"]
    assert len(record["generated_artifacts"]) == 1
    manifest = reproduce.read(output / "evidence-manifest.json")
    provenance = reproduce.read(output / "schema-provenance.json")
    assert provenance["benchmark_id"] == "SEMI-01"
    assert provenance["pydantic_model_validation_performed"] is False
    assert provenance["reused_schema_origin_sha256"] == fingerprint(output / "schema-origin.MAT-01.json")["sha256"]
    for artifact in manifest["bundle_files"]:
        assert fingerprint(output / artifact["path"])["sha256"] == artifact["sha256"]
    assert set(record["engineering_decision"][k] for k in reproduce.read(CASE / "plan.json")["unknown_quantities"]) == {None}
    bad = deepcopy(record)
    bad["calls"][0]["response"]["structuredContent"]["value_max"] = 42
    reproduce.write(output / "run.json", bad)
    with pytest.raises(ValueError, match="responses differ"):
        reproduce.verify_smoke(output)
    reproduce.write(output / "run.json", record)
    (output / record["generated_artifacts"][0]["path"]).write_text("corrupt export")
    with pytest.raises(ValueError, match="integrity"):
        reproduce.verify_smoke(output)
    with pytest.raises(FileExistsError):
        reproduce.reproduce(output)
