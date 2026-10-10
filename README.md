# Nano Tech Harness

Nano Tech Harness is [Mapped Assembly](https://github.com/Mapped-Assembly)'s
collection of scientific tools and reproducible engineering benchmarks. It combines
Orbital Studio molecular visualization and a local MCP server, traceable ABL1/T315I
sequence and structure workflows, and evidence bundles for materials, sensors,
batteries, semiconductors, process planning, and teaching.

Synthetic demonstrations, computed results, literature evidence, and physical
qualification remain explicitly distinguished. See each workflow's scientific
limits before interpreting its outputs. No particular editor, agent, or model
provider is required for the local viewer, MCP tools, or offline benchmarks.

## Getting started

Install Git and Python 3.11+. Linux/macOS or WSL2:

```bash
git clone https://github.com/Mapped-Assembly/nano-tech-harness.git
cd nano-tech-harness
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows PowerShell, without activating the environment:

```powershell
git clone https://github.com/Mapped-Assembly/nano-tech-harness.git
cd nano-tech-harness
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`requirements.txt` installs this checkout with the `mcp`, `ui`, and `test` extras.
It does not install the optional `fold` dependencies or download model weights.
Run the commands below from the repository root using the virtual environment.
In PowerShell, replace `python` with `.\.venv\Scripts\python.exe` if it is not
activated. Real ESMFold execution has a separate Linux/WSL2 setup in the
[structure guide](docs/abl1-structures.md).

| Path | Current contents |
| --- | --- |
| [`app.py`](app.py), [`orbital_viewer/`](orbital_viewer/) | Streamlit viewer, CUBE/spectrum processing, MCP tools, and benchmark helpers |
| [`protein_workflow/`](protein_workflow/), [`data/fetch_sequences.py`](data/fetch_sequences.py) | ABL1 sequence preparation and local structure-stage commands |
| [`benchmarks/`](benchmarks/) | Six reproducible scientific and engineering cases with evidence and limitations |
| [`examples/mcp/`](examples/mcp/) | Synthetic CUBE, ORCA, and transition CSV examples |
| [`docs/`](docs/) | MCP setup and ABL1 workflow guides |
| [`tests/`](tests/) | Offline checks, protocol tests, and source fixtures |

## Contributing

Include reproducible commands, prerequisites, source citations, and explicit
scientific limitations with changes. Run the checks below and submit a focused
pull request to this repository's default branch.

## ABL1 protein workflow

The [sequence-input guide](docs/abl1-sequences.md) implements the first ABL1/T315I
workflow stage. It retrieves and caches UniProt P00519 isoform IA, exports the
wild-type kinase domain and a verified single T315I mutant, and preserves every
residue's source mapping and provenance. Python 3.11+ is sufficient for this stage.

```bash
python data/fetch_sequences.py --output .protein-runs/abl1-input
```

For an offline run, add `--offline --cache tests/fixtures/abl1/P00519.cache.json`
and choose a new output directory. The default annotated interval is IA residues
242–493, so source T315 maps to extracted residue 74. Structure prediction,
pocket detection and docking form the remaining workflow.

The [ESMFold structure stage](docs/abl1-structures.md) accepts either validated
FASTA, runs a local pinned model, checks source-to-structure residue mapping and
confidence, and caches successful predictions. It requires the optional `fold`
dependencies and suitable compute. Try the artifact flow offline with:

```bash
python -m protein_workflow.folding --backend fixture --fasta .protein-runs/abl1-input/ABL1_WT.fasta --output .protein-runs/abl1-fixture-WT
```

Fixture coordinates are artificial and carry no scientific confidence. The guide
documents real model setup and the optional smoke test; real pretrained inference
has not yet been verified in this implementation environment.

The [fpocket stage](docs/abl1-pockets.md) detects cavities independently for each
validated structure, preserves residue mappings and native-tool provenance, and
exports explicit pocket selections with docking-box proposals in Å:

```bash
python -m protein_workflow.pockets detect --structure-result .protein-runs/esmfold-WT/result.json --output .protein-runs/pockets-WT
```

Install fpocket separately as described in the guide. Detection never selects a
binding site automatically. The real executable is verified on its experimental
reference protein; ABL1 fixture structures remain illustrative. Docking and the
comparison interface remain tracked in #7–#8.

## Orbital Studio

A Python/Streamlit molecular orbital viewer inspired by the workshop's ORCA/NTO visualization workflow. No ORCA installation is needed to view existing data.

### Run

After the setup above:

```bash
python -m streamlit run app.py
```

Open the local URL printed by Streamlit (normally http://localhost:8501).

### Use with an MCP-compatible agent

Orbital Studio also runs as a standalone local MCP server (stdio), without Streamlit or an agent-specific dependency:

```bash
python -m pip install -e '.[mcp]'
python -m orbital_viewer.mcp_server --data-dir ./examples/mcp
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

## Engineering and teaching benchmarks

Each case includes reproducible commands and identifies what is still unverified:

| Case | Purpose |
| --- | --- |
| [EDU-01](benchmarks/EDU-01/README.md) | Evidence-linked explanation of absorption and orbital concepts |
| [MAT-01](benchmarks/MAT-01/README.md) | Conditional UV protective-window selection and pinned Hardware IR checks |
| [SENSOR-01](benchmarks/SENSOR-01/README.md) | Uncalibrated UV sensor sizing and design handoffs |
| [BAT-01](benchmarks/BAT-01/README.md) | Reference-aware electrolyte screening and unresolved cell requirements |
| [SEMI-01](benchmarks/SEMI-01/README.md) | Si/SiC/GaN comparison for a robotic power module |
| [PROCESS-01](benchmarks/PROCESS-01/README.md) | Evidence and manual handoffs for process planning |

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

### Compare power semiconductors: SEMI-01

The [SEMI-01 benchmark](benchmarks/SEMI-01/README.md) compares Si, SiC and GaN
for a 650 V robotic power module. It distinguishes switch rating from bus voltage,
bulk material evidence from commercial specifications, and periodic solid-state
research from device selection. SiC is a conditional development baseline; the
operating point and final device remain unresolved.

```bash
python benchmarks/SEMI-01/reproduce.py --output .benchmark-runs/SEMI-01
```

The bundle includes sourced device comparisons, twelve CAID requirements, a
requirements-only proposal checked against the pinned Forma schema, conservative
voltage-headroom checks and two actual MCP calls on a synthetic scalar field.
Successful processing never approves a module or substitutes for device tests.

## Verification

```bash
python -m pytest -q
```

Tests cover CUBE ordering/units/affine axes, malformed data, signed surfaces, spectrum area conservation, CSV validation, Streamlit demo/upload states, MCP schemas and stdio calls, export contents, and bounded local file access.
They also check ABL1 source provenance, illustrative structure runs and cache/failure
paths, and benchmark evidence contracts. Real pretrained folding is an optional
smoke test described in the structure guide.

References: [ORCA NTO/TDDFT documentation](https://www.faccts.de/docs/orca/6.1/manual/contents/spectroscopyproperties/tddft.html), [cclib data units](https://cclib.github.io/data.html), [CUBE format](https://paulbourke.org/dataformats/cube/).

## Repository identity and provenance

The canonical repository is
[`Mapped-Assembly/nano-tech-harness`](https://github.com/Mapped-Assembly/nano-tech-harness),
transferred and renamed from `isayahc/claude-workshop` on October 8, 2026.
For an existing checkout, update its remote from inside that directory:

```bash
git remote set-url origin https://github.com/Mapped-Assembly/nano-tech-harness.git
```

Existing local directories can keep their names; use their actual absolute paths
in MCP client configuration. The installed distribution remains `orbital-studio`,
with `orbital_viewer` / `protein_workflow` imports and the `orbital-studio-mcp`,
`abl1-fetch-sequences`, and `abl1-fold` commands.

Pinned commit URLs, dated source records, fixture hashes, and references to CAID /
Forma in historical benchmark evidence retain their original identity. They record
the source or integration target inspected at the time, not the current owner of
this repository. The rename does not imply new scientific validation or a change
to those external projects.
