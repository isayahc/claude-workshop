"""Agent-independent Orbital Studio tools over local MCP stdio."""
import argparse
from contextlib import redirect_stdout
from functools import wraps
from io import StringIO
from pathlib import Path
import sys
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
import numpy as np
from pydantic import Field

from orbital_viewer.data import HC, broaden, read_cube, read_transitions
from orbital_viewer.mcp_files import FileAccessError, LocalFiles
from orbital_viewer.mcp_models import CubeInfo, Export, Spectrum, Transition, TransitionInfo
from orbital_viewer.plots import orbital_figure, spectrum_figure

MAX_TRANSITIONS = 10_000
CUBE_CAVEATS = [
    "Signed wavefunction amplitude: colors indicate phase, not charge or probability.",
    "Amplitude units are inherited from the source calculation; coordinates are in angstroms.",
    "Bond connectivity is inferred from distances, not bond order. No NTO pairing or alignment is inferred.",
]
SPECTRUM_CAVEATS = [
    "Area-normalized Gaussian broadening is in energy space with FWHM in eV.",
    "Wavelength is hc/E; the envelope remains oscillator strength/eV, not a density per nm or calibrated absorbance.",
    "The fixed 1,600-point positive-energy grid can truncate near-zero tails or undersample narrow, widely separated lines.",
    "Oscillator strengths do not determine NTO weights. ORCA compatibility depends on cclib; CSV is the fallback.",
]
FileName = Annotated[str, Field(min_length=1, max_length=1024, description="UTF-8 input file relative to --data-dir; use / separators.")]
Fwhm = Annotated[float, Field(gt=0, le=100, allow_inf_nan=False, description="Gaussian full width at half maximum in eV (at most 100).")]
Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]
Opacity = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


