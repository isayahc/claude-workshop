# ABL1 cavity detection and explicit pocket selection

Issue #6 accepts a successful [structure-stage](abl1-structures.md) `result.json`
for **one variant at a time**. It runs local fpocket, exports inspectable cavities,
and lets you explicitly record a pocket and proposed docking box for #7.

## Install

Python 3.11+ uses only the standard library for this adapter. The fpocket executable
is a separate dependency. In an activated project environment, `pip install -e .`
adds `abl1-pockets`; `python -m protein_workflow.pockets` is equivalent.

The verified Linux source build is fpocket **4.2.3**, commit
`4bb0d8447f62fee77e2c3c29f54b5fcaf5e2c066`:

```bash
# Debian/Ubuntu build prerequisites (see upstream for other platforms)
sudo apt-get install gcc g++ make libnetcdf-dev
git clone --branch 4.2.3 --depth 1 https://github.com/Discngine/fpocket.git /tmp/fpocket-4.2.3
git -C /tmp/fpocket-4.2.3 rev-parse HEAD
make -C /tmp/fpocket-4.2.3
/tmp/fpocket-4.2.3/bin/fpocket
```

Use serial `make`: upstream's parallel build can race Qhull's object generation.
No system-wide installation is needed when `--executable` names the binary.
The adapter recognizes the 4.x output contract; other major versions fail clearly.

The no-argument help banner is captured in full. **4.2.3 prints `fpocket 4.0`**;
`reported_version` preserves that actual value. The executable SHA-256 identifies
the exact build, and optional `--release-label` records your installation provenance
as a user declaration, separate from the reported version. Do not use `-v` as a
version query: fpocket uses it for Monte Carlo iterations.

## Detect both variants

Use successful real ESMFold run directories from #5:

```bash
python -m protein_workflow.pockets detect \
  --structure-result .protein-runs/esmfold-WT/result.json \
  --output .protein-runs/pockets-WT \
  --executable /tmp/fpocket-4.2.3/bin/fpocket \
  --release-label '4.2.3 source 4bb0d8447f62fee77e2c3c29f54b5fcaf5e2c066'

python -m protein_workflow.pockets detect \
  --structure-result .protein-runs/esmfold-T315I/result.json \
  --output .protein-runs/pockets-T315I \
  --executable /tmp/fpocket-4.2.3/bin/fpocket
```

Each output directory must be new. Both runs retain independent structures,
residue mappings, ranks and receipts. `pocket1` in WT is **not** automatically
the same physical site as `pocket1` in T315I.

The adapter rechecks the full #4/#5 source/sequence/backend/PDB provenance and
residue mapping before execution. Default source T315 remains PDB A:74; explicit
custom domain intervals retain their own verified mapping. Missing/ambiguous
residues and changed files are rejected rather than realigned by guesswork.

ESMFold stores pLDDT in PDB's B-factor column. fpocket uses B-factors in its
alpha-sphere filtering and flexibility descriptor. Therefore the adapter archives
the original prediction unchanged and writes a separate `raw/receptor.pdb` with
**B-factors zeroed**. Coordinates and residue/atom identities do not change.
Original pLDDT survives in the archived validation and each contacted residue's
record. fpocket's resulting `Flexibility` value is not a confidence estimate or
an experimental flexibility measurement.

Supported settings are recorded and passed explicitly:

| Setting | Default | Units |
| --- | ---: | --- |
| `--min-alpha-radius` | 3.4 | Å |
| `--max-alpha-radius` | 6.2 | Å |
| `--clustering-distance` | 2.4 | Å |
| `--min-spheres` | 15 | count |
| `--monte-carlo-iterations` | 300 | count |
| `--timeout` | 120 | seconds per detection process |

The version probe has a separate limit of at most 30 seconds. Processes run
without a shell with captured stdout/stderr; timeout/cancellation kills and reaps
the POSIX process group. fpocket always receives the controlled relative filename
`receptor.pdb`, avoiding its internal shell/path limitations. No external service
receives coordinates. Native Monte Carlo randomness is not seeded by this adapter,
so volume estimates can vary; raw outputs are preserved and there is no detection
cache that could conceal a rerun.

## Inspect and select

Inspect `pockets.json` and the corresponding `raw/receptor_out/pockets/` files.
Each record contains:

- An ID/rank local to this structure, original scores and all numeric descriptors.
  Known physical units are explicit; unavailable descriptor units are null.
