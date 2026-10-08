# EDU-01 — Explain absorption from orbital and transition artifacts

Issue: [#14](https://github.com/Mapped-Assembly/nano-tech-harness/issues/14).
Evidence scope: **synthetic teaching fixtures**. No molecule, molecular CUBE bundle
or electronic-structure calculation output was supplied with the issue. The existing
example CUBE, CSV and ORCA-format text are explicitly synthetic and unrelated.

**Decision:** deliver a reproducible teaching explanation and inspectable exports;
**block a molecule-specific transition assignment**. This is the precisely bounded
outcome allowed by the benchmark contract. No quantum calculation, experiment,
validated CAID import or physical-system qualification is claimed.

## Run it

From the repository root, with Python 3.11+:

```bash
python -m pip install -r requirements.txt
python -m orbital_viewer.benchmark --plan benchmarks/EDU-01/plan.json --data-dir examples/mcp --output .benchmark-runs/EDU-01
python -m orbital_viewer.absorption_explanation --run-dir .benchmark-runs/EDU-01 --lesson benchmarks/EDU-01/lesson.json
```

These same single-line Python commands work in Windows PowerShell. Then open the
report with:

```powershell
Start-Process .benchmark-runs/EDU-01/index.html
```

On other systems, open that HTML file in a browser. Both commands refuse to
overwrite their existing outputs; choose a fresh run directory to repeat. The
teaching report and Plotly visualizations work offline. External reference links
need internet access. Keep the complete run directory together, including
`inputs/` and `exports/`, when copying or sharing it.

CI executes these commands and publishes an `EDU-01-synthetic-evidence-RUN-ATTEMPT`
artifact, retained for 30 days. Unzip it and open `index.html`. A successful run
means the software exercise succeeded; the molecular assignment remains blocked.

## What the exercise explains

Electronic absorption connects the difference between electronic-state energies
to transition intensity. In the supplied CSV, **Observed** input row 2 has energy
**4.241 eV** and oscillator strength **0.72**, the largest strength among its four
rows. **Derived** using the application's `hc = 1239.841984 eV nm`, its photon
wavelength is about **292.3466 nm**, in the ultraviolet. The other synthetic rows
are 3.65, 4.85 and 5.4 eV, with strengths 0.09, 0.26 and 0.12. These locate and
weight the sticks in an illustrative UV envelope. They establish no absorption
band of an actual molecule.

The **Assumed** 0.18 eV Gaussian FWHM controls display broadening, not an inferred
physical linewidth. Its unit-area Gaussian formula is

`g(E) = Σ_i f_i exp[-(E−E_i)²/(2σ²)] / (σ√(2π))`,
where `σ = FWHM / √(8 ln 2)`.

The exact energy integral over the full real axis is `Σ f_i = 1.19`. The recorder
uses a finite positive-energy grid; the report independently recomputes the
trapezoidal integral over all 1,600 returned samples and reports the difference.
It also checks every CSV export row against the returned spectrum. Near-zero
tails and undersampled narrow lines remain documented limitations of the existing
tool. The nm view only remaps `E` to `hc/E`; its vertical axis is still **f/eV**.
A density per nm would require the Jacobian `hc/λ²`, which is not applied here.

The lesson and rendered report explain all nine requested concepts with primary
references: wavefunction amplitude, probability density, orbital phase, electron
density, excitation energy, oscillator strength, absorption spectrum, HOMO/LUMO
and NTO hole/electron pairs. See [`lesson.json`](lesson.json) for the explanation,
claim classification, source scope and retrieval/access notes for each concept.
In particular, signed colors represent the sign of a real amplitude **only when
the field is known to be an orbital**; they never represent positive/negative
charge. This input is simply a signed scalar fixture, not an identified orbital.

## Actual tool plan and exported evidence

[`plan.json`](plan.json) reuses the existing actual-stdio evidence recorder.
It pins the three unchanged example inputs by Git blob hash and records display
assumptions separately from observed tool responses.

| Call | Tool and input | Recorded purpose |
|---|---|---|
| 1 | `inspect_transitions`, `transitions.csv` | Observe four synthetic energy/strength rows |
| 2 | `inspect_transitions`, `synthetic-orca.out` | Exercise the cclib ORCA-format parser separately |
| 3 | `broaden_spectrum`, CSV, 0.18 eV | Observe the sampled energy-space envelope |
| 4 | `export_spectrum`, CSV output | Export both axes and f/eV values |
| 5 | `export_spectrum`, HTML/eV | Export an interactive energy view |
| 6 | `export_spectrum`, HTML/nm | Export an interactive wavelength view |
| 7 | `inspect_cube`, `signed-field.cube` | Observe grid, affine axes and scalar range |
| 8 | `export_orbital`, isovalue 0.5 | Export both signs of the synthetic field |

Expected output: **four actual MCP exports** (one CSV and three offline interactive
HTML files), raw `run.json`, copied plan/inputs, hashes and implementation versions.
The explanation command adds `explanation.json`, `lesson.json` and `index.html`.
It checks run status, call sequence/arguments, text-versus-structured results,
schemas/caveats, input and export hashes, pinned fixture identities, transition
input agreement, spectral units/conversions and exported numerical consistency
before writing. It rejects a failed, incomplete or inconsistent bundle.
These are consistency checks on a trusted local recorder's evidence, not external
attestation of a chemistry calculation.

## Exact assignment evidence and missing outputs

| Available evidence | What it supports | What it cannot establish |
|---|---|---|
| CSV energy and strength columns; exact row and MCP response pointers in `explanation.json` | Stick positions, relative strengths, derived wavelengths | State identity, occupied/virtual pair, orbital character or mechanism |
| Synthetic ORCA-format parser example; its separate response pointer | Compatibility with that specific parser fixture | A completed quantum job, molecule identity or real state composition |
| One synthetic 2×2×2 CUBE with values −1 and +1 | Signed scalar rendering on the recorded affine grid | Normalization, MO index/occupation, HOMO/LUMO label, NTO pair or electron density |
| Broadened samples, CSV and two spectrum views | Numerically reproducible display using explicit assumptions | Measured absorbance, physical linewidth or unique electronic assignment |

**No artifact joins a particular stick to the displayed scalar field.** Having
both kinds of file is not sufficient. `molecule`, `assigned_transition`,
`nto_weights`, CUBE occupation and orbital role remain `null`;
`assignment_allowed=false` and `release_allowed=false`.

For a defensible MO-based assignment, obtain a matched calculation bundle with:

1. Molecule and geometry, charge/multiplicity, method/basis, solvent/environment,
   program/version, convergence and job/input/output provenance.
2. State-resolved excited-state output: state labels, excitation energies,
   oscillator strengths, transition dipoles, occupied-to-virtual contributions,
   spin labels and printing threshold. Preserve the method's coefficient/weight
   convention; do not turn every coefficient into a probability by squaring it.
3. CUBEs for those contributing orbitals, with field identity, occupation,
   MO index and zero/one-based convention, units and geometry mapping.

If claiming an **NTO** interpretation, also require a state-specific hole/electron
pair mapping, pair weights and their convention/threshold, and the source
transition-density analysis. NTO output is optional for an MO-based interpretation.
The viewer neither computes NTOs nor infers their pairs or weights.

Experimental absorption, calibration and uncertainty are needed for experimental
comparison or an application decision; they are a separate qualification stage,
not a prerequisite for describing a sufficiently evidenced computed transition.
No generic orbital-energy difference replaces a state-resolved excitation energy.

## Handoffs, engineering decision and reusable gaps

Five explicit handoffs are recorded in the lesson: requester → computational
chemist → artifact producer → Orbital Studio operator → scientific reviewer →
CAID/educator. They cover calculation selection and review, exports, identity/index
mapping, tool use and approval of the resulting claims.

The reusable gaps are typed calculation provenance, CUBE field/occupation metadata,
state-resolved transition adapters, explicit NTO pairing/alignment, unit-aware
spectral explanations and portable evidence-linked reports. This PR implements the
last capability for the existing synthetic workflow. It does not add a quantum
engine adapter or claim support for assigning arbitrary uploaded datasets.

**Engineering/CAID outcome:** retain these files as educational evidence. Do not
populate a material absorption model, select hardware from a synthetic band or
approve a molecular assignment. Obtain and review the matched inputs above first.
The JSON decision is an evidence sidecar, not a schema-validated Hardware IR import.
Confidence is high for the checked software arithmetic; molecule-specific
confidence is undetermined. No compute cost or human-effort estimate is invented.

## Acceptance and verification

The six issue criteria map to the implementation as follows:

| Criterion | Evidence |
|---|---|
| Relevant tools exercised | Eight-call plan, actual MCP transcript and four exports |
| No unsupported scientific values | Synthetic scope, classified claims, unknown assignments and release block |
| Missing upstream artifacts explicit | Assignment evidence table and conditional MO/NTO requirements |
| Manual handoffs recorded | Five named handoffs in `lesson.json` and the report |
| Engineering/CAID decision | Machine-readable blocked assignment and educational-only use decision |
| Reusable gaps identified | Six gaps with general capabilities in `lesson.json` |

Run `python -m pytest -q` for the full suite. EDU-01 tests exercise the actual stdio
server, output generation and CLI, reject corrupted/failed/relabelled evidence,
check scientific units/conversions and preserve unknown assignments. The workflow
also reruns PROCESS-01, SENSOR-01 and BAT-01. Review actual run links and counts in
the PR; the plan alone is not execution evidence.

The IUPAC natural-orbital definition was available through the official indexed
text, while direct access returned HTTP 403; that access limitation is preserved
in the source ledger. ORCA and MIT references explain concepts and upstream data
requirements. Their example molecular results are not substituted for missing
inputs in this benchmark.
