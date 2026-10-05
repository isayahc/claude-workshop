# Claude Workshop

A hands-on space for learning, experimenting, and building with Claude and Claude Code.

Use this repository to collect workshop materials, try ideas in small projects, and keep useful prompts and notes in one place. The repository starts intentionally lightweight so it can grow around the exercises and tools used by your workshop.

## Getting Started

1. Clone the repository:

   ```bash
   git clone https://github.com/isayahc/claude-workshop.git
   cd claude-workshop
   ```

2. Open the project in your editor or Claude Code.
3. Add workshop exercises, project files, and notes as you work.

## Working With Claude Code

Claude Code can help you explore a codebase, make focused changes, run checks, and explain its reasoning. Give it a clear goal, relevant context, and constraints. Review proposed changes and run the project's checks before relying on them.

## Suggested Workshop Structure

As the workshop grows, you can organize material into folders such as:

```text
exercises/   Guided practice
projects/    Small hands-on builds
notes/       Concepts, prompts, and takeaways
```

Add setup instructions and verification steps alongside each exercise or project so others can follow along.

## Contributing

Add material that is practical, clearly explained, and easy to try. Include any prerequisites and instructions needed to reproduce the result.

## Orbital Studio

A Python/Streamlit molecular orbital viewer inspired by the workshop's ORCA/NTO visualization workflow. No ORCA installation is needed to view existing data.

### Run (Python 3.11+ / WSL2)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Open the local URL printed by Streamlit (normally http://localhost:8501).

### Use with an MCP-compatible agent

Orbital Studio also runs as a standalone local MCP server (stdio), without Streamlit or an agent-specific dependency:

```bash
python -m pip install -e '.[mcp]'
orbital-studio-mcp --data-dir ./examples/mcp
```

Connect this command in your MCP client's configuration to inspect CUBE/transition files, broaden spectra, and export offline HTML/CSV. The required data directory limits which local files the tools can read; exports are created under its `exports` directory by default. No API key or password is required. See the [MCP setup guide](docs/mcp.md) for Windows commands, generic client configuration, tool schemas, an example session, and data-handling limitations.

### Features

- Rotate and zoom signed orbital isosurfaces with atoms and inferred bonds.
- Upload multiple `.cube` / `.cub` files, select orbitals without repeating `orca_plot` interactions, and compare manually assigned hole/electron pairs.
- Set relative or shared absolute isovalues and surface opacity.
- Import excitation energies and oscillator strengths from cclib-supported ORCA `.out` / `.log` files or CSV.
- Explore Gaussian-broadened spectra in eV or nm and export the curve as CSV.
- Export standalone interactive orbital HTML files, individually or as a ZIP batch.
- Try clearly labeled illustrative benzene-like fields and a synthetic spectrum immediately.

CSV schema:

```csv
energy_ev,oscillator_strength
4.241,0.72
4.85,0.26
```

### Scientific scope and limitations

The demo is an analytic illustration, **not** a computed Si nanoparticle/ethylbenzene system or validated NTO calculation. Orbital surfaces show signed wavefunction amplitude; colors are phases, not charge. CUBE amplitude units come from the producing calculation. Coordinates are converted to angstroms. Bond connectivity is inferred from distances and does not encode bond order.

This app visualizes existing CUBE grids; it does not calculate orbitals, run ORCA, read binary `.gbw`/`.nto` files, or automatically pair NTOs. Export each orbital with `orca_plot` first, then batch-load the results. Hole/electron assignment is manual. The two cameras are independent and molecular structures are not automatically aligned. Relative thresholds scale each field separately; use an absolute threshold for amplitude comparisons.

Supported: scalar CUBE grids, single-orbital negative-atom-count CUBE records, Fortran D exponents, full affine/skew grid axes, positive-count Bohr grids and negative-count angstrom grids. Multi-field CUBEs and mixed-sign grid dimensions are rejected explicitly. Each file is limited to 40 MB and 4 million voxels. Many large grids or dense isosurfaces may still consume substantial memory.

Spectrum broadening uses area-normalized Gaussians in **energy space**, with FWHM in eV. Oscillator strengths determine areas. The wavelength view plots the same envelope against `hc/E`; its ordinate remains f/eV, not f/nm. This is not a prediction of calibrated absorbance. cclib compatibility varies by ORCA version/output; CSV is the explicit fallback. No NTO weights are inferred from oscillator strengths.

Files are processed by the app's Python server. Run locally for local-only calculation handling. Offline exported HTML embeds Plotly and the displayed data.

### Explain absorption: EDU-01

The [EDU-01 teaching benchmark](benchmarks/EDU-01/README.md) exercises the actual
MCP tools, exports interactive orbital/spectrum views, and creates an evidence-linked
explanation of amplitude, density, phase, excitation energies, oscillator strengths,
HOMO/LUMO and NTOs. Its supplied examples are synthetic; molecular assignment stays
blocked until a matched calculation bundle is provided.

```bash
python -m pip install -r requirements.txt
python -m orbital_viewer.benchmark --plan benchmarks/EDU-01/plan.json --data-dir examples/mcp --output .benchmark-runs/EDU-01
python -m orbital_viewer.absorption_explanation --run-dir .benchmark-runs/EDU-01 --lesson benchmarks/EDU-01/lesson.json
```

Open `.benchmark-runs/EDU-01/index.html`. Keep its whole directory together so the
three interactive HTML views, spectrum CSV, raw responses and provenance remain
available. Choose a new output directory for another run. CI also publishes this
directory as the `EDU-01-synthetic-evidence` artifact.

### Select a UV protective window: MAT-01

The [MAT-01 benchmark](benchmarks/MAT-01/README.md) compares specific fused-silica,
PMMA and polycarbonate configurations for an outdoor 280–400 nm sensor. It keeps
supplier evidence separate from actual MCP smoke tests and exports a proposal
checked against pinned Forma Hardware IR 0.2. The material decision remains
conditional; physical qualification and application import remain blocked.

```bash
python benchmarks/MAT-01/reproduce.py --output .benchmark-runs/MAT-01
```

The bundle includes raw MCP responses, research inputs, a conditional assessment,
the proposed window/BOM JSON and source/artifact hashes. CI publishes the same
bundle as `MAT-01-evidence`. Successful tool/schema checks do not qualify a window.

### Verification

```bash
python -m pytest -q
```

Tests cover CUBE ordering/units/affine axes, malformed data, signed surfaces, spectrum area conservation, CSV validation, Streamlit demo/upload states, MCP schemas and stdio calls, export contents, and bounded local file access.

References: [ORCA NTO/TDDFT documentation](https://www.faccts.de/docs/orca/6.1/manual/contents/spectroscopyproperties/tddft.html), [cclib data units](https://cclib.github.io/data.html), [CUBE format](https://paulbourke.org/dataformats/cube/).