- Contacted residues with PDB identity, domain position, IA source position,
  observed amino acid and original pLDDT when available.
- Every alpha-sphere center and radius, centroid, center bounds and full sphere
  envelope, all in Å. Pocket geometry is in the input structure's coordinate frame.
- Whether the pocket contacts source residue 315, its observed T/I identity, and
  the distance from its Cα to the nearest alpha-sphere center, in Å.
- Paths to the raw contacted-atom PDB and sphere PQR, relative to `raw/receptor_out`.

Open the raw PDB/PQR with a molecular viewer to inspect the geometry. Do not execute
generated visualization shell scripts automatically. Scores, mutation proximity
and rank alone do not establish a biologically relevant binding site.

After inspecting a pocket, record its exact ID and your rationale. This example
uses `pocket2` only to demonstrate an explicit choice; select the ID you reviewed:

```bash
python -m protein_workflow.pockets select \
  --result .protein-runs/pockets-WT/result.json \
  --pocket pocket2 --padding 4 \
  --rationale 'Describe the structural evidence for the chosen site here' \
  --output .protein-runs/selection-WT
```

The proposed box encloses the **full alpha-sphere envelope**, not just its centers,
and adds `padding` Å on each face. Its center is the envelope midpoint; its size
is the envelope extent plus twice the padding. `selection.json` includes x/y/z
center and size arrays, coordinate units, chosen pocket, rationale, input/result
hashes, exact backend receipt and classification. There is no implicit top-pocket
selection and detection never writes a selection itself.

To supply a reviewed box instead, pass both `--center X Y Z` and `--size SX SY SZ`.
Sizes must be finite and positive. The automatic proposal is retained alongside
the explicit override. Output directories cannot be overwritten.

The selection bundle includes `receptor.pdb`, `pocket.json`, `contact-atoms.pdb`,
`alpha-spheres.pqr`, and the source detection receipt, all hashed. The original run
retains the full provenance archive. #7 can consume the selection's receptor and
box in the same coordinate frame. Receptor/ligand preparation and docking still
need implementation: `docking_ready`, `binding_site_validated` and
`receptor_preparation_performed` remain false. Neither a cavity nor its box is a
binding-affinity result.

## Outcomes and evidence

Successful detection exports `result.json`, `pockets.json`, `status.json`, full
`inputs/structure-run/` provenance, `raw/backend.json`, probe/detection logs and
all raw fpocket artifacts. Every retained artifact has a SHA-256 and byte count.
`status` is `succeeded`, `no_pockets`, `failed`, `timed_out` or `cancelled`.
An explicit, successful empty result returns `no_pockets`, an empty pocket array,
and no selection. CLI exit is zero for `succeeded`/`no_pockets`; failures exit 2.

fpocket can report internal failures while exiting zero. The adapter checks its
completion marker, error diagnostics and output consistency. An absent file or
unexplained empty result is a failure, not a no-pocket finding. Failed runs retain
their receipts/logs and expose no usable pocket artifact.

Tests exercise real recorded output excerpts, both variants through illustrative
subprocesses, malformed descriptors/geometry, source mapping integrity, missing
and failing executables, exit-zero errors, timeouts, empty results, and explicit
selection/overrides. Fixture structures are refused by default; the explicit
`--allow-illustrative` opt-in is only for pipeline tests and preserves their
`illustrative` classification. Their straight artificial backbones are unsuitable
for meaningful cavity detection and can make the real native tool fail.

A separate CI job compiles the pinned real fpocket source and runs its experimental
1UYD reference through positive and forced-empty detection. Reproduce it with:

```bash
python -m protein_workflow.pocket_smoke \
  --fpocket-root /tmp/fpocket-4.2.3 \
  --output .protein-runs/fpocket-reference
```

This verifies the executable/parser contract on a real reference structure.
**Real ESMFold ABL1 inference and its resulting cavity predictions remain unverified**
in this environment; no ABL1 pocket or affinity claims are made from the fixtures.

Primary implementation references: upstream
[installation](https://github.com/Discngine/fpocket/blob/4.2.3/README.md),
[output format](https://github.com/Discngine/fpocket/blob/4.2.3/src/fpout.c),
[PQR writer](https://github.com/Discngine/fpocket/blob/4.2.3/src/writepdb.c),
[version/help](https://github.com/Discngine/fpocket/blob/4.2.3/src/fparams.c), and
[B-factor filtering](https://github.com/Discngine/fpocket/blob/4.2.3/src/voronoi.c).
