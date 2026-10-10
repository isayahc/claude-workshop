"""Offline pocket contracts, real recorded output, independent variants and process failures."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import pytest

from protein_workflow import folding, pockets, sequences
from protein_workflow.pocket_io import (PocketError, parse_info, parse_pockets,
                                       pdb_atoms, propose_box)
from protein_workflow.structures import THREE_TO_ONE, validate_structure

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/fpocket"


def reference_mapping(pdb: str) -> list[dict[str, Any]]:
    """Map the experimental reference's PDB identifiers, leaving unknown source positions null."""
    residues = {key[:3]: {"source_position": None, "domain_position": None, "domain_index": None,
                         "structure_residue": dict(zip(("chain", "number", "insertion_code"), key[:3], strict=True)),
                         "observed_amino_acid": THREE_TO_ONE[atom["residue_name"]], "plddt": None}
                for key, atom in pdb_atoms(pdb).items()}
    return list(residues.values())


@pytest.fixture
def reference(tmp_path: Path) -> Path:
    """Copy real fpocket output excerpts so each malformed-output test can edit its own data."""
    destination = tmp_path / "reference"
    shutil.copytree(FIXTURE, destination)
    return destination


@pytest.fixture
def executable(tmp_path: Path) -> str:
    """Install an explicitly illustrative standalone executable stub with no runtime dependencies."""
    path = tmp_path / "fpocket stub"
    path.write_text(f"#!{sys.executable}\n" + (FIXTURE / "stub_fpocket.py").read_text())
    path.chmod(0o755)
    return str(path)


@pytest.fixture
def structures(tmp_path: Path) -> dict[str, Path]:
    """Produce both actual #5 fixture bundles through their isolated workers."""
    record = sequences.load_source(ROOT / "tests/fixtures/abl1/P00519.cache.json", offline=True)
    inputs = tmp_path / "sequences"
    sequences.export_sequences(record, inputs)
    results = {}
    for variant in ("WT", "T315I"):
        result = folding.run_prediction(inputs / f"ABL1_{variant}.fasta", tmp_path / f"fold-{variant}",
                                        config=folding.PredictionConfig(backend="fixture", device="cpu"), cache=None)
        assert result.status == "succeeded"
        results[variant] = result.manifest_path
    return results


def test_recorded_reference_parsing_and_geometry(reference: Path) -> None:
    """Parse real output, check saved provenance, and assert envelope geometry independently."""
    provenance = pockets.read_json(reference / "provenance.json")
    pockets.verified_files(reference, provenance["artifacts"])
    pdb = (reference / "contact-reference.pdb").read_text()
    records = parse_pockets(reference / "receptor_out", pdb, reference_mapping(pdb))
    assert [row["id"] for row in records] == ["pocket1", "pocket2"]
    assert [len(row["geometry"]["alpha_spheres"]) for row in records] == [24, 70]
    assert len(records[0]["residues"]) == 11
    assert all(row["source_position"] is None for row in records[0]["residues"])
    assert records[0]["descriptors"]["Volume"]["unit"] == "angstrom_cubed"
    assert records[0]["descriptors"]["Total SASA"]["unit"] == "angstrom_squared"
    assert records[0]["geometry"]["sphere_bounds"]["min"] == pytest.approx([-15.49, 1.48, 32.276])
    assert records[0]["geometry"]["sphere_bounds"]["max"] == pytest.approx([-.098, 17.131, 46.718])
    box = propose_box(records[0], padding=4)
    assert box["center"] == pytest.approx([-7.794, 9.3055, 39.497])
    assert box["size"] == pytest.approx([23.392, 23.651, 22.442])
    assert box["coordinate_unit"] == "angstrom" and box["binding_site_validated"] is False


@pytest.mark.parametrize("change", ["junk", "duplicate_id", "missing_score", "duplicate_score", "nonfinite",
                                    "bad_number", "fractional_count", "missing_rank"])
