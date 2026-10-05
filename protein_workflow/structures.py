"""Validate the single-chain, input-numbered PDB output of the ESMFold adapter."""

from __future__ import annotations

import math
from typing import Any

ONE_TO_THREE = dict(zip("ARNDCQEGHILKMFPSTWYV", (
    "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE",
    "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL"), strict=True))
THREE_TO_ONE = {value: key for key, value in ONE_TO_THREE.items()}


def validate_structure(pdb: str, sequence: str, source_start: int, *, predicted: bool) -> dict[str, Any]:
    """Check sequence/mapping and finite backbone records; retain failures for review.

    This deliberately accepts only this backend's numbering: chain A, residue
    indices 1..L, no insertions/alternate locations or multiple models. It is not
    a general alignment tool, physical geometry validator or receptor preparation.
    """
    residues: dict[int, dict[str, Any]] = {}
    errors: list[str] = []
    unmapped: list[dict[str, Any]] = []
    serials: set[int] = set()
    last_residue = 0
    ended = False
    for number, line in enumerate(pdb.splitlines(), 1):
        tag = line[:6].strip()
        if tag in ("MODEL", "ENDMDL", "HETATM"):
            errors.append(f"Line {number}: unsupported {tag} record in single-chain prediction.")
        if tag == "END":
            ended = True
        if tag != "ATOM":
            continue
        try:
            if ended or len(line) < 66:
                raise ValueError("truncated atom or atom after END")
            serial, position = int(line[6:11]), int(line[22:26])
            atom, residue = line[12:16].strip(), line[17:20].strip()
            chain, insertion, alt = line[21], line[26], line[16]
            coordinates = [float(line[i:i + 8]) for i in (30, 38, 46)]
            occupancy, confidence = float(line[54:60]), float(line[60:66])
            if (not all(math.isfinite(v) for v in [*coordinates, occupancy, confidence])
                    or not 0 < occupancy <= 1 or not 0 <= confidence <= 100
                    or not atom or serial in serials or serial < 1):
                raise ValueError("invalid coordinates, occupancy, confidence or duplicate atom serial")
            serials.add(serial)
            if chain != "A" or insertion != " " or alt != " " or not 1 <= position <= len(sequence):
                unmapped.append({"line": number, "chain": chain, "residue_number": position,
                                 "insertion_code": insertion.strip(), "alternate_location": alt.strip()})
                continue
            if position < last_residue:
                raise ValueError("residue records are not in input order")
            last_residue = position
            row = residues.setdefault(position, {"residue": residue, "atoms": {}})
            if row["residue"] != residue or atom in row["atoms"]:
                raise ValueError("conflicting residue identity or duplicate atom")
            row["atoms"][atom] = confidence
        except ValueError as exc:
            errors.append(f"Line {number}: {exc}.")
    mapping: list[dict[str, Any]] = []
    missing: list[int] = []
    mismatches: list[dict[str, Any]] = []
    for index, expected in enumerate(sequence):
        position = index + 1
        row = residues.get(position)
        missing_atoms = sorted({"N", "CA", "C", "O"} - (set(row["atoms"]) if row else set()))
        observed = THREE_TO_ONE.get(row["residue"]) if row else None
        if row is None:
            missing.append(position)
        elif observed != expected:
            mismatches.append({"domain_position": position, "expected": expected,
                               "observed": row["residue"]})
        if row and missing_atoms:
            errors.append(f"Residue {position}: missing backbone atoms {', '.join(missing_atoms)}.")
        mapping.append({"source_position": source_start + index, "domain_position": position,
                        "domain_index": index, "expected_amino_acid": expected,
                        "structure_residue": {"chain": "A", "number": position, "insertion_code": ""} if row else None,
                        "observed_amino_acid": observed, "missing_backbone_atoms": missing_atoms,
                        "plddt": row["atoms"].get("CA") if predicted and row else None})
    confidence_values = [row["plddt"] for row in mapping if row["plddt"] is not None]
    return {"schema_version": 1, "valid": not (errors or missing or unmapped or mismatches),
            "coordinate_unit": "angstrom", "confidence_kind": "predicted_lddt" if predicted else "unavailable_fixture",
            "confidence_scale": [0, 100] if predicted else None,
            "confidence_summary": {"mean_ca_plddt": sum(confidence_values) / len(confidence_values) if confidence_values else None,
                                   "available_residues": len(confidence_values)},
            "errors": errors, "missing_domain_positions": missing, "unmapped_atoms": unmapped,
            "sequence_mismatches": mismatches, "residue_mapping": mapping,
            "physical_geometry_validated": False, "docking_preparation_performed": False}


def illustrative_pdb(sequence: str) -> str:
    """Create a labeled artificial backbone for artifact-flow tests, never a fold."""
    lines = ["REMARK 900 ILLUSTRATIVE FIXTURE - NOT AN ESMFOLD PREDICTION",
             "REMARK 900 ARTIFICIAL BACKBONE; NO SIDE CHAINS OR SCIENTIFIC CONFIDENCE"]
    serial = 0
    for position, amino_acid in enumerate(sequence, 1):
        for atom, offset in (("N", 0.0), ("CA", 1.3), ("C", 2.6), ("O", 3.0)):
            serial += 1
            lines.append(f"ATOM  {serial:5d} {atom:>4} {ONE_TO_THREE[amino_acid]:3s} A{position:4d}    "
                         f"{position * 3.8 + offset:8.3f}{0.0:8.3f}{0.0:8.3f}{1.0:6.2f}{0.0:6.2f}          {atom[0]:>2}")
    return "\n".join([*lines, "TER", "END", ""])
