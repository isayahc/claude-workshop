# Orbital Studio MCP server

Use any MCP client/agent that supports **local stdio servers** to inspect scalar CUBE grids, read transition data, broaden spectra, and export interactive HTML/CSV. The server calls the same `orbital_viewer.data` and `orbital_viewer.plots` functions as Streamlit. It does not start or import Streamlit, call a model, require an API key/password, run ORCA, or infer NTO pairs.

## Install and start

Python 3.11+ is required. From a fresh checkout:

```bash
git clone https://github.com/isayahc/claude-workshop.git
cd claude-workshop
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[mcp]'
orbital-studio-mcp --data-dir ./examples/mcp
```

Windows PowerShell, without activating the environment:

```powershell
git clone https://github.com/isayahc/claude-workshop.git
cd claude-workshop
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[mcp]"
.\.venv\Scripts\python.exe -m orbital_viewer.mcp_server --data-dir .\examples\mcp
```

The process waits for MCP JSON-RPC on stdin and writes responses to stdout. There is no web URL to open. Normally your MCP client launches this command for you; Ctrl+C stops a manually started server. Logs/third-party parser diagnostics go to stderr. Only stdio is exposed; no listening port or hosted service is needed. `--data-dir` is required, so a client never implicitly receives access to the process's working directory.

Exports default to `DATA_DIR/exports`. Use `--output-dir /absolute/path/to/exports` to choose another directory. It is created only on the first export. The equivalent module entry point is `python -m orbital_viewer.mcp_server`.

The MCP extra pins the SDK's supported v1 API (`mcp>=1.28,<2`). Install `python -m pip install -r requirements.txt` for the existing Streamlit app and complete test environment, then run `streamlit run app.py` as before.

## Generic client configuration

In a client with the common `mcpServers` configuration format, use absolute paths. Each client has its own settings location and may call these fields something else; the essential settings are transport **stdio**, a Python executable, and its argument list.

```json
{
  "mcpServers": {
    "orbital-studio": {
      "command": "/absolute/path/claude-workshop/.venv/bin/python",
      "args": [
        "-m", "orbital_viewer.mcp_server",
        "--data-dir", "/absolute/path/claude-workshop/examples/mcp",
        "--output-dir", "/absolute/path/claude-workshop/exports"
      ]
    }
  }
}
```

On Windows, use e.g. `C:/work/claude-workshop/.venv/Scripts/python.exe` and `C:/work/claude-workshop/examples/mcp`. The editable package install makes the command independent of the client's working directory. Approve/connect the local server using your client's normal controls, then discover its tools. No agent vendor is assumed.

## Tools and result contract

All tools publish JSON input and output schemas. Successful responses have MCP `structuredContent` plus a JSON text fallback for older clients. Every output includes `schema_version: "1"` and a `caveats` list. Validation and processing failures set MCP `isError: true` with an actionable message, without Python tracebacks or internal filesystem paths. Export URIs intentionally identify the file just created.

| Tool | Arguments | Result |
| --- | --- | --- |
| `inspect_cube` | `filename` | Shape, voxel/atom counts, origin and full affine grid axes in angstroms, amplitude min/max with source-defined units |
| `inspect_transitions` | `filename` | Validated rows: `energy_ev`, `wavelength_nm`, dimensionless `oscillator_strength` |
| `broaden_spectrum` | `filename`, `fwhm_ev=0.18` | 1,600 samples of `energy_ev`, `wavelength_nm`, `intensity_f_per_ev`, sampled integral and total oscillator strength |
| `export_orbital` | `filename`, `isovalue=0.03`, `opacity=0.72`, `show_atoms=true` | Standalone HTML artifact, surface count, absolute isovalue and units |
| `export_spectrum` | `filename`, `fwhm_ev=0.18`, `format="csv"` or `"html"`, `x_unit="eV"` or `"nm"` | CSV or standalone HTML artifact with spectrum units and caveats |

Input filenames are **relative to `--data-dir`**, using `/` separators (also on Windows). CUBE tools accept `.cube`/`.cub`; transition tools accept `.csv`/`.out`/`.log`. Text must be UTF-8; a UTF-8 BOM is accepted. Example: `calculation/orbital.cube`, not an absolute path or URL. Parameters are finite numbers: `0 < fwhm_ev <= 100`, `isovalue > 0`, and `0 <= opacity <= 1`.

