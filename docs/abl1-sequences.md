# ABL1 sequence input: wild type and T315I

This is the sequence-input stage in [issue #4](https://github.com/isayahc/claude-workshop/issues/4).
It retrieves the reviewed human ABL1 entry from UniProt, extracts a kinase-domain
interval, checks the reference residue, and exports wild-type and T315I FASTA
files with a provenance manifest. It does not predict a structure, locate a
pocket or dock a ligand. The supplied workshop photograph identifies the input
stage; this implementation does not assume the unseen workshop steps.

## Run

Use Python 3.11+ on Linux, macOS or Windows/WSL2. This stage uses only the Python
standard library: no model, GPU, API key or additional package is needed.
From the repository root:

```bash
python data/fetch_sequences.py --output .protein-runs/abl1-input
```

The reusable module has the same interface:

```bash
python -m protein_workflow.sequences --output .protein-runs/abl1-input
```

After installing the project with `python -m pip install -e .`, the equivalent
command is `abl1-fetch-sequences --output .protein-runs/abl1-input`.
Install inside an activated virtual environment so its scripts are on `PATH`;
if the command cannot be found, use the module form above.
Use **one** of these commands with a new output directory for each run.

The command fetches `https://rest.uniprot.org/uniprotkb/P00519.json` over HTTPS
on a cache miss. It reuses `.sequence-cache/P00519.cache.json` on subsequent
runs, preserving the original retrieval timestamp. It sends a public accession
request to UniProt; it does not upload user sequences. `--timeout 30` controls
the socket timeout in seconds. There are no automatic retries or silent fallback
from a failed refresh to older data.

```bash
# Explicitly fetch an updated record; replace cache only after validation.
python -m protein_workflow.sequences --refresh --output .protein-runs/abl1-refreshed

# Reuse your previously fetched cache without contacting UniProt.
python -m protein_workflow.sequences --offline --output .protein-runs/abl1-cached

# Reproducible offline example using the checked-in real response.
python -m protein_workflow.sequences --offline --cache tests/fixtures/abl1/P00519.cache.json --output .protein-runs/abl1-fixture
```

`--cache PATH` chooses a different cache file. Offline mode fails if the file is
absent or invalid. A corrupt cache is an error even in default mode; explicitly
refresh it online or supply an intact snapshot. The cache hash detects accidental
changes, not malicious rewriting of both data and receipt. Cached records are
snapshots, not assertions of current UniProt content.

## Sequence and numbering choice

The [UniProt JSON record](https://rest.uniprot.org/uniprotkb/P00519.json) identifies
the displayed sequence as **P00519-1, isoform IA**, and annotates its Protein kinase
domain. The saved response is entry version **294**, sequence version **4**, UniProt
release **2026_03**, retrieved **2026-10-05T07:00:46.249888+00:00**. Its full-length
sequence has 1,130 residues. Current live runs validate the same identity and
use the domain annotation in the fetched record; review version/boundary changes
in the manifest before comparing runs.

| Quantity | Default snapshot value | Convention |
| --- | --- | --- |
| Source sequence | P00519-1 / IA | Full-length human ABL1 |
| Extracted interval | 242–493 | Source positions, 1-based, both ends included |
| Domain length | 252 | Amino acids |
| Mutation | T315I | Source isoform IA residue 315, T → I |
| Mutation in extracted FASTA | 74 | 1-based position |
| Mutation in Python sequence | 73 | 0-based index |

For any exported interval, `domain_index = source_position - domain_start` and
`domain_position = domain_index + 1`. Every residue gets an explicit mapping row.
Both FASTA files use the same boundaries. The program verifies that exactly one
residue differs and that the mapped substitution is T → I.

Do not apply position 315 blindly to another isoform. UniProt's alternative
sequence annotation for isoform IB/P00519-2 replaces the first 26 IA residues
with 45 residues, shifting the shared kinase segment by +19. The commonly used
T315I label therefore maps to IB position 334; this distinction is also stated
in the [original ABL kinase study](https://pmc.ncbi.nlm.nih.gov/articles/PMC2581583/).
This entry point deliberately accepts **IA only**, checking both its identifier
and displayed-isoform metadata instead of applying an inferred offset to IB.

The default is an annotated domain interval, not a claim that this is the exact
construct used in the workshop photograph or an experimentally validated folding
or docking construct. If a downstream experiment calls for flanking residues,
provide an explicit interval in IA source numbering, for example:

```bash
python -m protein_workflow.sequences --offline --cache tests/fixtures/abl1/P00519.cache.json --domain-start 229 --domain-end 511 --output .protein-runs/abl1-extended
```

That interval has 283 residues and places T315 at exported residue 87. Custom
intervals must be within the source and include residue 315; they are recorded
as `user_supplied_interval`, alongside the original kinase annotation. Suitability
for structure prediction or docking requires a separate review.

## Bundle and provenance

| File | Contents |
| --- | --- |
| `ABL1_WT.fasta` | Extracted wild-type sequence with source coordinates in the header |
| `ABL1_T315I.fasta` | The same sequence with the verified T315I substitution |
| `P00519.source.json` | Exact UTF-8 UniProt response used for this run |
| `manifest.json` | Source URL, retrieval/run times, cache/network mode, release headers, accession/isoform, versions, boundaries, mutation and all residue mappings |

The manifest also records SHA-256 for the full source sequence, both extracted
sequences, each artifact's exact bytes and the implementation module. Sequence
hashes cover the uppercase amino-acid string without FASTA headers or newlines;
artifact hashes cover the complete file. Paths are relative to the manifest, so
keep the bundle together when handing it to the structure stage in issue #5.
The manifest has schema version 1; source/domain positions are 1-based inclusive,
while fields named `domain_index` are 0-based. No structure residue numbers or
confidence scores are invented at this stage.

The program validates source identity, canonical isoform, amino-acid alphabet,
declared length, versions, exact/unambiguous domain boundaries and the T315
reference residue before publishing output. Existing output directories are
refused. The completion manifest is written last; ordinary write failures remove
the partial bundle. If the process is forcibly killed or the machine loses power,
an incomplete directory may remain; a directory without a complete manifest must
not be consumed. Choose a new output path after inspecting an interrupted run.

Failures exit with code 2 and an explanation. For network errors, check connectivity
and retry, or use an intact offline cache. For a residue/isoform/annotation mismatch,
inspect the source and numbering; do not bypass the check by editing the target
position until another threonine is found.

## Verification

Ordinary CI runs entirely offline for this stage:

```bash
python -m pytest -q tests/test_protein_sequences.py
python -m pytest -q
```

Tests cover real cached data, source/domain offsets, exact single mutation, every
mapping row, artifact hashes, both CLI entry points, custom intervals, malformed
sources, wrong reference residues/isoforms, missing/corrupt caches, timeouts,
failed refreshes, output preservation and partial-write cleanup. CI also exports
the offline bundle as an `ABL1-sequences` artifact. Orbital/MCP regression tests
continue to run with the existing benchmark evidence steps.

Optional live smoke test (requires UniProt access):

```bash
python -m protein_workflow.sequences --refresh --cache .sequence-cache/abl1-smoke.json --output .protein-runs/abl1-live-smoke
python -m protein_workflow.sequences --offline --cache .sequence-cache/abl1-smoke.json --output .protein-runs/abl1-offline-smoke
```

Compare the FASTA files and source/sequence hashes from both manifests: they must
match. The original `retrieved_at` must be identical; `created_at` and `loaded_via`
describe the separate runs. Confirm the mapping and mutation table above before
starting any downstream tool. This validates sequence preparation only.
