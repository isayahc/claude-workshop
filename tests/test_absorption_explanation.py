"""EDU-01 evidence regression tests; every input here is a software fixture."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from orbital_viewer.absorption_explanation import (
    build_explanation, render_html, transition_rows, verify_bundle, write_explanation,
)
from orbital_viewer.benchmark import fingerprint
from orbital_viewer.data import HC

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "benchmarks/EDU-01/plan.json"
LESSON = ROOT / "benchmarks/EDU-01/lesson.json"


@pytest.fixture(scope="module")
def evidence(tmp_path_factory):
    pytest.importorskip("mcp")
    directory = tmp_path_factory.mktemp("edu") / "run"
    result = subprocess.run([sys.executable, "-m", "orbital_viewer.benchmark",
        "--plan", str(PLAN), "--data-dir", str(ROOT / "examples/mcp"), "--output", str(directory)],
        cwd=ROOT, capture_output=True, text=True, timeout=150)
    assert result.returncode == 0, result.stdout + result.stderr
    return directory


def table(energy=4.0, strength=0.0):
    return {"schema_version": "1", "transition_count": 1, "caveats": ["Test fixture"],
            "transitions": [{"energy_ev": energy, "wavelength_nm": HC / energy if energy else 0,
                             "oscillator_strength": strength}]}


def test_conversion_does_not_assign_a_state_or_orbital():
    row = transition_rows(table())[0]
    assert row["derived_wavelength_nm"] == pytest.approx(309.960496)
    assert row["oscillator_strength"] == 0
    assert row["molecular_state"] is None and row["orbital_assignment"] is None


@pytest.mark.parametrize("change", ["zero_energy", "negative_energy", "negative_strength", "nan",
                                    "wavelength", "count", "unit"])
def test_invalid_or_inconsistent_scientific_values_are_rejected(change):
    data = table()
    if change == "zero_energy": data["transitions"][0]["energy_ev"] = 0
    if change == "negative_energy": data["transitions"][0]["energy_ev"] = -4
    if change == "negative_strength": data["transitions"][0]["oscillator_strength"] = -1
    if change == "nan": data["transitions"][0]["energy_ev"] = float("nan")
    if change == "wavelength": data["transitions"][0]["wavelength_nm"] = 400
    if change == "count": data["transition_count"] = 2
    if change == "unit": data["energy_unit"] = "nm"
    with pytest.raises(ValueError):
        transition_rows(data)


def test_actual_mcp_bundle_to_explanation(evidence):
    report = build_explanation(evidence, LESSON)
    assert report["provenance"]["actual_mcp_calls"] == 8
    assert len(report["artifacts"]) == 4
    assert sum(a["media_type"] == "text/html" for a in report["artifacts"]) == 3
    observation = report["observations"][0]
    assert observation["derived"]["strongest_input_rows"] == [2]
    assert observation["rows"][1]["derived_wavelength_nm"] == pytest.approx(292.34661259136996)
    assert report["spectrum"]["recomputed_energy_integral"] == pytest.approx(1.19)
    assert report["spectrum"]["sample_count"] == 1600
    assert report["spectrum"]["relative_area_error"] < 1e-10
    assert report["spectrum"]["intensity_unit"] == "oscillator_strength/eV"
    assert report["cube"]["summary"]["shape"] == [2, 2, 2]
    assert report["cube"]["nto_state_and_pair"] is None
    assert report["assignment"]["assignment_allowed"] is False
    assert report["assignment"]["assigned_transition"] is None
    assert report["engineering_decision"]["release_allowed"] is False
    assert report["engineering_decision"]["quantum_results_generated"] is False


@pytest.mark.parametrize("change", ["failed", "scope", "assignment", "call_arguments", "call_missing",
                                    "mcp_error", "structured_text", "input", "export", "plan"])
def test_failed_or_changed_evidence_cannot_be_presented_as_success(evidence, tmp_path, change):
    root = tmp_path / "run"
    shutil.copytree(evidence, root)
    record = json.loads((root / "run.json").read_text())
    if change == "failed": record["tool_execution_status"] = "failed"
    if change == "scope": record["evidence_scope"] = "computed_molecule"
    if change == "assignment": record["engineering_decision"]["assigned_transition"] = "HOMO to LUMO"
    if change == "call_arguments": record["calls"][0]["arguments"]["filename"] = "other.csv"
    if change == "call_missing": record["calls"].pop()
    if change == "mcp_error": record["calls"][0]["response"]["isError"] = True
    if change == "structured_text": record["calls"][0]["response"]["content"][0]["text"] = "{}"
    if change == "input": (root / "inputs/transitions.csv").write_text("changed fixture")
    if change == "export": (root / record["generated_artifacts"][0]["path"]).write_text("changed export")
    if change == "plan": (root / "plan.json").write_text((root / "plan.json").read_text() + " ")
    (root / "run.json").write_text(json.dumps(record))
    with pytest.raises(ValueError):
        verify_bundle(root)


def test_rehashed_csv_with_wrong_values_is_rejected(evidence, tmp_path):
    root = tmp_path / "run"
    shutil.copytree(evidence, root)
    record = json.loads((root / "run.json").read_text())
    artifact = next(a for a in record["generated_artifacts"] if a["media_type"] == "text/csv")
    path = root / artifact["path"]
    text = path.read_text()
    lines = text.splitlines()
    row = lines[1].split(",")
    row[2] = "1.000000000000000000e+00"
    lines[1] = ",".join(row)
    path.write_text("\n".join(lines) + "\n")
    artifact.update(fingerprint(path))
    call = record["calls"][artifact["call_sequence"] - 1]
    call["response"]["structuredContent"]["size_bytes"] = artifact["size_bytes"]
    call["response"]["content"][0]["text"] = json.dumps(call["response"]["structuredContent"])
    (root / "run.json").write_text(json.dumps(record))
    with pytest.raises(ValueError, match="Exported spectrum differs"):
        build_explanation(root, LESSON)


def test_source_ledger_and_unknown_assignment_survive_html(evidence):
    report = build_explanation(evidence, LESSON)
    assert len(report["concepts"]) == 9 and len(report["manual_handoffs"]) == 5
    assert "NTO interpretation, if used" in {x["required_for"] for x in report["missing_data"]}
    html = render_html(report)
    assert "Assignment blocked" in html and "positive/negative charge" in html
    assert "f/eV" in html and "Input row numbers are not molecular state IDs" in html
    assert html.count("<iframe") == 3
    changed = copy.deepcopy(report)
    changed["concepts"][0]["explanation"] = "<script>alert(1)</script>"
    assert "<script>alert(1)</script>" not in render_html(changed)
    assert "&lt;script&gt;" in render_html(changed)


def test_cli_writes_portable_report_and_refuses_overwrite(evidence, tmp_path):
    root = tmp_path / "run"
    shutil.copytree(evidence, root)
    result = subprocess.run([sys.executable, "-m", "orbital_viewer.absorption_explanation",
        "--run-dir", str(root), "--lesson", str(LESSON)], cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((root / "explanation.json").read_text())
    assert report["provenance"]["lesson"] == fingerprint(root / "lesson.json")
    assert (root / "index.html").is_file()
    before = fingerprint(root / "explanation.json")
    with pytest.raises(FileExistsError):
        write_explanation(root, LESSON)
    assert fingerprint(root / "explanation.json") == before
