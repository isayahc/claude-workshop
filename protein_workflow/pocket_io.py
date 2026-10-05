"""Parse fpocket 4.x cavities without inventing scores, residue mappings or boxes."""

from __future__ import annotations

import math
from pathlib import Path
import re
from typing import Any

from protein_workflow.structures import THREE_TO_ONE


class PocketError(ValueError):
    """An invalid pocket input, executable receipt, selection or output artifact."""


class PocketTimeout(PocketError):
    """The fpocket process group exceeded its deadline and was terminated."""


def read_bytes(path: Path) -> bytes:
    """Read a bounded ordinary output file without changing its bytes or line endings."""
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
        raise PocketError(f"Missing, linked or oversized artifact: {path}")
    return path.read_bytes()


def read_text(path: Path) -> str:
    """Decode a bounded ASCII PDB/PQR/descriptor artifact without altering line endings."""
    return read_bytes(path).decode("ascii")


def parse_info(text: str) -> dict[int, dict[str, float]]:
    """Preserve every descriptor label; require finite scores and an integral sphere count."""
    pockets: dict[int, dict[str, float]] = {}
    current: dict[str, float] | None = None
    if text.strip().lower() == "no pockets found":
        return pockets
    for line in text.splitlines():
        if not line.strip():
            continue
        header = re.fullmatch(r"\s*Pocket\s+(\d+)\s*:\s*", line)
        if header:
            number = int(header[1])
            if number < 1 or number in pockets:
                raise PocketError("Duplicate or invalid pocket identifier.")
            current = pockets[number] = {}
            continue
        if current is None or ":" not in line:
            raise PocketError(f"Malformed fpocket descriptor line: {line!r}")
        label, raw = (part.strip() for part in line.split(":", 1))
        try:
            value = float(raw)
        except ValueError as exc:
            raise PocketError(f"Nonnumeric descriptor: {label}") from exc
        if not label or label in current or not math.isfinite(value):
            raise PocketError(f"Duplicate or nonfinite descriptor: {label}")
        current[label] = value
    if set(pockets) != set(range(1, len(pockets) + 1)):
        raise PocketError("Pocket ranks must be contiguous and one-based (fpocket 4.x).")
    for descriptors in pockets.values():
        if not {"Score", "Druggability Score", "Number of Alpha Spheres"} <= descriptors.keys():
            raise PocketError("Pocket is missing required scores or sphere count.")
        count = descriptors["Number of Alpha Spheres"]
        if count < 1 or not count.is_integer():
            raise PocketError("Alpha-sphere count must be a positive integer.")
    return pockets


def pdb_atoms(text: str) -> dict[tuple[str, int, str, str], dict[str, Any]]:
    """Index PDB ATOM records by chain, residue, insertion and atom name, keeping coordinates."""
    atoms: dict[tuple[str, int, str, str], dict[str, Any]] = {}
    for line in text.splitlines():
        if line[:6].strip() != "ATOM":
            continue
        try:
            chain, number, insertion = line[21].strip(), int(line[22:26]), line[26].strip()
            name, residue = line[12:16].strip(), line[17:20].strip()
            xyz = [float(line[i:i + 8]) for i in (30, 38, 46)]
            key = (chain, number, insertion, name)
            if (len(line) < 54 or line[16] != " " or key in atoms or not name
                    or not all(math.isfinite(x) for x in xyz)):
                raise ValueError("invalid or ambiguous atom")
            atoms[key] = {"residue_name": residue, "coordinates": xyz}
        except (ValueError, IndexError) as exc:
            raise PocketError(f"Malformed pocket/receptor PDB atom: {line!r}") from exc
    if not atoms:
        raise PocketError("Pocket/receptor PDB has no ATOM records.")
    return atoms


def parse_spheres(text: str, pocket_number: int) -> list[dict[str, Any]]:
    """Read fpocket fixed-column PQR centers and trailing charge/radius, in angstroms."""
    spheres: list[dict[str, Any]] = []
    serials: set[int] = set()
    for line in text.splitlines():
        if line[:6].strip() not in ("ATOM", "HETATM"):
            if line.strip() and line[:6].strip() not in ("HEADER", "REMARK", "TER", "END"):
                raise PocketError("Unexpected record in alpha-sphere PQR.")
            continue
        try:
            serial, number = int(line[6:11]), int(line[22:26])
            xyz = [float(line[i:i + 8]) for i in (30, 38, 46)]
            charge, radius = (float(value) for value in line[54:].split())
            if (line[17:20] != "STP" or number != pocket_number or serial < 1 or serial in serials
                    or not all(math.isfinite(v) for v in [*xyz, charge, radius]) or radius <= 0):
                raise ValueError("invalid sphere identity, coordinates or radius")
            serials.add(serial)
            spheres.append({"serial": serial, "center": xyz, "radius": radius,
                            "fpocket_atom_type": line[12:16].strip()})
        except (ValueError, IndexError) as exc:
            raise PocketError(f"Malformed alpha sphere: {line!r}") from exc
    if not spheres:
        raise PocketError("Pocket has no alpha spheres.")
    return spheres


