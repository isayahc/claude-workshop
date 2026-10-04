"""Numeric test cases are synthetic arithmetic, NOT electrolyte measurements."""
import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from orbital_viewer.electrolyte_screen import assess, margin_gate, run, validate_potential

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "benchmarks/BAT-01"


def load(name):
    return json.loads((CASE / name).read_text(encoding="utf-8"))


def potential(value, kind="thermodynamic_redox"):
    return {"value": value, "unit": "V", "kind": kind,
            "reference": "SYNTHETIC_TEST_REFERENCE", "conditions_id": "SYNTHETIC_TEST_MEDIUM",
            "uncertainty_v": 0.1, "classification": "Observed", "evidence_ids": ["SYNTHETIC_TEST_ONLY"]}


def test_supplied_requirement_is_not_a_charge_voltage():
    design = load("design.json")
    assert design["target"]["cathode_potential"]["value"] == 4.3
    assert design["target"]["cathode_potential"]["reference"] is None
    assert design["candidate_list_provenance"]["classification"] == "Assumed"
    assert all(value is None for value in design["context"].values())
    caid = design["caid_mapping"]
    assert caid["approved_terminal_charge_voltage_v"] is None
    assert caid["charger_or_bms_change_allowed"] is False
    assert caid["schema_validation_performed"] is False
    assert caid["caid_import_performed"] is False


def test_real_case_has_no_invented_candidate_results():
    design = load("design.json")
    result = assess(design)
    assert len(result["candidate_results"]) == 6
    for source, candidate in zip(design["candidates"], result["candidate_results"]):
        assert source["scientific_artifacts"] == []
        assert source["oxidation_potential"] is source["reduction_potential"] is None
        assert candidate["intrinsic_oxidation"]["status"] == "unknown"
        assert candidate["intrinsic_reduction"]["status"] == "unknown"
        assert candidate["intrinsic_oxidation"]["clearance_interval_v"] is None
        assert candidate["formulation_qualification"] == "unknown"
    assert result["engineering_decision"]["release_allowed"] is False
    assert result["engineering_decision"]["selected_electrolyte"] is None
    assert result["engineering_decision"]["approved_terminal_charge_voltage_v"] is None


def test_sources_resolve_and_research_priority_is_not_selection():
    sources = load("sources.json")["sources"]
    ids = {s["id"] for s in sources}
    assert len(ids) == len(sources) == 7
    assert all(s["classification"] == "External knowledge" and s["access"] and s["limitation"] for s in sources)
    design = load("design.json")
    for candidate in design["candidates"]:
        assert set(candidate["source_ids"]) <= ids
        assert candidate["assessment_classification"] == "External knowledge"
    proposal = design["engineering_proposal"]
    assert set(proposal["source_ids"]) <= ids
    assert proposal["classification"] == "Assumed"
    assert proposal["selected_electrolyte"] is None


def test_proposed_workflow_is_acyclic_and_not_executed():
    workflow = load("workflow.json")
    assert workflow["execution_status"] == "proposed_not_executed"
    seen = set()
    for job in workflow["jobs"]:
        assert job["id"] not in seen and set(job["depends_on"]) <= seen
        assert job["status"] in {"not_run", "blocked_missing_inputs"}
        assert job["requires"] and job["outputs"]
        seen.add(job["id"])
    assert {"electronic_states", "redox_thermodynamics", "decomposition_and_interfaces", "cell_validation", "caid_handoff"} <= seen
    assert len(workflow["manual_handoffs"]) == 7


def test_mcp_plan_excludes_irrelevant_optical_evidence():
    plan = load("plan.json")
    assert plan["evidence_scope"] == "synthetic_fixture"
    assert [c["name"] for c in plan["calls"]] == ["inspect_cube", "export_orbital"]
    assert len(plan["inputs"]) == 1
    assert plan["inputs"][0]["source_blob_sha1"] == "00360f0401245ef8fa2524e3079da0adfed44ea3"
    assert "NOT any BAT-01 candidate" in plan["inputs"][0]["provenance"]
    assert len(plan["intentionally_unused_tools"]) == 3


@pytest.mark.parametrize("high,low,expected", [(6, 4, "pass"), (3, 4, "fail"), (4.1, 4, "unknown")])
def test_conservative_three_state_gate(high, low, expected):
    result = margin_gate(potential(high), potential(low), 0.2)
    assert result["status"] == expected
    assert result["clearance_interval_v"] == pytest.approx([high - low - 0.4, high - low])


def test_reduction_comparison_has_the_correct_direction():
    # Synthetic electrode and redox numbers; high anode potential suppresses reduction.
    assert margin_gate(potential(2, "operating_potential"), potential(1), 0.1)["status"] == "pass"
    assert margin_gate(potential(0, "operating_potential"), potential(1), 0.1)["status"] == "fail"


@pytest.mark.parametrize("field,value", [("reference", None), ("conditions_id", None),
    ("uncertainty_v", None), ("evidence_ids", []), ("classification", "Assumed")])