def safe_tool(function):
    """Keep third-party output off protocol stdout and internal errors off the wire."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            with redirect_stdout(sys.stderr):
                return function(*args, **kwargs)
        except ToolError:
            raise
        except FileAccessError as exc:
            raise ToolError(str(exc)) from None
        except FloatingPointError:
            raise ToolError("Spectrum is outside the supported numeric range; check energies and FWHM in eV.") from None
        except Exception:
            raise ToolError("Unable to process this data. Check the documented format and limits; try a smaller file or CSV transitions.") from None
    return wrapped


def create_server(data_dir: Path, output_dir: Path | None = None) -> FastMCP:
    files = LocalFiles(data_dir, output_dir)
    server = FastMCP("Orbital Studio", instructions=(
        "Inspect local scalar CUBE and transition files relative to the configured data directory. "
        "Exports are new files in the configured output directory. Preserve returned units and caveats. "
        "No quantum-chemistry calculations or NTO pairing are performed."
    ))
    read_only = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
    writes_export = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)

    def load_cube(filename):
        text = files.read_text(filename, {".cube", ".cub"})
        try:
            # Never use untrusted CUBE comments as executable HTML labels.
            return read_cube(text, "Orbital")
        except ValueError:
            raise ToolError("Invalid scalar CUBE. Check finite values, complete headers/data, consistent unit signs, nondegenerate axes, one field, and the 4 million voxel / 10,000 atom limits.") from None

    def load_transitions(filename):
        text = files.read_text(filename, {".csv", ".out", ".log"})
        try:
            table = read_transitions(text, filename)
        except ValueError:
            raise ToolError("Invalid transitions. CSV requires energy_ev and oscillator_strength columns, positive energies, nonnegative strengths, and finite values. For unsupported ORCA output, export CSV.") from None
        if len(table) > MAX_TRANSITIONS:
            raise ToolError("At most 10,000 transitions are supported per call.")
        return table

    def spectrum_data(table, fwhm_ev):
        with np.errstate(over="raise", divide="raise", invalid="raise"):
            energy, intensity = broaden(table, fwhm_ev)
            wavelength = HC / energy
            area = float(np.trapezoid(intensity, energy))
            total = float(table[:, 1].sum())
        if (not all(np.isfinite(a).all() for a in (energy, wavelength, intensity))
                or not np.all(np.diff(energy) > 0)):
            raise ToolError("Spectrum is outside the supported numeric range; check energies and FWHM in eV.")
        caveats = list(SPECTRUM_CAVEATS)
        if energy[1] - energy[0] > fwhm_ev / 5:
            caveats.append("Sampling warning: fewer than five samples per FWHM; restrict the energy range or increase FWHM before interpreting peaks or areas.")
        return Spectrum(transition_count=len(table), fwhm_ev=fwhm_ev,
                        energy_ev=energy.tolist(), wavelength_nm=wavelength.tolist(),
                        intensity_f_per_ev=intensity.tolist(), integrated_oscillator_strength=area,
                        total_oscillator_strength=total, caveats=caveats)

    def save(content, suffix, media_type, caveats, **metadata):
        path, size = files.export(content, suffix)
        return Export(filename=path.name, uri=path.as_uri(), media_type=media_type,
                      size_bytes=size, caveats=caveats, **metadata)

    @server.tool(annotations=read_only)
    @safe_tool
    def inspect_cube(filename: FileName) -> CubeInfo:
        """Validate a scalar CUBE and report dimensions, affine grid axes, atoms, and amplitude range."""
        grid = load_cube(filename)
        return CubeInfo(shape=grid.values.shape, voxel_count=grid.values.size, atom_count=len(grid.atoms),
                        origin=tuple(grid.origin), axes=tuple(tuple(row) for row in grid.axes),
                        value_min=float(grid.values.min()), value_max=float(grid.values.max()),
                        caveats=CUBE_CAVEATS)

    @server.tool(annotations=read_only)
    @safe_tool
    def inspect_transitions(filename: FileName) -> TransitionInfo:
        """Validate CSV or cclib-supported ORCA output; return excitation energies and oscillator strengths."""
        table = load_transitions(filename)
        return TransitionInfo(transition_count=len(table), transitions=[
            Transition(energy_ev=float(e), wavelength_nm=float(HC / e), oscillator_strength=float(f))
            for e, f in table
        ], caveats=SPECTRUM_CAVEATS)

    @server.tool(annotations=read_only)
    @safe_tool
    def broaden_spectrum(filename: FileName, fwhm_ev: Fwhm = 0.18) -> Spectrum:
        """Return the 1,600-point Gaussian energy-space envelope, wavelengths, units, and integrated area."""
        return spectrum_data(load_transitions(filename), fwhm_ev)

    @server.tool(annotations=writes_export)
    @safe_tool
    def export_orbital(filename: FileName, isovalue: Positive = 0.03,
                       opacity: Opacity = 0.72, show_atoms: bool = True) -> Export:
        """Write standalone offline HTML for signed surfaces at an absolute source-amplitude isovalue."""
        grid = load_cube(filename)
        figure = orbital_figure(grid, isovalue, opacity, show_atoms)
        surfaces = sum(trace.type == "mesh3d" for trace in figure.data)
        caveats = list(CUBE_CAVEATS)
        if not surfaces:
            caveats.append("No isosurface at this threshold. Choose an isovalue within the field's amplitude range.")
        return save(figure.to_html(include_plotlyjs=True), ".html", "text/html", caveats,
                    coordinate_unit="angstrom", amplitude_unit="source-defined",
                    isovalue=isovalue, surface_count=surfaces)

    @server.tool(annotations=writes_export)
    @safe_tool
    def export_spectrum(filename: FileName, fwhm_ev: Fwhm = 0.18,
                        format: Literal["csv", "html"] = "csv",
                        x_unit: Literal["eV", "nm"] = "eV") -> Export:
        """Write a broadened spectrum CSV (both axes) or offline HTML; x_unit controls only the HTML axis."""
        table = load_transitions(filename)
        spectrum = spectrum_data(table, fwhm_ev)
        if format == "csv":
            output = StringIO()
            np.savetxt(output, np.column_stack((spectrum.energy_ev, spectrum.wavelength_nm, spectrum.intensity_f_per_ev)),
                       delimiter=",", header="energy_ev,wavelength_nm,intensity_f_per_ev", comments="")
            content = output.getvalue()
        else:
            content = spectrum_figure(table, fwhm_ev, x_unit == "nm").to_html(include_plotlyjs=True)
        return save(content, "." + format, "text/csv" if format == "csv" else "text/html", spectrum.caveats,
                    x_unit=x_unit if format == "html" else "eV", intensity_unit="oscillator_strength/eV", fwhm_ev=fwhm_ev)

    return server


def main():
    parser = argparse.ArgumentParser(description="Orbital Studio local MCP server (stdio).")
    parser.add_argument("--data-dir", type=Path, required=True, help="Trusted directory containing input files (required).")
    parser.add_argument("--output-dir", type=Path, help="Export directory; default: DATA_DIR/exports.")
    args = parser.parse_args()
    try:
        server = create_server(args.data_dir, args.output_dir)
    except FileAccessError as exc:
        parser.error(str(exc))
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