def test_malformed_info_rejected(reference: Path, change: str) -> None:
    """Do not silently ignore malformed, duplicated, truncated or nonfinite descriptors."""
    text = (reference / "receptor_out/receptor_info.txt").read_text()
    if change == "junk": text = "garbage\n" + text
    if change == "duplicate_id": text += text
    if change == "missing_score": text = text.replace("Druggability Score", "Unknown")
    if change == "duplicate_score": text = text.replace("Pocket 2 :", "Score : 1\nPocket 2 :")
    if change == "nonfinite": text = text.replace("0.122", "nan", 1)
    if change == "bad_number": text = text.replace("Pocket 1 :", "Pocket 0 :")
    if change == "fractional_count": text = text.replace("Spheres : \t24", "Spheres : 24.5")
    if change == "missing_rank": text = text.replace("Pocket 2 :", "Pocket 3 :")
    with pytest.raises(PocketError):
        parse_info(text)


@pytest.mark.parametrize("change", ["missing_pqr", "extra_id", "count", "sphere_id", "radius", "coordinate",
                                    "duplicate_sphere", "truncated", "atom_mismatch", "mapping", "symlink"])
def test_malformed_geometry_or_mapping_rejected(reference: Path, change: str) -> None:
    """Cross-check descriptor, PQR, contacted atoms and residue provenance instead of guessing."""
    directory = reference / "receptor_out"
    pqr = directory / "pockets/pocket1_vert.pqr"
    info = directory / "receptor_info.txt"
    atoms = directory / "pockets/pocket1_atm.pdb"
    receptor = (reference / "contact-reference.pdb").read_text()
    mapping = reference_mapping(receptor)
    if change == "missing_pqr": pqr.unlink()
    if change == "extra_id": shutil.copyfile(pqr, pqr.with_name("pocket99_vert.pqr"))
    if change == "count": info.write_text(info.read_text().replace("Spheres : \t24", "Spheres : 23"))
    if change == "mapping": mapping = []
    if change == "atom_mismatch": atoms.write_text(atoms.read_text().replace(" ILE ", " THR "))
    if change == "symlink":
        pqr.unlink()
        pqr.symlink_to(FIXTURE / "receptor_out/pockets/pocket1_vert.pqr")
    if change in ("sphere_id", "radius", "coordinate", "duplicate_sphere", "truncated"):
        lines = pqr.read_text().splitlines()
        index = next(i for i, line in enumerate(lines) if line.startswith("ATOM"))
        if change == "sphere_id": lines[index] = lines[index][:22] + "   2" + lines[index][26:]
        if change == "radius": lines[index] = lines[index][:54] + " 0.00 -1.00"
        if change == "coordinate": lines[index] = lines[index][:30] + "     nan" + lines[index][38:]
        if change == "duplicate_sphere": lines.append(lines[index])
        if change == "truncated": lines[index] = lines[index][:40]
        pqr.write_text("\n".join(lines))
    with pytest.raises(PocketError):
        parse_pockets(directory, receptor, mapping)


def test_no_pocket_requires_complete_empty_output(reference: Path) -> None:
    """An empty summary alone is ambiguous; companion artifacts and absence of spheres matter."""
    directory = reference / "receptor_out"
    receptor = (reference / "contact-reference.pdb").read_text()
    mapping = reference_mapping(receptor)
    (directory / "receptor_info.txt").write_text("")
    shutil.rmtree(directory / "pockets")
    (directory / "pockets").mkdir()
    with pytest.raises(PocketError):
        parse_pockets(directory, receptor, mapping)
    (directory / "receptor_out.pdb").write_text(receptor)
    (directory / "receptor_pockets.pqr").write_text("HEADER empty\nTER\nEND\n")
    assert parse_pockets(directory, receptor, mapping) == []
    (directory / "receptor_pockets.pqr").write_text("ATOM      1\n")
    with pytest.raises(PocketError):
        parse_pockets(directory, receptor, mapping)


