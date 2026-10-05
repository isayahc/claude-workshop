# SEMI-01 — 650 V robotic power switching

Addresses [issue #12](https://github.com/isayahc/claude-workshop/issues/12).

**Recommendation: use SiC as a provisional development baseline if the intended application is a hard-switched robotic motor drive. Retain silicon and GaN for a comparison at the actual operating point. No device or operating voltage is approved.** This is an **Assumed** engineering priority, informed by manufacturer servo-drive guidance [S2], not a numerical ranking. The issue does not specify the topology, load, switching frequency, cooling or meaning of “650 V.”

If **650 V is the DC bus**, do not simply buy a 650 V switch: regeneration, tolerance and switching overshoot must fit an explicitly reviewed device envelope. Reopen the voltage class, including higher-rated SiC and silicon alternatives; 1200 V is a candidate class to evaluate, not an automatic approval. If **650 V is the device class**, the permissible bus still has to be determined. A multilevel converter also requires an explicit per-switch stress and fault analysis; do not assume each switch sees half the bus.

**For commercial module selection, new DFT is not required. For new bulk band-structure, DOS or defect claims, periodic solid-state evidence is required; the molecular-orbital workflow is insufficient.** No periodic, molecular, circuit or thermal simulation, device measurement, or hardware energization was performed for this benchmark.

## 1. Evidence and decision boundary

| Classification | Available evidence | Permitted use |
| --- | --- | --- |
| Observed | Issue #12 requests a 650 V power module for a robot and three technology families. | Preserve the requirement and missing context. |
| External knowledge | Eleven manufacturer/documentation source records in [sources.json](sources.json), with access dates, locations and limitations. | Establish technology context, actual catalog examples and upstream capabilities. |
| Assumed | Hard-switched motor-drive scenario, SiC development priority, requirements and proposed workflow. | Guide the next investigation; not an approved architecture. |
| Observed, software only | Actual stdio MCP responses and one exported synthetic CUBE view when the reproduction command runs. | Verify inspection/export capability, never establish semiconductor properties. |
| Derived | The screening module processes the supplied inputs and retains unknown gates. | No numerical device ranking, loss or junction temperature is generated. |

The supplied values in [design.json](design.json) leave bus, stress, current, frequency, thermal conditions and margin policy unresolved. The generated assessment keeps the final technology, part number, approved bus/current/frequency, losses and junction temperature null and `release_allowed=false`.

## 2. Material science versus commercial devices

These are **External knowledge**, illustrative bulk values from TI's training comparison, slide 3 [S1]. Its temperature, crystal orientation, doping and uncertainty are not specified. Retain the original units; these are not measurements of our candidate devices and are not inputs to the executable screen.

| Descriptor | Si | 4H-SiC | GaN |
| --- | ---: | ---: | ---: |
| Band gap, eV | 1.12 | 3.26 | 3.4 |
| Critical field, MV/cm | 0.3 | 3.0 | 3.3 |
| Electron mobility, cm²/(V·s) | 1400 | 900 | 990–2000 |
| Thermal conductivity, W/(cm·K) | 1.3 | 3.7 | 1.5 |

**Engineering interpretation:** these descriptors explain why wide-bandgap devices merit evaluation; they cannot supply a packaged transistor's loss, voltage rating or allowable temperature. Bulk mobility is not channel mobility in a processed MOS interface or a particular GaN heterostructure. A thermal conductivity is not package thermal resistance. Band gap is not a drain-voltage limit. Compare the full device and cooling path, not a weighted score of this table.

### Commercial comparison snapshot — October 5, 2026

The following are **catalog comparators**, not a BOM or an exhaustive family comparison. Different die sizes, packages, architectures and test conditions prevent direct loss ranking.

| Technology / example | Sourced device information | Decision consequence |
| --- | --- | --- |
| Si: Infineon **IPW65R041CFD7** | 650 V superjunction MOSFET, PG-TO247-3. RDS(on) 34 mΩ typical / 41 mΩ maximum at Tj=25 °C, VGS=10 V, ID=24.8 A. Junction limit 150 °C. [S3] | Keep as a silicon comparator, especially if resonant operation is intended. For a motor inverter, also compare a suitable Si IGBT once current and frequency are known; this single SJ part does not represent all silicon. |
| SiC: Wolfspeed **C3M0060065K** | 650 V MOSFET, TO-247-4 with Kelvin source. RDS(on) 60 mΩ typical / 79 mΩ maximum at TC=25 °C, VGS=15 V, ID=13.2 A. Junction limit 175 °C. [S4] | Provisional family baseline; this part is not selected. Its 37 A at TC=25 °C becomes 27 A at TC=100 °C under the specified gate/junction conditions. Neither is an approved module current. |
| GaN: TI **LMG3522R030** | 650 V GaN power stage with integrated driver, top-cooled 52-pin VQFN. **38 A recommended RMS** differs from **55 A absolute maximum**. RDS(on) is 26 mΩ typical / 35 mΩ maximum at TJ=25 °C, VIN=5 V under section 5.5 conditions. Junction limit 150 °C. [S5] | Evaluate for a compact switching stage after layout, reverse-conduction, cooling and protection review. The external supply drives an integrated driver; it is not an exposed GaN gate-bias prescription. |

TI distinguishes switching, off-state and surge voltage stress and does not recommend this GaN part for continuous non-switching voltage stress. Its surge ratings do not authorize a higher continuous bus. Absence of a p-n body diode does not eliminate reverse-conduction/dead-time loss. [S5 §§7.3.1–7.3.3]

All three official product pages showed **Active** status [S6–S8]. That establishes a catalog listing, not stock, lead time or procurement approval. Infineon's page displayed **4.07** under **“Budgetary Price €/1k”** [S6]; its displayed basis is preserved without inventing a normalized project quote. Comparable quotes for the three devices and the full subsystem are absent. No total-cost winner is established. Include driver, cooling, filtering, magnetics, assembly and validation costs when comparing alternatives.

### What changes the recommendation?

- **Assumed motor-drive case:** begin the SiC study, with a silicon IGBT/MOSFET baseline. Manufacturer servo-drive guidance identifies both SiC and IGBT alternatives [S2]. Confirm motor cable/dv/dt, regeneration and fault behavior before optimizing switching speed.
- **Assumed compact high-frequency converter:** prioritize a GaN comparison if its integrated drive, thermal path and application envelope fit. TI lists vendor simulation resources [S8]; none was executed here.
- **Assumed cost-led or lower-frequency case:** retain silicon if matched losses, cooling and actual total cost win. No universal frequency or cost crossover is claimed.
- **Actual 650 V bus:** the three 650 V examples have no established headroom. Start voltage-class/topology selection again.

## 3. Required engineering evidence

**Proposed evaluation**, not measured results: obtain worst-case voltage/current waveforms and matched vendor models across gate drive, temperature, frequency, duty cycle, commutating device and parasitics. Preserve typical versus guaranteed values and model validity ranges.

For a MOSFET at an appropriately modeled temperature, conduction loss can be estimated by averaging `i(t)^2 * RDS(on,T)` during conduction. At a fixed operating point, `fs * (Eon + Eoff)` is a switching-loss approximation only when energy definitions and test conditions match. Integrate varying operating points; include reverse conduction, recovery/output-capacitance energy, gate/auxiliary power and snubber loss without double-counting energies already included in Eon/Eoff. An IGBT needs its own conduction model. None of those matched inputs exists here.

Iterate electrical loss with the package/interface/heat-sink thermal network and transient thermal impedance over the mission profile. A datasheet Tj maximum is a limit, not a predicted operating temperature. Validate vendor models with double-pulse and thermal measurements, then examine faults, parasitic turn-on, dead time, isolation, EMI and motor/cable compatibility. The source-specific limits remain authoritative; no standard spacing, gate voltage, derating factor or short-circuit time is invented for the unspecified module.

`orbital_viewer.semiconductor_screen` implements only **necessary catalog-voltage headroom arithmetic**. It requires a worst-case drain-peak quantity in volts, uncertainty, conditions, non-assumed provenance and an explicit fraction below the catalog voltage class. It rejects nominal-bus/band-gap substitution, booleans, nonfinite values and invalid bounds. An overlapping uncertainty interval stays unknown. A pass cannot qualify a device, select a part or clear the other gates. Caller evidence IDs are not independently authenticated by the module.

## 4. Periodic calculations and artifacts

The optional material-research route in [workflow.json](workflow.json) is **proposed, not executed**. It is separate from the commercial-device route. A molecule-sized cluster may answer a local chemical question after validation; it does not establish the bulk band dispersion of Si, a specified SiC polytype, or a GaN heterostructure.

| Requested artifact | Required upstream evidence / legitimate use | What it does not establish |
| --- | --- | --- |
| Band structure | Crystal/polytype, lattice/positions, strain/doping model, periodic SCF and bands, reciprocal units/k-path, occupations and energy reference. QE `bands.x` handles upstream band outputs [S9]. Validate the gap method against appropriate evidence. | A molecular HOMO–LUMO gap cannot replace E_n(k); a band plot is not a transistor voltage rating. |
| DOS / PDOS | Converged k-mesh, broadening/integration choice, units/normalization and projection basis. QE `dos.x` / `projwfc.x` are upstream capabilities [S10]. | Molecular oscillator-strength CSVs cannot serve as electronic DOS. PDOS weights are not unique chemical populations. |
| Charge density | Field kind, units, lattice, grid, charge/spin normalization, pseudopotential/all-electron convention and calculation hashes. | Signed orbital phase colors do not represent charge sign. |
| Wavefunctions | Band, k-point, spin, occupation, normalization, gauge and real/imaginary components where needed. | A real scalar CUBE does not preserve a general complex Bloch state. |
| Effective masses | Converged local band curvature near identified extrema, reciprocal-coordinate conversion, tensor/directional fit and uncertainty. | One mass is not mobility; scattering and temperature/doping information are missing. |
| Defect states | Converged defect supercell, charge/spin states, chemical potentials, finite-size corrections, energy alignment and suitable gap treatment. | A pristine-cell gap does not establish trapping, leakage or device lifetime. |

Before those outputs: converge geometry, pseudopotential/basis, cutoff and k-grid, preserve engine version/input hashes and failed jobs, and assess method sensitivity. Transport claims additionally need a validated scattering/transport treatment; thermal-conductivity claims need phonon/thermal-transport or measured evidence. Device breakdown and switching additionally depend on structure, interfaces, field distribution, gate drive and packaging; periodic DFT alone cannot qualify the module.

## 5. Orbital Studio usefulness and limits

**Observed from the repository:** the five tools inspect CUBE/transition data and export views. They contain no band/DOS, periodic solver, transport, TCAD, circuit-loss or thermal solver. No matching CAID/Orbital Studio connector was returned by this session's available-tool discovery; the repository's actual stdio server supplies the software checks.

`inspect_cube` can check a compatible scalar grid's dimensions, axes and range. `export_orbital` can illustrate an appropriately identified signed scalar field, but its current caveats describe wavefunction amplitude and its bond display is distance-based. It does not carry lattice/PBC, k-point, field-kind or complex-wavefunction semantics. Do not use it as a validated density or periodic-material viewer.

**Specific format trap:** QE `pp.x` can write Gaussian CUBE, but `plot_num=7` produces `|psi|²`; Gamma-point `lsign` produces signed squared modulus, not raw amplitude. Its other field options include charge and potential [S11]. A readable CUBE is not automatically the quantity Orbital Studio labels. A field-aware adapter/viewer and provenance sidecar are needed before scientific reuse.

The [plan](plan.json) exercises **only `inspect_cube` and `export_orbital`**, on the existing explicitly synthetic scalar fixture. All five tools are discovered; the three optical tools are intentionally unused. There is no real semiconductor field available. This satisfies a software capability check and documents why scientifically relevant periodic/device execution remains blocked; it is not evidence that Orbital Studio is sufficient for selecting power semiconductors.

## 6. CAID requirements and handoffs

[requirements.json](requirements.json) records **12 unresolved requirements** covering voltage, topology/load, losses/frequency, cooling, drive, faults, isolation, EMI/motor interface, packaging, procurement, optional scientific provenance and release. Each has an owner, intended Hardware IR fields and required verification evidence. [workflow.json](workflow.json) assigns **six handoffs** covering all requirements and identifies reusable platform gaps.

[hardware-ir.proposed.json](hardware-ir.proposed.json) is a **requirements-only proposal**: empty part definitions/components/BOM, explicit unknown values under `assembly_metadata.semi01`, critical qualification finding, `is_valid=false` and `production_release=false`. No footprint, wiring, CAD model or build-ready module is claimed.

Reproduction validates it against the existing, unmodified [pinned Forma 0.2 JSON Schema](../MAT-01/hardware-ir.schema.json) and checks source/requirements linkage and preservation of nulls. Compatibility is scoped to revision `ffd6772d54fa410e46910890434572333026e395`; this run does not repeat Pydantic model validation, verify the live schema or import into a Forma project. In particular, absent numeric schema defaults (operating voltage, estimated cost/current) must not become evidence. A future application adapter must preserve the explicit unknowns and use `exclude_unset=True` where appropriate.

Reusable gaps are condition-aware device-data ingestion, operating-point loss/thermal/protection evaluation, periodic/defect artifact schemas, field-aware visualization, vendor-model orchestration, comparable procurement evidence, and evidence-linked CAID import/release handling. These are documented requirements, not claims that this benchmark implements those platforms.

**Confidence:** high in the identified tool/evidence boundary; conditional in the SiC development priority; insufficient evidence for a final device, quantified performance or procurement decision. Main friction is the missing operating point and mismatched supplier conditions, followed by absent scientific artifacts and live application integration.

## 7. Reproduce and review

From the repository root, in PowerShell or a standard shell with Python 3.11+:

```text
python -m pip install -r requirements.txt
python -m pytest -q --junitxml=.benchmark-runs/test-results.xml
python benchmarks/SEMI-01/reproduce.py --output .benchmark-runs/SEMI-01-local
```

Use a fresh output directory. The runner refuses overwrite, starts the actual MCP server, validates the exact two-call plan and response schemas/text, checks input/export hashes, runs the voltage screen, validates the pinned IR schema and records source/bundle hashes. CI preserves the report, six input manifests, raw responses, synthetic HTML, assessment, schema/provenance, mapping result and JUnit results.

Exit success means evidence processing passed. Inspect the actual `run.json`, `assessment.json`, `mapping-check.json` and `evidence-manifest.json`; the plan is not an execution receipt. No browser-render verification is claimed. Upstream simulation, material measurements, physical module validation and CAID application import remain unperformed.

## Sources

Full URLs, versions, access scope and limitations are in [sources.json](sources.json). Bracketed IDs above resolve to its records: S1 material context; S2 servo-drive guidance; S3–S5 exact device datasheets; S6–S8 dated commercial listings; S9 bands; S10 DOS/PDOS; S11 field semantics. These external sources are separate from the benchmark's synthetic MCP evidence.