def sphere_geometry(spheres: list[dict[str, Any]]) -> dict[str, Any]:
    """Describe both center bounds and the full sphere envelope, with explicit units."""
    return {"coordinate_unit": "angstrom", "alpha_spheres": spheres,
            "centroid": [sum(s["center"][i] for s in spheres) / len(spheres) for i in range(3)],
            "center_bounds": {"min": [min(s["center"][i] for s in spheres) for i in range(3)],
                              "max": [max(s["center"][i] for s in spheres) for i in range(3)]},
            "sphere_bounds": {"min": [min(s["center"][i] - s["radius"] for s in spheres) for i in range(3)],
                              "max": [max(s["center"][i] + s["radius"] for s in spheres) for i in range(3)]}}


def descriptor_unit(label: str) -> str | None:
    """Attach only known physical units; retain unknown descriptor units as unavailable."""
    if label in ("Total SASA", "Polar SASA", "Apolar SASA"):
        return "angstrom_squared"
    if label == "Volume":
        return "angstrom_cubed"
    if label in ("Mean alpha sphere radius", "Cent. of mass - Alpha Sphere max dist"):
        return "angstrom"
    if label == "Number of Alpha Spheres":
        return "count"
    return None


def parse_pockets(directory: Path, receptor: str, mapping: list[dict[str, Any]],
                  *, stem: str = "receptor") -> list[dict[str, Any]]:
    """Join info/PQR/PDB by rank and verify every contacted atom against its receptor.

    ``mapping`` uses the #5 validation rows. A general reference smoke test can
    supply rows with null source/domain positions; no source numbering is inferred.
    Artifact paths are relative to ``directory``. Empty info is accepted only with
    complete empty output companions; the caller also checks process/log success.
    """
    descriptors = parse_info(read_text(directory / f"{stem}_info.txt"))
    pocket_dir = directory / "pockets"
    if not pocket_dir.is_dir() or pocket_dir.is_symlink():
        raise PocketError("Missing pocket output directory.")
    expected = {f"pocket{i}_{suffix}" for i in descriptors for suffix in ("atm.pdb", "vert.pqr")}
    actual = {p.name for p in pocket_dir.iterdir() if re.fullmatch(r"pocket\d+_(atm\.pdb|vert\.pqr)", p.name)}
    if expected != actual:
        raise PocketError("Pocket info/PDB/PQR identifiers disagree or files are missing.")
    if not descriptors:
        if pdb_atoms(read_text(directory / f"{stem}_out.pdb")) != pdb_atoms(receptor):
            raise PocketError("Empty-result receptor disagrees with the input coordinates.")
        combined = read_text(directory / f"{stem}_pockets.pqr")
        if any(line[:6].strip() in ("ATOM", "HETATM") for line in combined.splitlines()):
            raise PocketError("Empty pocket summary conflicts with alpha-sphere output.")
        return []
    atoms = pdb_atoms(receptor)
    by_residue: dict[tuple[str, int, str], dict[str, Any]] = {}
    for row in mapping:
        residue = row["structure_residue"]
        if residue is None:
            continue
        key = (residue["chain"], residue["number"], residue["insertion_code"])
        if key in by_residue:
            raise PocketError("Ambiguous input residue mapping.")
        by_residue[key] = row
    pockets = []
    for number, values in sorted(descriptors.items()):
        atom_path, sphere_path = f"pockets/pocket{number}_atm.pdb", f"pockets/pocket{number}_vert.pqr"
        contacted = pdb_atoms(read_text(directory / atom_path))
        residues: dict[tuple[str, int, str], dict[str, Any]] = {}
        for key, atom in contacted.items():
            if key not in atoms or atom != atoms[key]:
                raise PocketError("Pocket atom identity/coordinates disagree with the input receptor.")
            row = by_residue.get(key[:3])
            if row is None or THREE_TO_ONE.get(atom["residue_name"]) != row["observed_amino_acid"]:
                raise PocketError("Pocket residue is missing from or disagrees with the source mapping.")
            residues[key[:3]] = row
        spheres = parse_spheres(read_text(directory / sphere_path), number)
        if len(spheres) != values["Number of Alpha Spheres"]:
            raise PocketError("Alpha-sphere count disagrees with the pocket descriptor.")
        pockets.append({"id": f"pocket{number}", "rank": number,
                        "scores": {"fpocket": values["Score"], "druggability": values["Druggability Score"]},
                        "descriptors": {label: {"value": value, "unit": descriptor_unit(label)}
                                        for label, value in values.items()},
                        "residues": [residues[key] for key in sorted(residues)],
                        "contacted_atom_count": len(contacted), "geometry": sphere_geometry(spheres),
                        "artifacts": {"contact_atoms": atom_path, "alpha_spheres": sphere_path}})
    return pockets


def propose_box(pocket: dict[str, Any], padding: float = 4.0) -> dict[str, Any]:
    """Propose an axis-aligned sphere-envelope box padded on each face, never select a pocket."""
    if type(padding) not in (int, float) or not math.isfinite(padding) or padding < 0:
        raise PocketError("Box padding must be finite and nonnegative, in angstroms.")
    bounds = pocket["geometry"]["sphere_bounds"]
    return {"coordinate_unit": "angstrom", "axes": ["x", "y", "z"],
            "center": [(low + high) / 2 for low, high in zip(bounds["min"], bounds["max"], strict=True)],
            "size": [high - low + 2 * padding for low, high in zip(bounds["min"], bounds["max"], strict=True)],
            "padding_per_face": padding, "method": "alpha_sphere_envelope_plus_padding",
            "status": "proposal", "binding_site_validated": False}