@pytest.mark.parametrize("variant,amino_acid", [("WT", "T"), ("T315I", "I")])
def test_variant_to_explicit_selection(structures: dict[str, Path], executable: str, tmp_path: Path,
                                     variant: str, amino_acid: str) -> None:
    """Preserve mapping/classification and select rank two explicitly through actual subprocess calls."""
    result = pockets.run_pockets(structures[variant], tmp_path / "run with spaces ; literal", executable=executable,
                                 allow_illustrative=True, release_label="test double")
    assert result.status == "succeeded" and result.count == 2
    data = pockets.read_json(result.manifest_path)
    assert data["selection"] is None and data["docking_ready"] is False
    assert data["classification"] == "illustrative"
    assert data["backend"]["reported_version"] == "4.0"
    assert data["backend"]["declared_release_verified"] is False
    assert data["backend"]["executable_sha256"] == sequences.sha256(Path(executable).read_bytes())
    pockets.verified_files(result.manifest_path.parent, data["artifacts"])
    records = pockets.read_json(result.pockets_path)["pockets"]
    assert records[0]["mutation_context"]["observed_amino_acid"] == amino_acid
    assert records[0]["mutation_context"]["contacted"] is True
    assert records[1]["mutation_context"]["contacted"] is False
    assert records[0]["residues"][0]["source_position"] == 315
    assert records[0]["residues"][0]["structure_residue"]["number"] == 74
    assert records[0]["descriptors"]["Example new descriptor"] == {"value": 2.5, "unit": None}
    selection_path = pockets.select_pocket(result.manifest_path, tmp_path / "selection", pocket_id="pocket2",
                                           rationale="Second pocket selected for an illustrative box contract test.", padding=3)
    selection = pockets.read_json(selection_path)
    assert selection["pocket_id"] == "pocket2" and selection["selection_method"] == "explicit"
    assert selection["box"]["size"] == [17, 17, 17]
    assert selection["receptor_sha256"] == data["receptor_sha256"]
    assert selection["classification"] == "illustrative" and selection["docking_ready"] is False
    pockets.verified_files(selection_path.parent, selection["artifacts"])
    selected_pocket = pockets.read_json(selection_path.parent / "pocket.json")
    assert all((selection_path.parent / name).is_file() for name in selected_pocket["artifacts"].values())
    with pytest.raises(FileExistsError):
        pockets.select_pocket(result.manifest_path, selection_path.parent, pocket_id="pocket1", rationale="Cannot overwrite")


@pytest.mark.parametrize("mode,status", [("missing", "failed"), ("failed", "failed"), ("version", "failed"),
                                        ("internal", "failed"), ("no_output", "failed"), ("malformed", "failed"),
                                        ("timeout", "timed_out"), ("empty", "no_pockets")])
def test_external_failures_and_empty_receipts(structures: dict[str, Path], executable: str, tmp_path: Path,
                                            monkeypatch: pytest.MonkeyPatch, mode: str, status: str) -> None:
    """Exercise absent/failed tools, misleading exit zero, deadline expiry and real no-pocket shape."""
    monkeypatch.setenv("FPOCKET_STUB_MODE", mode)
    result = pockets.run_pockets(structures["WT"], tmp_path / "run", allow_illustrative=True,
                                 executable=str(tmp_path / "missing") if mode == "missing" else executable,
                                 timeout=.3 if mode == "timeout" else 10)
    assert result.status == status and result.count == 0
    data = pockets.read_json(result.manifest_path)
    assert data["selection"] is None
    assert pockets.read_json(result.manifest_path.parent / "status.json")["status"] == status
    assert "raw/backend.json" in data["artifacts"]
    pockets.verified_files(result.manifest_path.parent, data["artifacts"])
    if mode == "empty":
        assert pockets.read_json(result.pockets_path)["pockets"] == []
        assert data["error"] is None
    else:
        assert result.pockets_path is None and data["error"]
    with pytest.raises(PocketError):
        pockets.select_pocket(result.manifest_path, tmp_path / "selection", pocket_id="pocket1", rationale="No usable pockets")


@pytest.mark.parametrize("change", ["hash", "mapping", "classification", "sequence", "path", "failed"])
def test_invalid_structure_rejected_before_launch(structures: dict[str, Path], executable: str, tmp_path: Path, change: str) -> None:
    """Do not accept tampered mappings, changed structures or a failed prediction as fpocket input."""
    path = structures["WT"]
    data = pockets.read_json(path)
    if change == "hash": (path.parent / "raw/structure.pdb").write_text("edited")
    if change == "mapping":
        validation = pockets.read_json(path.parent / "validation.json")
        validation["residue_mapping"][73]["source_position"] = 334
        pockets.write_json(path.parent / "validation.json", validation)
        data["artifacts"]["validation.json"] = pockets.receipt((path.parent / "validation.json").read_bytes())
    if change == "classification": data["classification"] = "computed_prediction"
    if change == "sequence": data["input"]["domain_start"] = 229
    if change == "path": data["artifacts"]["../outside"] = {"sha256": "x", "bytes": 0}
    if change == "failed": data["status"] = "failed"
    pockets.write_json(path, data)
    with pytest.raises((ValueError, OSError)):
        pockets.run_pockets(path, tmp_path / "run", executable=executable, allow_illustrative=True)
    assert not (tmp_path / "run").exists()


