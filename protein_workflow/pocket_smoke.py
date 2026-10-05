"""Verify a real fpocket build on its reference protein, without claiming an ABL1 prediction."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
from typing import Any

from protein_workflow.pocket_io import parse_pockets, pdb_atoms, propose_box
from protein_workflow.pockets import PocketConfig, execute_fpocket, receipt, write_json
from protein_workflow.sequences import sha256
from protein_workflow.structures import THREE_TO_ONE

FPOCKET_COMMIT = "4bb0d8447f62fee77e2c3c29f54b5fcaf5e2c066"


def verify(fpocket_root: Path, output: Path) -> Path:
    """Run real positive and no-pocket cases, saving complete raw artifacts and a verification receipt."""
    revision = subprocess.run(["git", "-C", str(fpocket_root), "rev-parse", "HEAD"], capture_output=True,
                               text=True, check=True, timeout=30).stdout.strip()
    if revision != FPOCKET_COMMIT:
        raise ValueError(f"Reference verification requires fpocket source {FPOCKET_COMMIT}, found {revision}.")
    output.mkdir(parents=True, exist_ok=False)
    source = (fpocket_root / "data/sample/1UYD.pdb").read_bytes()
    (output / "1UYD.source.pdb").write_bytes(source)
    # Explicit single-conformer ATOM-only reference input; experimental B-factors
    # remain experimental here. This is not the #5 ABL1 prediction input contract.
    lines = [line[:16] + " " + line[17:] for line in source.decode("ascii").splitlines()
             if line.startswith("ATOM  ") and line[16] in (" ", "A")]
    receptor = "\n".join([*lines, "TER", "END", ""])
    atoms = pdb_atoms(receptor)
    residues: dict[tuple[str, int, str], dict[str, Any]] = {}
    for key, atom in atoms.items():
        residues[key[:3]] = {"source_position": None, "domain_position": None, "domain_index": None,
                             "structure_residue": dict(zip(("chain", "number", "insertion_code"), key[:3], strict=True)),
                             "observed_amino_acid": THREE_TO_ONE[atom["residue_name"]], "plddt": None}
    results: dict[str, Any] = {}
    for case, config in (("positive", PocketConfig()), ("empty", PocketConfig(min_spheres=1_000_000))):
        raw = output / case
        backend = execute_fpocket(receptor, raw, executable=str(fpocket_root / "bin/fpocket"), config=config,
                                  release_label=f"4.2.3 source {FPOCKET_COMMIT}")
        pockets = [] if backend["no_output_no_pockets"] else parse_pockets(raw / "receptor_out", receptor, list(residues.values()))
        if (case == "positive" and not pockets) or (case == "empty" and pockets):
            raise RuntimeError(f"Unexpected real fpocket outcome for {case}: {len(pockets)} pockets")
        for pocket in pockets:
            box = propose_box(pocket)
            for sphere in pocket["geometry"]["alpha_spheres"]:
                if any(abs(sphere["center"][axis] - box["center"][axis]) + sphere["radius"] > box["size"][axis] / 2
                       for axis in range(3)):
                    raise RuntimeError("Proposed box does not contain its alpha spheres")
        write_json(raw / "parsed-pockets.json", {"pockets": pockets, "coordinate_unit": "angstrom"})
        results[case] = {"pocket_count": len(pockets), "backend": backend}
    summary = {"schema_version": 1, "status": "verified", "classification": "experimental_reference_tool_smoke",
               "fpocket_source_commit": revision,
               "reference": "fpocket data/sample/1UYD.pdb", "source_input_sha256": sha256(source),
               "normalization": "ATOM only; keep blank/A alternate locations, replace A with blank; preserve experimental B-factors",
               "abl1_prediction_verified": False, "reference_source_mapping_available": False,
               "cases": results, "artifacts": {str(p.relative_to(output)): receipt(p.read_bytes())
                                                for p in output.rglob("*") if p.is_file()}}
    write_json(output / "verification.json", summary)
    return output / "verification.json"


def main(argv: list[str] | None = None) -> int:
    """Run the reproducible reference verification from a checked-out and compiled fpocket tree."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fpocket-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    print(verify(args.fpocket_root.resolve(), args.output.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
