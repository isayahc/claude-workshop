"""Evidence-boundary tests; numeric unit-test values are mathematical fixtures only."""
import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from orbital_viewer.benchmark import (empty_record, fingerprint, relative_name, run,
                                      snapshot_inputs, spectrum_summary, validate_plan)

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "benchmarks" / "PROCESS-01" / "plan.json"


def plan():
    return json.loads(PLAN.read_text())


def test_declared_plan_covers_tools_without_claiming_material_data():
    value = validate_plan(plan())
    assert len(value["calls"]) == 7
    assert {c["name"] for c in value["calls"]} == {
        "inspect_cube", "inspect_transitions", "broaden_spectrum", "export_orbital", "export_spectrum"}
    assert all(x["classification"] == "Assumed" for x in value["assumptions"])
    decision = empty_record(value)["engineering_decision"]
    assert decision["release_allowed"] is False
    assert all(v is None for k, v in decision.items() if k not in {"status", "release_allowed", "reason"})


@pytest.mark.parametrize("name", ["../x", "/x", "C:/x", "a\\b", "a//b", "./x", "a/../x", "", "a\0b"])
def test_unsafe_names_rejected(name):
    with pytest.raises(ValueError):
        relative_name(name)


@pytest.mark.parametrize("change", ["scope", "tool", "undeclared", "duplicate", "provenance"])
def test_plan_rejects_unsupported_claims_and_calls(change):
    value = copy.deepcopy(plan())
    if change == "scope": value["evidence_scope"] = "measured_photoinitiator"
    if change == "tool": value["calls"][0]["name"] = "run_dft"
    if change == "undeclared": value["calls"][0]["arguments"]["filename"] = "missing.csv"
    if change == "duplicate": value["inputs"].append(value["inputs"][0])
    if change == "provenance": value["inputs"][0]["provenance"] = ""
    with pytest.raises(ValueError):
        validate_plan(value)


def test_area_diagnostic_is_derived_not_a_cure_dose():
    result = spectrum_summary({"integrated_oscillator_strength": 1.8, "total_oscillator_strength": 2,
                               "energy_ev": [1, 2], "caveats": ["Test fixture only"]})
    assert result["derived"]["relative_area_error"] == pytest.approx(0.1)
    assert result["observed"]["intensity_unit"] == "oscillator_strength/eV"
    assert "dose" not in str(result)
    zero = spectrum_summary({"integrated_oscillator_strength": 0, "total_oscillator_strength": 0,
                             "energy_ev": [1, 2], "caveats": ["Test fixture only"]})
    assert zero["derived"]["relative_area_error"] is None


def test_input_snapshot_hashes_and_escape_rejection(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    source = root / "fixture.csv"
    source.write_text("mathematical test fixture")
    value = {"inputs": [{"filename": "fixture.csv", "provenance": "test only"}]}
    records = snapshot_inputs(value, root, tmp_path / "snapshot")
    assert records[0]["sha256"] == fingerprint(source)["sha256"]
    assert (tmp_path / "snapshot/fixture.csv").read_bytes() == source.read_bytes()
    mismatch = {"inputs": [{"filename": "fixture.csv", "source_blob_sha1": "0" * 40}]}
    with pytest.raises(ValueError, match="declared repository fixture"):
        snapshot_inputs(mismatch, root, tmp_path / "mismatch")
    outside = tmp_path / "outside.csv"
    outside.write_text("not an authorized input")
    try:
        (root / "escape.csv").symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks unavailable")
    with pytest.raises(ValueError):
        snapshot_inputs({"inputs": [{"filename": "escape.csv"}]}, root, tmp_path / "other")


def test_failed_run_keeps_error_evidence_and_never_releases(tmp_path):
    code = run(PLAN, tmp_path / "missing-input-directory", tmp_path / "run")
    record = json.loads((tmp_path / "run/run.json").read_text())
    assert code == 1 and record["tool_execution_status"] == "failed"
    assert record["calls"] == [] and record["error"]["type"] == "FileNotFoundError"
    assert record["engineering_decision"]["release_allowed"] is False
    with pytest.raises(FileExistsError):
        run(PLAN, tmp_path, tmp_path / "run")


def test_real_stdio_record_and_exports(tmp_path):
    pytest.importorskip("mcp")
    output = tmp_path / "record"
    result = subprocess.run([sys.executable, "-m", "orbital_viewer.benchmark", "--plan", str(PLAN),
        "--data-dir", str(ROOT / "examples/mcp"), "--output", str(output)],
        cwd=ROOT, capture_output=True, text=True, timeout=150)
    assert result.returncode == 0, result.stdout + result.stderr
    record = json.loads((output / "run.json").read_text())
    assert record["tool_execution_status"] == "passed"
    assert len(record["calls"]) == 7 and all(c["status"] == "succeeded" for c in record["calls"])
    assert all(not c["response"]["isError"] for c in record["calls"])
    assert record["calls"][0]["response"]["structuredContent"]["transition_count"] == 4
    assert record["spectral_diagnostics"][0]["observed"]["sample_count"] == 1600
    assert record["spectral_diagnostics"][0]["derived"]["relative_area_error"] < 1e-5
    assert len(record["generated_artifacts"]) == 3
    for artifact in record["generated_artifacts"]:
        assert fingerprint(output / artifact["path"])["sha256"] == artifact["sha256"]
        assert artifact["evidence_scope"] == "synthetic_fixture"
    assert record["engineering_decision"]["release_allowed"] is False
    assert record["engineering_decision"]["selected_wavelength_nm"] is None