def test_fixture_requires_explicit_opt_in(structures: dict[str, Path], executable: str, tmp_path: Path) -> None:
    """An illustrative structure cannot accidentally be treated as a scientific input."""
    with pytest.raises(PocketError, match="Illustrative"):
        pockets.run_pockets(structures["WT"], tmp_path / "run", executable=executable)
    assert not (tmp_path / "run").exists()


def test_plddt_is_not_thermal_bfactor() -> None:
    """Clear confidence for fpocket without modifying coordinates, residue identities or original data."""
    source = folding._read(ROOT / "tests/fixtures/fpocket/contact-reference.pdb").decode("ascii")
    changed = pockets.prepare_receptor(source)
    assert pdb_atoms(changed) == pdb_atoms(source)
    assert all(float(line[60:66]) == 0 for line in changed.splitlines() if line.startswith("ATOM"))
    assert changed != source


def test_predicted_confidence_survives_in_mapping(structures: dict[str, Path], executable: str, tmp_path: Path) -> None:
    """Use a simulated real-backend receipt to prove pLDDT stays in mapping, never native B-factors."""
    path = structures["WT"]
    data = pockets.read_json(path)
    config = folding.PredictionConfig(backend="esmfold", device="cpu")
    runtime = {"backend": "esmfold", "simulated_receipt_for_testing": True}
    raw = path.parent / "raw"
    pdb = "\n".join(line[:60] + " 87.25" + line[66:] if line.startswith("ATOM") else line
                     for line in (raw / "structure.pdb").read_text().splitlines()) + "\n"
    (raw / "structure.pdb").write_text(pdb)
    backend = data["backend"]
    backend.update(classification="computed_prediction", configuration=folding.asdict(config), environment=runtime,
                   model={"id": folding.MODEL_ID, "revision": folding.MODEL_REVISION, "resolved_config_revision": folding.MODEL_REVISION})
    pockets.write_json(raw / "backend.json", backend)
    pockets.write_json(raw / "confidence.json", {"kind": "predicted_lddt", "raw_scale": [0, 1], "pdb_scale": [0, 100],
                                                "raw_ca_values": [0.8725] * 252})
    sequence = folding.load_sequence_input(path.parent / "inputs/ABL1_WT.fasta")
    pockets.write_json(path.parent / "validation.json", validate_structure(pdb, sequence.sequence, sequence.start, predicted=True))
    data.update(configuration=folding.asdict(config), classification="computed_prediction", backend=backend,
                structure_prediction_performed=True, inference_executed_this_run=True)
    data["identity"]["environment"] = runtime
    for name in ("raw/structure.pdb", "raw/confidence.json", "raw/backend.json", "validation.json"):
        data["artifacts"][name] = pockets.receipt((path.parent / name).read_bytes())
    pockets.write_json(path, data)
    result = pockets.run_pockets(path, tmp_path / "run", executable=executable)
    assert result.status == "succeeded"
    records = pockets.read_json(result.pockets_path)["pockets"]
    assert records[0]["residues"][0]["plddt"] == 87.25
    receptor = (result.manifest_path.parent / "raw/receptor.pdb").read_text()
    assert all(float(line[60:66]) == 0 for line in receptor.splitlines() if line.startswith("ATOM"))
    assert (result.manifest_path.parent / "inputs/structure-run/raw/structure.pdb").read_text() == pdb


def test_custom_domain_mapping(executable: str, tmp_path: Path) -> None:
    """Carry a nondefault domain offset through fpocket without assuming mutation is residue 74."""
    record = sequences.load_source(ROOT / "tests/fixtures/abl1/P00519.cache.json", offline=True)
    sequences.export_sequences(record, tmp_path / "inputs", start=229, end=511)
    folded = folding.run_prediction(tmp_path / "inputs/ABL1_T315I.fasta", tmp_path / "fold",
                                    config=folding.PredictionConfig(backend="fixture", device="cpu"), cache=None)
    result = pockets.run_pockets(folded.manifest_path, tmp_path / "run", executable=executable, allow_illustrative=True)
    assert result.status == "succeeded"
    first = pockets.read_json(result.pockets_path)["pockets"][0]
    assert first["residues"][0]["source_position"] == 302
    assert first["mutation_context"]["structure_residue"]["number"] == 87
    assert first["mutation_context"]["observed_amino_acid"] == "I"


