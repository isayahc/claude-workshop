# MAT-01 — outdoor UV protective window

[Issue #9](https://github.com/isayahc/claude-workshop/issues/9). Research refreshed
October 5, 2026. This benchmark separates a material decision, actual software
execution, a schema check, and physical qualification.

## Decision

**Nominate FS-01, Edmund #14-962, for prototype testing. Keep PMMA-01, smooth
PLEXIGLAS GS 2458, as a conditional alternative. PC-01, TUFFAK UV clear 83838702,
lacks sufficient optical evidence for admission to a qualified full-band shortlist.**
This is a test-article priority, not a numerical ranking or production selection.
No candidate passes all optical, mechanical and environmental gates. [E101–E302]

| Workstream | Outcome | Boundary |
|---|---|---|
| Material decision | Conditional | Exact configurations and test priority; no qualified winner |
| Orbital Studio execution | Complete when the recorded MCP run passes | Seven real stdio calls, all five tools, three synthetic exports |
| Candidate-specific orbital analysis | Blocked | No relevant molecular calculation files supplied; no demonstrated decision value |
| CAID schema check | Complete for pinned 0.2 | Real Pydantic validation and local serialization; CI repeats exported JSON Schema and relationship checks |
| CAID export/integration | Blocked for application integration | A window-only JSON proposal is exported; no target-project import |
| Physical qualification | Blocked | Missing acceptance limits and matched optical, impact, sealing and outdoor-life tests |

Every statement's evidence ID resolves through [evidence.json](evidence.json) to
[sources.json](sources.json), including source locations, units, conditions and
limitations. Supplier facts remain **External knowledge**, not local measurements.
Unknowns remain null. Assumptions and derived quantities are labeled separately.

## Requirements and comparison

[requirements.json](requirements.json) records all 16 requirements, their origin,
units, status and consequences. Only outdoor use and the initial 280–400 nm band
come from the issue. Full-band versus selected-wavelength operation, T_required(λ),
haze, distortion, detector response, illumination, environment, life, impact,
pressure, cleaning, quantity, budget and lead time remain unresolved. [E001]

The provisional geometry is a 20 mm clear aperture and 25 mm outer diameter,
smooth initially uncoated faces at normal incidence, and a replaceable perimeter
gasket/retainer. These are **assumptions A01–A03**, not user requirements or a
completed mount. Different thicknesses are compared as configurations; no optical
rescaling or stiffness equivalence is assumed.

| Candidate | Grade/configuration and evidence | Limitation affecting selection |
|---|---|---|
| FS-01 | Edmund #14-962; Corning 7980 0G; 25 mm diameter, 2 ±0.10 mm thick, 22.5 mm clear aperture, uncoated, 40-20 faces. [E101] | Catalog range 200–2200 nm does not specify pointwise transmission. Linked typical spectrum describes **3 mm**, not this 2 mm optic. [E102] |
| PMMA-01 | Smooth PLEXIGLAS GS clear 2458, 3 mm stock, proposed 25 mm cut. Manufacturer lists a typical **≥80% at 315 nm**, DIN 5036 part 3. [E201–E202] | A typical single-point bound is neither an exact measured sample nor full 280–400 nm coverage. Finished-part/aged/angular performance unknown. |
| PC-01 | TUFFAK UV clear 83838702, 0.118-inch stock, 48 ×96-inch sheet, proposed 25 mm cut. [E301] | UV resistance does not establish UV transmission. No numeric spectrum for this SKU was retrieved; this is **unknown**, not a measured optical failure. [E302] |

The silica's listed density is 2.20 g/cm³ and modulus 73 GPa; its cited CTE applies
only to the source's temperature interval. [E103] PMMA has grade-specific density,
modulus and CTE evidence with its own conditions. [E203] These do not establish
allowable mounted loads. The replay derives ideal disc masses from sourced
density and geometry: about **2.160 g silica** and **1.752 g PMMA**. It also converts
0.118 inch to **2.9972 mm**. Bevels, tolerances and mount mass are excluded; PMMA
diameter is assumed. Equations and evidence IDs are in `assessment.json`. [D101–D102]

GS2458 aging information describes 3 and 8 mm samples before/after 1,000 hours
under a 160 W Cosmolux VHR lamp. Lamp rating is not specimen dose or outdoor years;
no numerical aging loss was extracted. Machining stress and cleaning compatibility
need review. [E204–E205] For every candidate, qualify the actual mount, sealant,
cleaner, finish, exposure and failure mode. No IP rating or impact rating is claimed.

Commercial observations retrieved October 5: silica **USD127 each at quantity
1–5**, and 3 mm acrylic **from EUR154.70/m²**; PC needs a quote. These are different
price bases, not comparable delivered-component costs. No currency conversion or
sheet-area-to-disc-cost calculation is made. Dynamic stock/price views, an earlier
EUR118.88/m² snippet, old/current acrylic stock-format differences, and the PC
catalog's inconsistent area-unit column remain recorded. [E104, E206, E301]

## Gates, sensitivity and next physical evidence

Missing evidence prevents qualification; a failed sampled requirement cannot be
hidden by an average. `reproduce.py` includes a small benchmark-only three-state
gate with no interpolation. Its numeric tests are artificial examples, excluded
from candidate evidence. No score weights are applied while hard gates are unknown.

| Changed requirement | Decision consequence |
|---|---|
| Full band including 280 nm | Prioritize FS-01 measurements; catalog coverage is insufficient for acceptance |
| Only 315 nm, as-new threshold no higher than 80% | PMMA becomes a serious test alternative; verify the typical bound on actual parts |
| 95% full-band transmission, as an example | Current evidence qualifies none; investigate an exact coated configuration |
| Glass fragments or impact failure unacceptable | Require mount/impact evidence; reconsider the candidate set |
| Aperture, angle, life or replacement budget changes | Reassess geometry, spectrum, maintenance and matched supplier quotes |

First define whether 280 nm is mandatory, T_required(λ), and the acceptable impact
failure mode. Obtain matched finished-part spectra with thickness, coating, angle,
lot, instrument bandwidth, calibration and uncertainty. Check sufficiently resolved
pointwise acceptance values; separately measure scattering in the relevant
collection geometry. Repeat after agreed aging, cleaning and abrasion exposures,
and test impact/load and sealing in the actual housing.

An optional sensor-weighted metric is
`η = ∫T(λ)E(λ)R(λ)dλ / ∫E(λ)R(λ)dλ`, where E is spectral irradiance per wavelength
and R is detector responsivity. **It is not evaluated:** matched arrays are missing,
and an average would not replace hard wavelength limits. Confidence is moderate
for prototype priority and insufficient for production qualification; the gaps
above could change the winner. See [decision.json](decision.json).

## Actual tool contribution

The current shared recorder captures MCP initialize, tools/list, seven calls,
raw structured/text results, input/export hashes, source revision and installed
versions. It exercises inspection of synthetic CSV and ORCA-parser fixtures,
Gaussian broadening (assumed 0.18 eV FWHM), CUBE inspection, and three exports:
one spectrum CSV and two offline HTML views. `verify_smoke` checks the plan,
responses and artifact integrity. A failed tool run exits nonzero and retains
its failure record; it is never converted into a library fallback success.

The fixtures are **smoke tests only**, with zero candidate-specific orbital runs.
Their 1,600-point envelope and oscillator-strength integral near 1.19 describe
synthetic numerical inputs, not window transmission or calibrated absorbance.
The wavelength display retains oscillator strength/eV. Signed colors indicate
field phase, not positive/negative charge. No quantum calculations, molecular
assignments, NTO pairings, bulk spectra or outdoor properties are generated.

The material decision uses supplier evidence and explicit requirements only.
The absence of candidate orbital data does not require inventing a molecular
calculation: no justified decision value has been demonstrated for this selection.

## Forma proposal and validation

The unmodified `HardwareIntermediateRepresentation` at
[`ffd6772`](https://github.com/caid-technologies/Form-OSS/blob/ffd6772d54fa410e46910890434572333026e395/forma_core/workspaces/projects/models.py)
was recovered from an authorized source archive and loaded with Pydantic 2.13.5.
Its version is **0.2**. The ZIP's Git archive comment pins the full revision;
source/archive hashes and the three model/doc/version files' equality with the
saved `510582e` snapshot are recorded in [schema-provenance.json](schema-provenance.json).
Live repository retrieval returned 404; current live-branch equivalence is unknown.

[material-entry.proposed.json](material-entry.proposed.json) contains a window-only
IR proposal: one shared part definition, physical instance **W1**, and a matching
quantity-one BOM row. Optical requirements, evidence references, null unknowns and
qualification state use the actual free-form instance `configuration` field.
There is no typed optical acceptance subsystem. No housing or gasket part was invented.

**Actual Pydantic validation and local JSON round trip passed**, retaining supplied
fields, evidence IDs and nulls. Three invalid BOM cases were rejected by the real
model. [forma-model-check.json](forma-model-check.json) binds that result to the
exact proposal bytes and loaded sources. CI validates against the exported full
[JSON Schema](hardware-ir.schema.json) and checks part/instance/BOM relationships.
The canonical [proposal JSON](hardware-ir.proposed.json) is the exact serialized
file from that Pydantic check; replay verifies its hash before exporting it.
It does **not** rerun the external Forma runtime; `verify_forma.py` does that when
an authorized source checkout is available.

`is_valid=false`, a critical qualification finding, and `production_release=false`
survive serialization. The exported `hardware-ir.proposed.json` is structurally
checked, not design-approved. **No hosted import or application round trip occurred.**
Target-project integration and physical qualification remain separate blockers.

## Reproduce and review

From the repository root, Python 3.11+:

```bash
python -m pip install -r requirements.txt
python -m pytest -q
python benchmarks/MAT-01/reproduce.py --output .benchmark-runs/MAT-01
```

Use a fresh output directory. Read `benchmark-report.md`, `assessment.json`,
`manifest.json`, `hardware-ir.proposed.json`, `run.json`, and `assessment-inputs/`
together. Exports remain under `exports/`. The manifest identifies all research
snapshots and output hashes; `run.json` records actual protocol calls, versions,
source hashes and failures. CI publishes this bundle plus JUnit results as
`MAT-01-evidence-<run>-<attempt>` (30-day retention).

To independently repeat the **actual Forma model** check:

```bash
python benchmarks/MAT-01/verify_forma.py --source /path/to/pinned/Forma-OSS --output .benchmark-runs/MAT-01-forma
```

Use the documented source revision and Pydantic version for exact schema-byte
reproduction. No service credentials are required. No browser visual inspection
is claimed; automated checks cover file contents, protocol results and numerics.

[handoffs.json](handoffs.json) records five manual handoffs, including the testing
and import steps still pending. [friction.json](friction.json) records seven gaps
with evidence, impact and verifiable reusable capabilities. Historical MCP and
publication blockers are distinguished from current scientific/integration gaps.
Full-task time/cost were not measured.

The prior October 4 research is retained through [recovery.json](recovery.json).
The old copied runtime, library fallback results and megabytes of generated HTML
are not part of the new source change. This implementation reuses the current
shared runner and publishes fresh evidence, without modifying scientific tools.
