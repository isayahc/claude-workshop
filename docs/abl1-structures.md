# Local ESMFold structure stage

[Issue #5](https://github.com/Mapped-Assembly/nano-tech-harness/issues/5) adds the
sequence-to-structure stage after the [validated sequence inputs](abl1-sequences.md).
The same command accepts either WT or T315I FASTA. It launches a local worker,
validates the resulting PDB against the requested sequence, preserves confidence
and full-source residue numbering, and exports a reproducible run bundle.

**Verification boundary:** ordinary CI exercises the complete process/artifact
flow with an explicitly illustrative fixture, including failure handling and
cache reuse. No pretrained ESMFold inference was performed while implementing
this change: that environment had no PyTorch or GPU runtime. The optional real
smoke test below remains the deployment check for your chosen machine. Fixture
coordinates and confidence placeholders must not be used for pocket detection,
docking or scientific comparison.

## Backend and requirements

The real backend is Hugging Face's local port of ESMFold v1:

| Setting | Value |
| --- | --- |
| Model | `facebook/esmfold_v1` |
| Immutable checkpoint revision | `75a3841ee059df2bf4d56688166c8fb459ddd97a` |
| Transformers | `4.57.6`, checked by the worker |
| PyTorch | `>=2.6,<3`; actual version and CUDA build recorded |
| Other optional packages | Accelerate, SciPy; versions recorded along with NumPy and Hugging Face Hub |
| Default device/precision | CUDA; ESM stem float16, folding trunk float32 |
| CPU option | Explicit `--device cpu`, all float32; potentially much slower |
| Default recycling | `--num-recycles 3`: three additional passes, four total |
| Default attention chunk | `--chunk-size 128` |
| Seed | `--seed 0`, recorded; not a cross-device bitwise-reproducibility guarantee |

The wrapper and worker require Python 3.11+. Linux or Windows **WSL2/Linux** is
the supported execution recipe, including process-group termination on timeout.
The model checkpoint is multi-gigabyte; plan substantial disk space and tens of
GB of RAM/VRAM depending on device, sequence length and settings. No memory or
speed measurement for ABL1 is claimed here. Smaller attention chunks can reduce
memory usage at a speed cost. This adapter caps inputs at 1,024 residues and never
silently truncates them; the default kinase-domain input has 252 residues.

For an isolated inference environment, from the repository root:

```bash
python3.11 -m venv .venv-fold
source .venv-fold/bin/activate
python -m pip install --upgrade pip
# Install a PyTorch build compatible with your driver, then the remaining extra.
python -m pip install -e '.[fold]'
```

Use the [official PyTorch selector](https://pytorch.org/get-started/locally/) if
your CUDA/driver setup needs a specific wheel. Confirm that
`python -c "import torch; print(torch.__version__, torch.cuda.is_available())"`
reports a working CUDA runtime before a CUDA prediction. The ordinary
`requirements.txt` install does **not** install the folding extra, weights or GPU
toolchain. You can keep the orchestration environment separate and pass the
inference interpreter as `--python /absolute/path/to/.venv-fold/bin/python`.

**Data handling:** sequences and inference stay on this machine. The default
uses locally cached weights only. `--allow-model-download` permits downloading
the pinned public checkpoint/config from Hugging Face; it does not send the
sequence to an inference service. Hub telemetry is disabled. The pinned model
uses its original PyTorch weight file with `weights_only=True`; no automatic
remote model-code loading or hosted conversion is used. Downloading dependencies
and model files still requires network access; cached execution does not.

## Run either variant

Generate the sequence input once (or supply an existing intact #4 bundle):

```bash
python -m protein_workflow.sequences --offline --cache tests/fixtures/abl1/P00519.cache.json --output .protein-runs/abl1-inputs
```

Run each prediction with a new output directory:

```bash
python -m protein_workflow.folding --fasta .protein-runs/abl1-inputs/ABL1_WT.fasta --output .protein-runs/abl1-WT --allow-model-download
python -m protein_workflow.folding --fasta .protein-runs/abl1-inputs/ABL1_T315I.fasta --output .protein-runs/abl1-T315I
```

After project installation, `abl1-fold` is equivalent to
`python -m protein_workflow.folding`. `--manifest PATH` selects a sequence
manifest elsewhere; otherwise it is read beside the FASTA. Both source FASTAs,
the raw UniProt response and the full mapping must still be intact. The adapter
reconstructs the mutation from the source, rather than trusting an edited FASTA
or an updated file checksum alone.

The command reports stage progress on stderr and a final JSON result on stdout.
Follow `status.json`, `events.jsonl` and `worker.stdout.log` during a run. The
default inference timeout is **1,200 wall-clock seconds**, covering worker startup,
weight loading/download and inference. A separate dependency/runtime probe gets
at most 60 seconds (or the shorter configured timeout). Set `--timeout SECONDS`
explicitly if an initial download or CPU run needs longer.

The importable API is `run_prediction(fasta, output, config=PredictionConfig(...))`.
It returns a typed `PredictionResult` containing terminal status, result/validation
paths, a usable structure path only on success, and whether the cache was used.
Input/configuration errors raise before creating the run directory; backend
failures return a failed/timed-out result with diagnostics. The CLI exits 0 only
on success and 2 on failure. Existing output paths are refused, including failed
runs; choose a new path to retry while preserving the original logs.

## Numbering, validation and confidence

ESMFold receives exactly the selected extracted sequence. The adapter's PDB
contract is **one chain A, residues 1..L, no insertion codes or alternate locations**.
Structure residue 74 therefore maps to full IA source position 315 for the default
242–493 interval. Custom source intervals from #4 retain their own offset.

Every input residue appears in `validation.json`, including a `null` structure
mapping if missing. The report lists sequence mismatches, missing positions,
unmapped atom records and missing backbone atoms. Wrong-chain, out-of-range,
multiple-model, duplicate, nonfinite and ambiguous records are rejected. Partial
or mismatched structures remain reviewable in the failed run but are not accepted
or cached. The validator checks input identity and backbone completeness; it does
not perform stereochemical refinement, side-chain completeness checks or clash
analysis. A successful result is not a prepared docking receptor.

The pinned Transformers implementation returns `plddt` in **0..1**, whereas its
PDB serializer writes supplied values directly into B-factor columns. The worker
checks that raw scale and explicitly multiplies by 100 before serialization:

- `raw/confidence.json` preserves unrounded C-alpha values and the conversion.
- The PDB B-factor columns contain atom-level **pLDDT in 0..100**, rounded to two
  decimal places; these are not experimental thermal displacement factors.
- `validation.json` exposes per-residue C-alpha pLDDT and its arithmetic mean,
  and verifies agreement with the raw values within PDB rounding precision.
- Fixture-mode scientific confidence is always `null`; its artificial zero
  B-factors must not be interpreted as a real confidence estimate.

pLDDT describes the model's local structural confidence. It is not evidence of
binding affinity, resistance, a ligand-compatible conformation or a meaningful
WT/mutant structural difference. Those interpretations require later analysis.

## Bundle, cache and failures

| Artifact | Purpose |
| --- | --- |
| `inputs/` | Complete verified #4 input bundle with both FASTAs and original source |
| `request.json` | Selected sequence, backend settings and model-download policy |
| `raw/structure.pdb` | Predicted structure or prominently labeled artificial fixture |
| `raw/confidence.json` | Raw confidence values and explicit scale conversion, or null fixture values |
| `raw/backend.json` | Actual runtime versions, pinned model, settings, sequence hash, completion time and backend duration |
| `validation.json` | Every source/domain/structure mapping and validation diagnostics |
| `probe.*.log`, `worker.*.log` | Captured stdout/stderr (worker logs absent on cache hits) |
| `status.json`, `events.jsonl` | Current/terminal stage state and progress history |
| `result.json` | Terminal result, relative artifact paths, hashes, runtime and provenance |

Only consume `result.json` when `status == "succeeded"`; then check
`classification` to distinguish `computed_prediction` from `illustrative`.
`prediction_validated` means the structural *file* passed the stated checks.
`docking_ready` stays false. Failed/timed-out/cancelled results never expose a
usable `structure_artifact`. A killed interpreter/machine may leave `running`
status behind; that is an incomplete run, not success.

Prediction cache entries live under `.protein-cache/structures` by default.
Keys include sequence hash, immutable model/revision, model settings, runtime
versions/hardware identity and hashes of the adapter/worker/validator/sequence
code. Thus WT, T315I, changed recycling/chunk settings and different runtimes do
not silently share a prediction. Timeout and download permission do not affect
the scientific cache key. Each reuse rechecks artifact hashes, receipt identity,
confidence and PDB semantics, and regenerates the current source mapping.

Cache hits preserve the original backend completion time; the new result records
its own start/duration and `cache_hit=true`. For real results,
`inference_executed_this_run=false` distinguishes reuse from a new computation.
Failed real attempts may have an unknown (`null`) execution-completion flag; their
logs and terminal status carry the evidence. Failed, partial and illustrative
outputs never enter the real prediction cache namespace. Fixture entries have a
different model/backend identity. Cache hashes detect corruption, not malicious
rewriting of both data and receipts. `--no-cache` bypasses both reads and writes
for investigation; a corrupt entry fails visibly and is never silently replaced.

On timeout, the wrapper kills and reaps the worker; on Linux/WSL2 it also signals
the worker's entire process group. There is no automatic fallback to a fixture
or hosted predictor. Check the failure receipt and stderr log for missing
dependencies, unavailable CUDA, missing local weights, download errors or memory
exhaustion before retrying in a fresh directory.

## Offline walkthrough and verification

No model download, model package or GPU is needed:

```bash
python -m protein_workflow.folding --backend fixture --fasta .protein-runs/abl1-inputs/ABL1_WT.fasta --output .protein-runs/fixture-WT
python -m protein_workflow.folding --backend fixture --fasta .protein-runs/abl1-inputs/ABL1_T315I.fasta --output .protein-runs/fixture-T315I
python -m protein_workflow.folding --backend fixture --fasta .protein-runs/abl1-inputs/ABL1_WT.fasta --output .protein-runs/fixture-WT-cached
python -m pytest -q tests/test_protein_folding.py
```

The fixture is a deterministic, artificial straight backbone generated from the
validated sequence, with no side chains or claimed structural confidence. Its
PDB REMARKs, backend identity and manifests retain that label, including on reuse.
CI publishes both variants and a repeated cached WT run as the
`ABL1-structure-fixture` artifact, plus test results. The existing orbital/MCP
regression suite and benchmark artifact workflows continue to run.

**Optional real-backend smoke test:** install the extra and matching compute
runtime, then run both real commands above. Confirm both results say
`succeeded` / `computed_prediction`, the checkpoint revision matches the table,
and `validation.json` contains 252 matching residues with no missing/unmapped
entries. At default structure residue 74 confirm T for WT and I for T315I,
both mapped to source position 315. Inspect the complete structure and confidence
profile before proceeding; do not require or assume any particular WT/mutant
geometry or score difference. Repeat WT into a new output directory, verify
`cache_hit=true` and identical PDB bytes, then repeat with a different chunk or
recycle setting and verify a new cache key. Preserve result/validation files,
runtime logs and GPU configuration as the real-backend verification receipt.

## Primary implementation references

- [ESMFold project and installation/compute guidance](https://github.com/facebookresearch/esm)
- [Pinned model checkpoint](https://huggingface.co/facebook/esmfold_v1/tree/75a3841ee059df2bf4d56688166c8fb459ddd97a)
- [Transformers 4.57.6 ESMFold source](https://github.com/huggingface/transformers/blob/v4.57.6/src/transformers/models/esm/modeling_esmfold.py): AF2 token ordering, recycling, `categorical_lddt` and `output_to_pdb`
- [Pinned PDB serializer](https://github.com/huggingface/transformers/blob/v4.57.6/src/transformers/models/esm/openfold_utils/protein.py)
- [ESM documentation](https://huggingface.co/docs/transformers/v4.57.1/model_doc/esm)
