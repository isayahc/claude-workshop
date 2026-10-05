"""MAT-01 evidence boundaries, actual MCP recording and pinned schema checks."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "benchmarks/MAT-01"
SPEC = importlib.util.spec_from_file_location("mat01_reproduce", BASE / "reproduce.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


@pytest.mark.parametrize("points,minimum", [(None, None), (None, .8), ([], .8), ([[315, .8]], None)])
def test_missing_data_never_passes(points, minimum):
    assert runner.optical_gate(points, minimum) == "unknown"


def test_whole_band_gate_needs_sampling_review_and_preserves_failure():
    assert runner.optical_gate([[315, .8]], .8, coverage_validated=True) == "unknown"
    assert runner.optical_gate([[270, .9], [410, .9]], .8, coverage_validated=True) == "unknown"
    assert runner.optical_gate([[280, .9], [400, .9]], .8) == "unknown"
    assert runner.optical_gate([[280, .5], [315, .99], [400, .99]], .8, coverage_validated=True) == "fail"
    assert runner.optical_gate([[315, .5]], .8) == "fail"
    assert runner.optical_gate([[280, .9], [315, .9], [400, .9]], .8, coverage_validated=True) == "pass"


@pytest.mark.parametrize("points,minimum", [([[280, float("nan")]], .8), ([[280, 1.1]], .8),
    ([[280, -.1]], .8), ([[280, .9]], 1.2), ([[280, .9]], float("inf")),
    ([[400, .9], [280, .9]], .8), ([[280, .9], [280, .8]], .8), ([[280, .9]], True)])
def test_invalid_optical_inputs_rejected(points, minimum):
    with pytest.raises(ValueError):
        runner.optical_gate(points, minimum)


def test_evidence_audit_preserves_unknowns_and_excludes_smoke():
    data = runner.audit_inputs()
    assert {c["family"] for c in data["candidates"]} == {"fused silica", "PMMA", "polycarbonate"}
    assert all(c["optical"]["full_band_transmission_fraction"] is None for c in data["candidates"])
    assert all(c["qualification"]["pointwise_T_280_400"] == "unknown" for c in data["candidates"])
    assert data["decision"]["production_release"] is False
    assert not data["decision"]["sensor_weighted_metric"]["evaluated"]
    assert len(data["requirements"]) == 16 and len(data["handoffs"]) == 5
    for gap in data["friction"]:
        assert all(gap[k] for k in ("stage", "gap_type", "expected", "observed", "evidence", "workaround", "impact", "reusable_capability_and_success_criterion"))
    evidence = {e["evidence_id"]: e for e in data["evidence"]}
    assert not evidence["O501"]["decision_use"] and not evidence["O502"]["decision_use"]
    assert evidence["E206"]["values"]["earlier_snippet_price_per_m2"] == 118.88


def test_derivations_use_source_values_without_inventing_a_spectrum():
    derived = runner.derived_values(runner.audit_inputs())
    assert derived["FS_ideal_nominal_disc_mass_g"] == pytest.approx(2.15984494934)
    assert derived["PMMA_ideal_proposed_disc_mass_g"] == pytest.approx(1.75241965278)
    assert derived["PC_nominal_thickness_mm"] == pytest.approx(2.9972)
    assert derived["full_band_or_sensor_weighted_transmission"] is None


@pytest.mark.parametrize("mutation", ["quantity", "instance", "part", "price", "duplicate", "missing_bom", "double_bom", "release", "is_valid", "schema_type"])
def test_bad_proposals_cannot_pass_ci_checks(mutation):
    m = deepcopy(runner.read_json(BASE / "material-entry.proposed.json")["proposed_mapping"])
    if mutation == "quantity": m["bom"][0]["quantity"] = 2
    elif mutation == "instance": m["bom"][0]["instance_refs"] = ["W2"]
    elif mutation == "part": m["components"][0]["part_definition_id"] = "absent"
    elif mutation == "price": m["bom"][0]["extended_price"] = 1
    elif mutation == "duplicate": m["components"].append(deepcopy(m["components"][0]))
    elif mutation == "missing_bom": m["bom"] = []
    elif mutation == "double_bom": m["bom"].append(deepcopy(m["bom"][0]))
    elif mutation == "release": m["assembly_metadata"]["production_release"] = True
    elif mutation == "is_valid": m["is_valid"] = True
    else: m["part_definitions"][0]["dimensions_mm"]["thickness"] = "unmeasured"
    with pytest.raises((ValueError, jsonschema.ValidationError)):
        runner.mapping_checks(m)


def test_actual_forma_model_check_is_bound_to_proposal_and_schema():
    result = runner.read_json(BASE / "forma-model-check.json")
    assert result["unmodified_model_validation"] == "passed"
    assert result["local_serialization_round_trip"] == "passed"
    assert len(result["negative_cases_rejected"]) == 3
    assert result["evidence_and_nulls_preserved"] and not result["caid_import_performed"]
    assert result["schema_sha256"] == runner.fingerprint(BASE / "hardware-ir.schema.json")["sha256"]
    assert result["proposal_input_sha256"] == runner.fingerprint(BASE / "material-entry.proposed.json")["sha256"]
    assert result["serialized_proposal_sha256"] == runner.fingerprint(BASE / "hardware-ir.proposed.json")["sha256"]


def test_actual_mcp_bundle_and_separate_outcomes(tmp_path):
    pytest.importorskip("mcp")
    output = tmp_path / "MAT-01"
    result = subprocess.run([sys.executable, str(BASE / "reproduce.py"), "--output", str(output)],
                            cwd=ROOT, capture_output=True, text=True, timeout=150)
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = runner.read_json(output / "manifest.json")
    assessment = runner.read_json(output / "assessment.json")
    assert manifest["actual_mcp_successes"] == 7 and manifest["actual_mcp_failures"] == 0
    assert manifest["export_count"] == 3 and manifest["candidate_specific_orbital_runs"] == 0
    assert manifest["statuses"]["material_decision"] == "Conditional"
    assert manifest["statuses"]["orbital_execution"] == "Complete"
    assert manifest["statuses"]["caid_export_integration"] == "Blocked"
    assert not manifest["production_release"] and not manifest["caid_import_performed"]
    assert all(row["optical_gate"] == "unknown" for row in assessment["qualification_gates"])
    for item in manifest["input_artifacts"] + manifest["output_artifacts"]:
        assert runner.fingerprint(output / item["path"])["sha256"] == item["sha256"]
    proposal = runner.read_json(output / "hardware-ir.proposed.json")
    assert (output / "hardware-ir.proposed.json").read_bytes() == (BASE / "hardware-ir.proposed.json").read_bytes()
    assert proposal["is_valid"] is False
    assert proposal["components"][0]["configuration"]["required_transmission_fraction"] is None
    raw = runner.read_json(output / "run.json")
    assert raw["spectral_diagnostics"][0]["observed"]["sample_count"] == 1600
    assert raw["spectral_diagnostics"][0]["observed"]["integrated_oscillator_strength"] == pytest.approx(1.19)
    export = output / raw["generated_artifacts"][0]["path"]
    export.write_text("corrupted evidence")
    with pytest.raises(ValueError, match="hash mismatch"):
        runner.verify_smoke(output, runner.read_json(BASE / "plan.json"), raw)