@pytest.mark.parametrize("change", ["id", "rationale", "negative_padding", "nan_padding", "center_only", "negative_size", "tampered_json"])
def test_bad_selection_rejected(structures: dict[str, Path], executable: str, tmp_path: Path, change: str) -> None:
    """Reject ambiguous choices and invalid boxes, even when edited pocket JSON has a fresh hash."""
    result = pockets.run_pockets(structures["WT"], tmp_path / "run", executable=executable, allow_illustrative=True)
    kwargs: dict[str, Any] = {"pocket_id": "pocket1", "rationale": "test selection"}
    if change == "id": kwargs["pocket_id"] = "pocket99"
    if change == "rationale": kwargs["rationale"] = " "
    if change == "negative_padding": kwargs["padding"] = -1
    if change == "nan_padding": kwargs["padding"] = float("nan")
    if change == "center_only": kwargs["center"] = [0, 0, 0]
    if change == "negative_size": kwargs.update(center=[0, 0, 0], size=[-1, 1, 1])
    if change == "tampered_json":
        data = pockets.read_json(result.pockets_path)
        data["pockets"][0]["geometry"]["sphere_bounds"]["min"][0] = -999
        pockets.write_json(result.pockets_path, data)
        manifest = pockets.read_json(result.manifest_path)
        manifest["artifacts"]["pockets.json"] = pockets.receipt(result.pockets_path.read_bytes())
        pockets.write_json(result.manifest_path, manifest)
    with pytest.raises(PocketError):
        pockets.select_pocket(result.manifest_path, tmp_path / "selection", **kwargs)
    assert not (tmp_path / "selection").exists()


def test_explicit_box_override(structures: dict[str, Path], executable: str, tmp_path: Path) -> None:
    """Preserve the automatic proposal alongside an explicitly supplied center and dimensions."""
    result = pockets.run_pockets(structures["WT"], tmp_path / "run", executable=executable, allow_illustrative=True)
    path = pockets.select_pocket(result.manifest_path, tmp_path / "selection", pocket_id="pocket1", rationale="Reviewed custom box",
                                 center=[1, 2, 3], size=[20, 22, 24])
    data = pockets.read_json(path)
    assert data["box"]["center"] == [1, 2, 3] and data["box"]["size"] == [20, 22, 24]
    assert data["box"]["method"] == "explicit_override"
    assert data["automatic_box_proposal"]["method"] == "alpha_sphere_envelope_plus_padding"


@pytest.mark.parametrize("kwargs", [{"min_spheres": 0}, {"min_spheres": True}, {"min_alpha_radius": 7},
                                   {"max_alpha_radius": float("inf")}, {"clustering_distance": -1}])
def test_invalid_detection_settings(kwargs: dict[str, Any]) -> None:
    """Prevent invalid units/ranges and Python booleans from silently changing the native command."""
    with pytest.raises(PocketError):
        replace(pockets.PocketConfig(), **kwargs).arguments()


def test_cli_detection_selection_and_errors(structures: dict[str, Path], executable: str, tmp_path: Path) -> None:
    """Exercise installed-module command boundaries and required explicit selection arguments."""
    command = [sys.executable, "-m", "protein_workflow.pockets"]
    run = tmp_path / "cli-run"
    detected = subprocess.run([*command, "detect", "--structure-result", str(structures["T315I"]), "--output", str(run),
                               "--executable", executable, "--allow-illustrative"], capture_output=True, text=True, timeout=30)
    assert detected.returncode == 0, detected.stderr
    assert json.loads(detected.stdout)["pocket_count"] == 2
    selected = subprocess.run([*command, "select", "--result", str(run / "result.json"), "--output", str(tmp_path / "selection"),
                               "--pocket", "pocket2", "--rationale", "CLI contract test"], capture_output=True, text=True, timeout=30)
    assert selected.returncode == 0, selected.stderr
    assert json.loads(selected.stdout)["status"] == "proposal"
    missing = subprocess.run([*command, "select", "--result", str(run / "result.json"), "--output", str(tmp_path / "missing")],
                              capture_output=True, text=True, timeout=30)
    assert missing.returncode == 2 and "--pocket" in missing.stderr
