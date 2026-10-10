"""Offline structure-stage checks: source mapping, processes, cache and confidence."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

import pytest

from protein_workflow import folding as fold
from protein_workflow import sequences
from protein_workflow.structures import illustrative_pdb, validate_structure

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_CONFIG = fold.PredictionConfig(backend="fixture", device="cpu")


@pytest.fixture
def inputs(tmp_path: Path) -> Path:
    """Generate the actual #4 input bundle from the recorded UniProt response."""
    record = sequences.load_source(ROOT / "tests/fixtures/abl1/P00519.cache.json", offline=True)
    sequences.export_sequences(record, tmp_path / "inputs")
    return tmp_path / "inputs"


@pytest.mark.parametrize("variant,amino_acid", [("WT", "T"), ("T315I", "I")])
def test_variant_flow_mapping_confidence_and_cache(inputs: Path, tmp_path: Path,
                                                 variant: str, amino_acid: str) -> None:
    """Trace each variant through a real fixture subprocess, then verified cache reuse."""
    first = fold.run_prediction(inputs / f"ABL1_{variant}.fasta", tmp_path / "first",
                                config=FIXTURE_CONFIG, cache=tmp_path / "cache")
    assert first.status == "succeeded" and not first.cache_hit
    manifest = json.loads(first.manifest_path.read_text())
    validation = json.loads(first.validation_path.read_text())
    assert manifest["classification"] == "illustrative"
    assert manifest["structure_prediction_performed"] is False
    assert manifest["inference_executed_this_run"] is False and manifest["docking_ready"] is False
    assert "NOT AN ESMFOLD PREDICTION" in first.structure_path.read_text()
    assert len(validation["residue_mapping"]) == 252
    target = validation["residue_mapping"][73]
    assert target["source_position"] == 315 and target["observed_amino_acid"] == amino_acid
    assert target["structure_residue"] == {"chain": "A", "number": 74, "insertion_code": ""}
    assert target["plddt"] is None
    assert validation["confidence_summary"] == {"mean_ca_plddt": None, "available_residues": 0}
    assert validation["missing_domain_positions"] == validation["unmapped_atoms"] == []
    for name, receipt in manifest["artifacts"].items():
        data = (first.manifest_path.parent / name).read_bytes()
        assert receipt == {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    second = fold.run_prediction(inputs / f"ABL1_{variant}.fasta", tmp_path / "second",
                                 config=FIXTURE_CONFIG, cache=tmp_path / "cache")
    assert second.status == "succeeded" and second.cache_hit
    assert second.structure_path.read_bytes() == first.structure_path.read_bytes()
    assert not (second.manifest_path.parent / "worker.stdout.log").exists()
    second_manifest = json.loads(second.manifest_path.read_text())
    assert second_manifest["backend"]["completed_at"] == manifest["backend"]["completed_at"]
    assert second_manifest["started_at"] != manifest["started_at"]
    assert json.loads((second.manifest_path.parent / "status.json").read_text())["status"] == "succeeded"


def test_custom_domain_mapping_survives(inputs: Path, tmp_path: Path) -> None:
    """Preserve explicit full-source coordinates instead of assuming the default offset."""
    record = sequences.load_source(ROOT / "tests/fixtures/abl1/P00519.cache.json", offline=True)
    sequences.export_sequences(record, tmp_path / "extended", start=229, end=511)
    result = fold.run_prediction(tmp_path / "extended/ABL1_T315I.fasta", tmp_path / "fold",
                                 config=FIXTURE_CONFIG, cache=None)
    assert result.status == "succeeded"
    row = json.loads(result.validation_path.read_text())["residue_mapping"][86]
    assert row["source_position"] == 315 and row["domain_position"] == 87
    assert row["observed_amino_acid"] == "I"


@pytest.mark.parametrize("change", ["file_bytes", "mapping", "mutation", "isoform", "length", "rehash_wrong_sequence"])
def test_invalid_source_bundle_rejected_before_backend(inputs: Path, tmp_path: Path, change: str) -> None:
    """Do not trust hashes alone when source, mapping and mutant identity disagree."""
    path = inputs / "manifest.json"
    manifest = json.loads(path.read_text())
    if change == "mapping": manifest["residue_mapping"][73]["source_position"] = 334
    if change == "mutation": manifest["mutation"]["domain_position"] = 73
    if change == "isoform": manifest["source"]["isoform"] = "P00519-2"
    if change == "length": manifest["domain"]["length"] -= 1
    if change in ("file_bytes", "rehash_wrong_sequence"):
        fasta = inputs / "ABL1_WT.fasta"
        lines = fasta.read_text().splitlines()
        lines[1] = "A" + lines[1][1:]
        fasta.write_text("\n".join(lines) + "\n")
        if change == "rehash_wrong_sequence":
            data = fasta.read_bytes()
            manifest["artifacts"][fasta.name] = {"sha256": sequences.sha256(data), "bytes": len(data)}
            manifest["sequences"]["WT"]["sha256"] = sequences.sha256("".join(lines[1:]).encode())
    path.write_text(json.dumps(manifest))
    with pytest.raises(fold.PredictionError):
        fold.run_prediction(inputs / "ABL1_WT.fasta", tmp_path / "run", config=FIXTURE_CONFIG)
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize("change", ["missing", "identity", "chain", "insertion", "alternate", "duplicate",
                                    "nonfinite", "confidence", "backbone", "models", "truncated", "extra_residue"])
def test_invalid_pdb_exposes_missing_and_unmapped_residues(change: str) -> None:
    """Reject malformed/ambiguous structures instead of silently shifting residue maps."""
    lines = illustrative_pdb("ATG").splitlines()
    atom = next(i for i, line in enumerate(lines) if line.startswith("ATOM"))
    if change == "missing": lines = [line for line in lines if not (line.startswith("ATOM") and int(line[22:26]) == 2)]
    if change == "identity": lines[atom] = lines[atom][:17] + "GLY" + lines[atom][20:]
    if change == "chain": lines[atom] = lines[atom][:21] + "B" + lines[atom][22:]
    if change == "insertion": lines[atom] = lines[atom][:26] + "A" + lines[atom][27:]
    if change == "alternate": lines[atom] = lines[atom][:16] + "A" + lines[atom][17:]
    if change == "duplicate": lines.insert(atom + 1, lines[atom])
    if change == "nonfinite": lines[atom] = lines[atom][:30] + "     nan" + lines[atom][38:]
    if change == "confidence": lines[atom] = lines[atom][:60] + "101.00" + lines[atom][66:]
    if change == "backbone": lines.pop(atom + 1)
    if change == "models": lines.insert(0, "MODEL        2")
    if change == "truncated": lines[atom] = lines[atom][:50]
    if change == "extra_residue": lines[atom] = lines[atom][:22] + "   4" + lines[atom][26:]
    report = validate_structure("\n".join(lines), "ATG", 314, predicted=True)
    assert report["valid"] is False
    assert len(report["residue_mapping"]) == 3
    assert report["residue_mapping"][1]["source_position"] == 315
    if change == "missing":
        assert report["missing_domain_positions"] == [2]
        assert report["residue_mapping"][1]["structure_residue"] is None
    if change in ("chain", "insertion", "alternate", "extra_residue"):
        assert len(report["unmapped_atoms"]) == 1


def test_predicted_confidence_semantics() -> None:
    """Read C-alpha pLDDT on its documented 0..100 scale, never as crystallographic B."""
    lines = illustrative_pdb("ATG").splitlines()
    lines = [line[:60] + " 87.25" + line[66:] if line.startswith("ATOM") else line for line in lines]
    report = validate_structure("\n".join(lines), "ATG", 314, predicted=True)
    assert report["valid"] is True
    assert report["confidence_scale"] == [0, 100]
    assert report["confidence_summary"] == {"mean_ca_plddt": 87.25, "available_residues": 3}
    assert report["residue_mapping"][1]["plddt"] == 87.25


@pytest.mark.parametrize("change", ["valid", "raw_scale", "length", "out_of_range", "pdb_disagreement", "revision"])
def test_representative_predicted_backend_receipt(inputs: Path, tmp_path: Path, change: str) -> None:
    """Validate simulated real-backend format and scale conversion without claiming inference."""
    source = fold.load_sequence_input(inputs / "ABL1_WT.fasta")
    config = fold.PredictionConfig(device="cpu")
    runtime = {"backend": "esmfold", "test_receipt_only": True}
    raw = tmp_path / "raw"
    raw.mkdir()
    lines = illustrative_pdb(source.sequence).splitlines()
    lines = [line[:60] + " 87.25" + line[66:] if line.startswith("ATOM") else line for line in lines]
    (raw / "structure.pdb").write_text("\n".join(lines))
    backend = {"schema_version": 1, "classification": "computed_prediction",
               "sequence_sha256": sequences.sha256(source.sequence.encode()), "configuration": fold.asdict(config),
               "environment": runtime, "sequence_sent_to_external_service": False, "runtime_seconds": 1.0,
               "completed_at": "2026-10-05T00:00:00+00:00",
               "model": {"id": fold.MODEL_ID, "revision": fold.MODEL_REVISION, "resolved_config_revision": fold.MODEL_REVISION}}
    confidence = {"kind": "predicted_lddt", "raw_scale": [0, 1], "pdb_scale": [0, 100],
                  "raw_ca_values": [0.8725] * len(source.sequence)}
    if change == "raw_scale": confidence["raw_scale"] = [0, 100]
    if change == "length": confidence["raw_ca_values"].pop()
    if change == "out_of_range": confidence["raw_ca_values"][0] = 87.25
    if change == "pdb_disagreement": confidence["raw_ca_values"][0] = 0.5
    if change == "revision": backend["model"]["resolved_config_revision"] = "different-checkpoint"
    (raw / "backend.json").write_text(json.dumps(backend))
    (raw / "confidence.json").write_text(json.dumps(confidence))
    if change == "valid":
        assert fold._validate_raw(raw, source, config, runtime, tmp_path / "validation.json") == backend
    else:
        with pytest.raises(fold.PredictionError):
            fold._validate_raw(raw, source, config, runtime, tmp_path / "validation.json")


@pytest.mark.parametrize("change", ["seed", "chunk", "recycles", "device", "backend", "runtime", "sequence"])
def test_cache_changes_with_scientific_inputs(change: str) -> None:
    """A different model request or runtime must never reuse a previous prediction."""
    config, runtime, sequence = FIXTURE_CONFIG, {"python": "test"}, "ATG"
    baseline = fold.cache_identity(sequence, config, runtime)
    if change == "seed": config = replace(config, seed=1)
    if change == "chunk": config = replace(config, chunk_size=32)
    if change == "recycles": config = replace(config, num_recycles=0)
    if change == "device": config = replace(config, device="cuda")
    if change == "backend": config = replace(config, backend="esmfold")
    if change == "runtime": runtime = {"python": "other"}
    if change == "sequence": sequence = "AIG"
    assert fold.cache_identity(sequence, config, runtime) != baseline


@pytest.mark.parametrize("corruption", ["bytes", "rehash_bad_structure", "receipt"])
def test_corrupted_cache_never_becomes_success(inputs: Path, tmp_path: Path, corruption: str) -> None:
    """Recheck output semantics even when a cache file's hash has been updated."""
    first = fold.run_prediction(inputs / "ABL1_WT.fasta", tmp_path / "first",
                                config=FIXTURE_CONFIG, cache=tmp_path / "cache")
    key = json.loads(first.manifest_path.read_text())["cache_key"]
    entry = tmp_path / "cache" / key
    receipt = json.loads((entry / "cache.json").read_text())
    if corruption == "receipt":
        receipt["identity"]["configuration"]["seed"] = 999
    else:
        path = entry / "structure.pdb"
        path.write_text("BROKEN\n")
        if corruption == "rehash_bad_structure":
            receipt["artifacts"][path.name] = {"sha256": sequences.sha256(path.read_bytes()), "bytes": path.stat().st_size}
    (entry / "cache.json").write_text(json.dumps(receipt))
    second = fold.run_prediction(inputs / "ABL1_WT.fasta", tmp_path / "second",
                                 config=FIXTURE_CONFIG, cache=tmp_path / "cache")
    assert second.status == "failed" and second.structure_path is None
    assert json.loads(second.manifest_path.read_text())["structure_artifact"] is None
    assert not (tmp_path / "second/worker.stdout.log").exists()
    if corruption == "rehash_bad_structure":
        assert len(json.loads(second.validation_path.read_text())["missing_domain_positions"]) == 252
    fresh = fold.run_prediction(inputs / "ABL1_WT.fasta", tmp_path / "fresh", config=FIXTURE_CONFIG, cache=None)
    assert fresh.status == "succeeded" and not fresh.cache_hit


def test_missing_executable_and_existing_output(inputs: Path, tmp_path: Path) -> None:
    """Keep a reviewable failure receipt and refuse to overwrite it on retry."""
    result = fold.run_prediction(inputs / "ABL1_WT.fasta", tmp_path / "failed", config=FIXTURE_CONFIG,
                                 python=str(tmp_path / "nonexistent-python"), cache=tmp_path / "cache")
    assert result.status == "failed" and result.structure_path is None
    data = json.loads(result.manifest_path.read_text())
    assert data["failed_step"] == "probing_backend"
    assert data["inference_attempted"] is False
    assert not (tmp_path / "cache").exists()
    before = result.manifest_path.read_bytes()
    with pytest.raises(FileExistsError):
        fold.run_prediction(inputs / "ABL1_WT.fasta", tmp_path / "failed", config=FIXTURE_CONFIG)
    assert result.manifest_path.read_bytes() == before


@pytest.mark.parametrize("failure", ["exit", "timeout", "bad_pdb"])
def test_backend_failure_states_and_logs(inputs: Path, tmp_path: Path,
                                       monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    """Exercise an actual failed, hung or invalid-output subprocess without heavy packages."""
    wrapper = tmp_path / "worker.py"
    wrapper.write_text("import sys, subprocess, time\nfrom pathlib import Path\n"
                       f"real_worker = {str(fold.WORKER)!r}\n"
                       "if '--probe' in sys.argv:\n"
                       "    sys.exit(subprocess.call([sys.executable, real_worker, *sys.argv[1:]]))\n"
                       f"failure = {failure!r}\n"
                       "if failure == 'exit':\n    print('backend failed', file=sys.stderr, flush=True)\n    sys.exit(7)\n"
                       "if failure == 'timeout':\n    print('started waiting', flush=True)\n    time.sleep(30)\n"
                       "subprocess.run([sys.executable, real_worker, *sys.argv[1:]], check=True)\n"
                       "out=Path(sys.argv[sys.argv.index('--output')+1])\n"
                       "(out/'structure.pdb').write_text('invalid structure\\n')\n")
    monkeypatch.setattr(fold, "WORKER", wrapper)
    result = fold.run_prediction(inputs / "ABL1_WT.fasta", tmp_path / "run", config=FIXTURE_CONFIG,
                                 cache=tmp_path / "cache", timeout=0.8)
    assert result.status == ("timed_out" if failure == "timeout" else "failed")
    assert result.structure_path is None and not (tmp_path / "cache").exists()
    manifest = json.loads(result.manifest_path.read_text())
    assert manifest["error"] and manifest["runtime_seconds"] >= 0
    assert (result.manifest_path.parent / "worker.stderr.log").exists()
    assert json.loads((result.manifest_path.parent / "status.json").read_text())["status"] == result.status
    if failure == "bad_pdb":
        assert json.loads(result.validation_path.read_text())["missing_domain_positions"] == list(range(1, 253))


@pytest.mark.skipif(os.name != "posix" or not Path("/proc/self").exists(), reason="Process-group check requires Linux procfs")
@pytest.mark.parametrize("stage", ["fold", "pocket"])
def test_timeout_terminates_descendant(tmp_path: Path, stage: str) -> None:
    """Check the actual descendant in procfs, including containers with a different mounted PID namespace."""
    from protein_workflow import pockets

    script = tmp_path / "spawn.py"
    child_pid = tmp_path / "child.pid"
    child_code = ("import os,time\nfrom pathlib import Path\n"
                  f"Path({str(child_pid)!r}).write_text(os.readlink('/proc/self'))\n"
                  "time.sleep(30)\n")
    script.write_text("import subprocess,sys,time\nfrom pathlib import Path\n"
                      f"subprocess.Popen([sys.executable,'-c',{child_code!r}])\n"
                      "time.sleep(30)\n")
    runner, error = (fold.run_process, fold.PredictionTimeout) if stage == "fold" else (pockets.run_process, pockets.PocketTimeout)
    with pytest.raises(error):
        runner([sys.executable, str(script)], tmp_path, "worker", 0.5)
    pid = int(child_pid.read_text())
    proc = Path(f"/proc/{pid}/stat")

    def still_running() -> bool:
        """Allow an already killed descendant to disappear between procfs reads."""
        try:
            return proc.read_text().split()[2] != "Z"
        except FileNotFoundError:
            return False

    deadline = time.monotonic() + 2
    while still_running() and time.monotonic() < deadline:
        time.sleep(.01)
    assert not still_running()


@pytest.mark.parametrize("field,value", [("seed", -1), ("seed", True), ("chunk_size", 0),
                                        ("chunk_size", 1025), ("num_recycles", -1), ("num_recycles", 1.5)])
def test_invalid_config(field: str, value: Any) -> None:
    """Reject impossible or ambiguous model parameters before running a backend."""
    with pytest.raises(fold.PredictionError):
        replace(FIXTURE_CONFIG, **{field: value}).validate()


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), True])
def test_invalid_timeout(inputs: Path, tmp_path: Path, timeout: float) -> None:
    """Require a bounded positive runtime before creating a run directory."""
    with pytest.raises(fold.PredictionError):
        fold.run_prediction(inputs / "ABL1_WT.fasta", tmp_path / "run", config=FIXTURE_CONFIG, timeout=timeout)
    assert not (tmp_path / "run").exists()


def test_fixture_cli_is_explicit_and_offline(inputs: Path, tmp_path: Path) -> None:
    """Use the actual CLI with no model package, downloads, service or GPU."""
    result = subprocess.run([sys.executable, "-m", "protein_workflow.folding", "--backend", "fixture",
                             "--fasta", str(inputs / "ABL1_T315I.fasta"), "--output", str(tmp_path / "run"),
                             "--no-cache"], cwd=ROOT, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    stdout = json.loads(result.stdout)
    assert stdout["status"] == "succeeded"
    manifest = json.loads(Path(stdout["manifest"]).read_text())
    assert manifest["classification"] == "illustrative" and manifest["prediction_validated"] is True
    assert "probing_backend" in result.stderr and "validating_structure" in result.stderr
