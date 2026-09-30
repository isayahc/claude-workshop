"""Validated CUBE grids, transition tables, and illustrative sample data."""
from dataclasses import dataclass
from io import StringIO
import csv
import tempfile
from pathlib import Path
import numpy as np
from numpy.typing import NDArray

BOHR = 0.529177210903
CM_PER_EV = 8065.543937
HC = 1239.841984

@dataclass
class Grid:
    """Scalar orbital field with coordinates expressed in angstroms."""
    title: str
    origin: NDArray[np.float64]
    axes: NDArray[np.float64]
    atoms: NDArray[np.float64]
    values: NDArray[np.float64]


def read_cube(text: str, title: str = "Orbital") -> Grid:
    """Read one scalar CUBE field, including skew axes and single-MO records."""
    try:
        lines = text.replace("D", "E").replace("d", "e").splitlines()
        header = lines[2].split()
        nat = int(header[0])
        if abs(nat) > 10000:
            raise ValueError("Too many atoms (maximum 10,000).")
        if len(header) > 4 and int(header[4]) != 1:
            raise ValueError("Export one orbital per CUBE file; multiple fields are unsupported.")
        origin = np.array(header[1:4], dtype=float)
        counts = np.array([int(lines[i].split()[0]) for i in range(3, 6)])
        shape = np.abs(counts)
        if np.any(shape < 2) or np.prod(shape.astype(object)) > 4_000_000:
            raise ValueError("Grid dimensions must be >=2 and total at most 4 million voxels.")
        if not (np.all(counts > 0) or np.all(counts < 0)):
            raise ValueError("Mixed coordinate unit signs are unsupported.")
        factor = BOHR if counts[0] > 0 else 1.0
        axes = np.array([lines[i].split()[1:4] for i in range(3, 6)], dtype=float) * factor
        atoms = np.array([lines[i].split()[:5] for i in range(6, 6 + abs(nat))], dtype=float).reshape(-1, 5)
        atoms[:, 2:5] *= factor
        tokens = " ".join(lines[6 + abs(nat):]).split()
        if nat < 0:
            if int(tokens[0]) != 1:
                raise ValueError("Export one orbital per CUBE file; multiple orbitals are unsupported.")
            tokens = tokens[2:]
        if len(tokens) != int(np.prod(shape)):
            raise ValueError("CUBE scalar count does not match its grid dimensions.")
        values = np.asarray(tokens, dtype=float).reshape(tuple(shape))
        if not all(np.isfinite(a).all() for a in (origin, axes, atoms, values)):
            raise ValueError("CUBE contains non-finite numbers.")
        if origin.shape != (3,) or axes.shape != (3, 3) or abs(np.linalg.det(axes)) < 1e-12:
            raise ValueError("CUBE coordinate axes must form a non-degenerate 3D grid.")
        return Grid(title, origin * factor, axes, atoms, values)
    except (IndexError, TypeError, OverflowError) as exc:
        raise ValueError("Incomplete or malformed CUBE header/data.") from exc


def validate_transitions(energies: NDArray, strengths: NDArray) -> NDArray:
    """Return finite, positive-energy transitions with nonnegative oscillator strengths."""
    if len(energies) != len(strengths) or not len(energies):
        raise ValueError("No matching excitation energies and oscillator strengths found.")
    table = np.column_stack((energies, strengths)).astype(float)
    if not np.isfinite(table).all() or np.any(table[:, 0] <= 0) or np.any(table[:, 1] < 0):
        raise ValueError("Energies must be positive; strengths nonnegative; all values finite.")
    return table


def read_transitions(text: str, filename: str) -> NDArray:
    """Read energy_ev/oscillator_strength CSV or cclib-supported ORCA output."""
    if filename.lower().endswith(".csv"):
        rows = list(csv.DictReader(StringIO(text)))
        try:
            return validate_transitions(np.array([float(r["energy_ev"]) for r in rows]),
                                        np.array([float(r["oscillator_strength"]) for r in rows]))
        except (KeyError, TypeError) as exc:
            raise ValueError("CSV needs energy_ev and oscillator_strength columns.") from exc
    import cclib
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "calculation.out"
        path.write_text(text)
        try:
            data = cclib.io.ccread(str(path))
        except Exception as exc:
            raise ValueError("Could not parse this calculation output. Try the CSV format.") from exc
    if data is None or not hasattr(data, "etenergies") or not hasattr(data, "etoscs"):
        raise ValueError("Output has no supported excitation/oscillator-strength table. Try CSV.")
    return validate_transitions(np.asarray(data.etenergies) / CM_PER_EV, np.asarray(data.etoscs))


def broaden(table: NDArray, fwhm: float) -> tuple[NDArray, NDArray]:
    """Area-normalized Gaussian broadening in energy space (oscillator strength/eV)."""
    if not np.isfinite(fwhm) or fwhm <= 0:
        raise ValueError("FWHM must be positive and finite.")
    sigma = fwhm / np.sqrt(8 * np.log(2))
    x = np.linspace(max(0.01, table[:, 0].min() - 4 * fwhm), table[:, 0].max() + 4 * fwhm, 1600)
    y = np.zeros_like(x)
    for energy, strength in table:
        y += strength * np.exp(-0.5 * ((x - energy) / sigma) ** 2) / (sigma * np.sqrt(2 * np.pi))
    return x, y


def demo_grid(phase: int = 0) -> Grid:
    """Build an illustrative benzene-like pi field, not a quantum-chemistry calculation."""
    size = 52
    origin = np.array([-4., -4., -3.])
    axes = np.diag([8 / (size - 1), 8 / (size - 1), 6 / (size - 1)])
    xyz = np.moveaxis(np.indices((size,) * 3), 0, -1) @ axes + origin
    atoms, field = [], np.zeros((size,) * 3)
    for i in range(6):
        angle = i * np.pi / 3
        center = np.array([1.4 * np.cos(angle), 1.4 * np.sin(angle), 0.])
        atoms.extend([[6, 0, *center], [1, 0, *(center * (2.48 / 1.4))]])
        delta = xyz - center
        coefficient = np.cos((1 + phase) * angle + 0.3)
        field += coefficient * delta[..., 2] * np.exp(-np.sum(delta ** 2, axis=-1) * 1.7)
    return Grid("Illustrative π field", origin, axes, np.array(atoms), field)