def test_missing_evidence_never_becomes_pass(field, value):
    high = potential(10)
    high[field] = value
    assert margin_gate(high, potential(0), 0.1)["status"] == "unknown"


@pytest.mark.parametrize("field", ["reference", "conditions_id"])
def test_mismatched_reference_or_medium_is_not_silently_converted(field):
    high = potential(10)
    high[field] = "OTHER_SYNTHETIC_CONTEXT"
    result = margin_gate(high, potential(0), 0.1)
    assert result["status"] == "unknown" and result["clearance_interval_v"] is None


@pytest.mark.parametrize("high,low,margin", [(None, potential(1), 0.1), (potential(2), None, 0.1), (potential(2), potential(1), None)])
def test_missing_margin_or_potential_stays_unknown(high, low, margin):
    assert margin_gate(high, low, margin)["status"] == "unknown"


@pytest.mark.parametrize("value", [True, False, "4.3", float("nan"), float("inf"), -float("inf")])
def test_non_numeric_or_nonfinite_potentials_rejected(value):
    with pytest.raises(ValueError):
        validate_potential(potential(value))


@pytest.mark.parametrize("field,value", [("uncertainty_v", -0.1), ("uncertainty_v", True),
    ("unit", "eV"), ("kind", "measured_oxidation_onset"), ("kind", "HOMO"),
    ("reference", ""), ("conditions_id", ""), ("evidence_ids", [""]), ("classification", "computed")])
def test_invalid_metadata_rejected(field, value):
    item = potential(1)
    item[field] = value
    with pytest.raises(ValueError):
        validate_potential(item)


@pytest.mark.parametrize("value", [-0.1, True, float("nan")])
def test_invalid_margins_rejected_even_without_potentials(value):
    with pytest.raises(ValueError):
        margin_gate(None, None, value)


def test_overflow_is_not_a_passing_gate():
    with pytest.raises(ValueError, match="overflow"):
        margin_gate(potential(1e308), potential(-1e308), 0)


def test_duplicate_candidates_and_wrong_potential_roles_rejected():
    design = load("design.json")
    design["candidates"].append(copy.deepcopy(design["candidates"][0]))
    with pytest.raises(ValueError, match="unique"):
        assess(design)
    design = load("design.json")
    design["candidates"][0]["oxidation_potential"] = potential(6, "operating_potential")
    with pytest.raises(ValueError, match="substitute"):
        assess(design)


def test_all_intrinsic_passes_still_cannot_release_an_electrolyte():
    design = load("design.json")
    design["target"].update(cathode_potential=potential(4, "operating_potential"),
                            anode_potential=potential(2, "operating_potential"), required_margin_v=0.1)
    for candidate in design["candidates"]:
        candidate.update(oxidation_potential=potential(6), reduction_potential=potential(0))
    result = assess(design)
    assert all(c["intrinsic_oxidation"]["status"] == c["intrinsic_reduction"]["status"] == "pass" for c in result["candidate_results"])
    assert result["engineering_decision"]["release_allowed"] is False
    assert all(c["formulation_qualification"] == "unknown" for c in result["candidate_results"])
    design["release_allowed"] = True
    with pytest.raises(ValueError, match="release_allowed"):
        assess(design)


def test_receipt_hashes_inputs_and_never_overwrites(tmp_path):
    output = tmp_path / "assessment.json"
    assert run(CASE / "design.json", output) == 0
    value = json.loads(output.read_text())
    assert len(value["design_sha256"]) == len(value["implementation_sha256"]) == 64
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        run(CASE / "design.json", output)
    assert before == output.read_bytes()


def test_actual_stdio_cube_calls_are_only_synthetic_tooling_evidence(tmp_path):
    pytest.importorskip("mcp")
    from orbital_viewer.benchmark import fingerprint, validate_plan
    validate_plan(load("plan.json"))
    output = tmp_path / "mcp"
    result = subprocess.run([sys.executable, "-m", "orbital_viewer.benchmark", "--plan", str(CASE / "plan.json"),
        "--data-dir", str(ROOT / "examples/mcp"), "--output", str(output)],
        cwd=ROOT, capture_output=True, text=True, timeout=150)
    assert result.returncode == 0, result.stdout + result.stderr
    record = json.loads((output / "run.json").read_text())
    assert record["tool_execution_status"] == "passed"
    assert len(record["calls"]) == 2
    assert all(c["status"] == "succeeded" and not c["response"]["isError"] for c in record["calls"])
    assert record["spectral_diagnostics"] == []
    assert len(record["generated_artifacts"]) == 1
    for artifact in record["input_artifacts"] + record["generated_artifacts"]:
        assert fingerprint(output / artifact["path"])["sha256"] == artifact["sha256"]
    assert record["engineering_decision"]["release_allowed"] is False
    assert all(record["engineering_decision"][k] is None for k in load("plan.json")["unknown_quantities"])