Artifacts report `filename`, `uri` (local `file:` URI), `media_type`, and `size_bytes`. Filenames are generated uniquely and never overwrite input or existing exports. HTML includes Plotly and the rendered data for offline viewing. CSV always has `energy_ev,wavelength_nm,intensity_f_per_ev`; `x_unit` affects HTML only. Open the artifact with a local browser or spreadsheet program; an MCP client may not display local file links automatically. The server does not send the full HTML through model context or provide arbitrary file downloads.

## Minimal example session

Start with `--data-dir ./examples/mcp`, connect, and discover tools (`tools/list`). Ask your agent:

> Inspect signed-field.cube and transitions.csv. Broaden the transitions with a 0.18 eV FWHM, export the spectrum as CSV and wavelength HTML, and export both signed orbital surfaces at isovalue 0.5. Explain the units and scientific limitations.

The corresponding `tools/call` names and arguments are:

```json
{"name":"inspect_cube","arguments":{"filename":"signed-field.cube"}}
{"name":"inspect_transitions","arguments":{"filename":"transitions.csv"}}
{"name":"broaden_spectrum","arguments":{"filename":"transitions.csv","fwhm_ev":0.18}}
{"name":"export_spectrum","arguments":{"filename":"transitions.csv","format":"csv"}}
{"name":"export_spectrum","arguments":{"filename":"transitions.csv","format":"html","x_unit":"nm"}}
{"name":"export_orbital","arguments":{"filename":"signed-field.cube","isovalue":0.5}}
```

Expected: a `2 × 2 × 2` grid, one atom, angstrom coordinates, a skew second axis `[0.5, 1, 0]`, amplitude range `[-1, 1]`, four transitions, sampled spectral area approximately **1.19**, two signed surfaces, and three newly created export files. `synthetic-orca.out` also exercises cclib's ORCA extraction (two synthetic transitions at 4 and 5 eV). **All these samples are synthetic parser/visualization fixtures, not calculated molecular orbitals or experimental results.**

The protocol smoke test launches a real stdio subprocess and performs this session without an LLM:

```bash
python -m pip install -r requirements.txt
python -m pytest -q
```

## Local data handling and trust boundary

- Starting this server authorizes the connected client to read supported files under the chosen data directory and create exports under the chosen output directory. Choose a dedicated calculation folder, not a home directory or drive root.
- Absolute paths, traversal (`..`), Windows drive/UNC paths, and symlink escapes are rejected. Only regular files are read; directories/devices/FIFOs are rejected. Reads are bounded to **40 MiB per input**, including files that grow during reading. The existing **4 million voxel / 10,000 atom** CUBE limits remain in force. Transition calls are limited to **10,000 rows** and exports to **100 MiB** each.
- The server is a local tool for a trusted client and trusted local directory ownership, **not an OS sandbox**. Do not let another untrusted local process replace files/directories/symlinks while it runs. A user with filesystem access can still create hard links or modify files outside this application's control. For hostile multi-user workloads, use OS/container isolation.
- No raw files are uploaded by the server. Parsed metadata, transition rows, spectra, and artifact locations are returned to your MCP client. That client may send tool results to its chosen model/provider; local processing alone does not make a hosted agent private.
- ORCA parsing uses a temporary local file which is removed after parsing. Exports persist until you delete them. There is no server cache, background computation, automatic network fetch, shell tool, or arbitrary write tool.
- File limits bound accepted inputs, not peak memory: parsing, meshes, bonds, and embedded Plotly HTML can use considerably more RAM. Use smaller grids for dense isosurfaces; repeated exports also consume disk space. There is no multi-user quota system.

## Scientific limitations

This interface retains the app's scientific scope. Scalar CUBE coordinates are converted to angstroms, preserving affine/skew axes; amplitude units belong to the source calculation. Multi-field grids and mixed-sign unit counts are unsupported. Colors indicate wavefunction phase, not charge. A threshold outside the amplitude range produces no surfaces and a warning. Bonds are distance-inferred; no automatic molecule alignment or NTO pairing is performed.

Gaussian broadening is area-normalized in **energy space**. The positive-energy, fixed 1,600-point grid can truncate low-energy tails or undersample very narrow lines; compare `integrated_oscillator_strength` with `total_oscillator_strength` and heed sampling warnings. Wavelength display maps `hc/E` without applying a spectral-density Jacobian, so intensities remain **f/eV**, not f/nm. Values are not calibrated absorbance and oscillator strengths are not NTO weights. ORCA output compatibility depends on cclib and the producing ORCA version; provide CSV if parsing fails.

Protocol reference: [official MCP Python SDK v1 server documentation](https://py.sdk.modelcontextprotocol.io/v1/server/).
