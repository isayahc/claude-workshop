# PROCESS-01: photoinitiator-driven UV-curing station

Issue: [#13](https://github.com/isayahc/claude-workshop/issues/13).

**Engineering disposition: BLOCKED for material-specific wavelength selection and production release.** The issue supplies no photoinitiator identity, formulation, measured absorption, material-specific quantum calculation, cure-response data, or part requirements. A successful fixture run demonstrates the tools, not a working curing recipe. This is a bounded benchmark result, not a manufacturing-ready machine or a safety certification.

## 1. Illumination decision

**Assumed — proposed development architecture:** a fully enclosed, programmable LED flood-curing station with replaceable source heads, a fixed-height keyed part nest, calibrated work-plane radiometry, independent safety shutdown, and an automated exposure/cooling cycle. Loading is initially manual; material handling automation is a separate throughput decision.

**External knowledge:** commercial LED flood-curing source classes include nominal **365, 385, and 405 nm** emitters [S1]. These are candidate development options, **not the unidentified photoinitiator's absorption region or an approved wavelength**. 405 nm is violet light, not UV-A. Do not order a production head solely because its wavelength is common. The measured formulation response may require a different band or source class entirely.

**Engineering decision:** shortlist a source only after comparing its measured emission with the actual formulation's absorption and photochemical response, through the real optical path. Confirm the shortlist with cure coupons. No wavelength, optical wattage, irradiance, dose, exposure time, temperature limit, or production rate is approved by this benchmark. Those values remain `null` in every replay's `engineering_decision`.

## 2. Available evidence and actual tool exercise

**Observed — repository inspection:** `docs/mcp.md` explicitly identifies the files in `examples/mcp` as synthetic parser/visualization fixtures. They are not data for a named molecule. The [plan](plan.json) pins the three input Git blob hashes from repository revision `3d326f4d516bd6851c6e6eeb8cc68b1a0f361800`; the recorder refuses changed fixtures.

The recorder starts the actual `orbital_viewer.mcp_server` subprocess, initializes MCP, discovers tools, and makes these seven calls. It does not imitate the tools with replacement calculations:

| Call | Input and explicit setting | Purpose and scientific boundary |
| --- | --- | --- |
| `inspect_transitions` | `transitions.csv` | Observe synthetic energies, wavelengths and oscillator strengths; no molecular assignment |
| `inspect_transitions` | `synthetic-orca.out` | Exercise the ORCA parser; this is not an ORCA calculation |
| `broaden_spectrum` | CSV, FWHM 0.18 eV | Energy-space envelope; linewidth is an **Assumed** display parameter |
| `export_spectrum` | Same CSV/FWHM, CSV | Full numerical spectrum artifact with units |
| `export_spectrum` | Same CSV/FWHM, HTML, nm axis | Offline spectral visualization; ordinate remains f/eV |
| `inspect_cube` | `signed-field.cube` | Inspect the synthetic field's geometry and values |
| `export_orbital` | Same CUBE, isovalue 0.5 | Offline signed-field visualization; threshold is **Assumed**, source-defined amplitude |

**Execution evidence is `run.json`, not this call plan.** It records each actual MCP response, discovered schemas, success/failure, timestamps, Python/package versions, code revision and implementation hashes, copied input bytes and SHA-256 hashes, exported files and hashes, and returned caveats. A failed or interrupted tool run must not be reported as successful. `tool_execution_status` and `engineering_decision.status` are deliberately separate.

**Observed results** are taken only from successful tool responses. **Derived results** are the spectral area diagnostics: `absolute_error = abs(integrated_area - total_strength)` and, for nonzero total strength, `relative_error = absolute_error / total_strength`. Neither is a cure metric. A zero-strength spectrum has an undefined relative error, represented by `null`. Numerical output is generated at execution time, not invented in this report.

### Reproduce and obtain artifacts

From the repository root, with Python 3.11+:

```bash
python -m pip install -e '.[mcp,test]'
python -m orbital_viewer.benchmark --plan benchmarks/PROCESS-01/plan.json --data-dir examples/mcp --output .benchmark-runs/PROCESS-01
python -m pytest -q tests/test_benchmark.py
```

Windows PowerShell, without activation:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[mcp,test]"
.\.venv\Scripts\python.exe -m orbital_viewer.benchmark --plan benchmarks/PROCESS-01/plan.json --data-dir examples/mcp --output .benchmark-runs/PROCESS-01
.\.venv\Scripts\python.exe -m pytest -q tests/test_benchmark.py
```

Use a new output directory for each rerun; existing directories are never overwritten. No API key, password, hosted model or ORCA installation is needed. For the complete existing suite, install `-r requirements.txt` first, which also includes the UI dependencies.

The Tests workflow publishes `PROCESS-01-synthetic-evidence-<run-id>-<attempt>` containing `run.json`, the plan, input snapshots, a warning file, one spectrum CSV, and two offline HTML files. Open the spectrum HTML and orbital HTML only as **synthetic tool demonstrations**. Raw server exports are preserved unchanged and must travel with their provenance; their local `file:` URIs are not public download links. A failed workflow may publish partial evidence: inspect `tool_execution_status` and individual calls before citing it.

## 3. Scientific sufficiency and limitations

| Quantity | Classification and current conclusion | Data/calculation needed |
| --- | --- | --- |
| Photoinitiator absorption region | **Observed:** not supplied; fixture wavelengths do not answer it | Chemical identity, formulation/lot, concentration, solvent or matrix, optical thickness, measured UV-visible absorption/transmission and uncertainty |
| Relevant electronic transitions | **Observed:** no material-specific assignments supplied | Validated excited-state calculation with method/basis, charge, multiplicity, geometry, environment, state indices, transition contributions and/or explicitly identified NTO pairs and weights |
| Photochemical quantum yield | **External knowledge:** events per absorbed photon [S4]; not oscillator strength and not necessarily fluorescence yield | Yield for the specified initiating event versus wavelength and formulation conditions, or an empirical cure-response qualification route |
| Polymerization kinetics | **External knowledge:** conversion and network evolution require more than absorption [S5] | Conversion-versus-time measurements across irradiance, temperature, composition, thickness and atmosphere; relevant final-property tests |
| Required process dose | **Observed:** absent; cannot be extracted from the envelope | Qualified cure window and endpoints for the actual part/formulation, including allowable irradiance/time histories |
| Thermal effects | **Observed:** no thermal limits or exotherm supplied | Source electrical/radiant power, cooling requirements, material temperature limit and measured cure exotherm/temperature history |
| Manufacturing throughput | **Observed:** no handling times, batch size or yield supplied | Measured loading, verifying, exposure, cooling, unloading, availability and accepted-part yield |

**Observed — tool boundary:** Orbital Studio analyzes existing data. It does not run DFT/TD-DFT, produce electronic states, infer NTO pairing, determine radical formation, or model polymerization. Energies and oscillator strengths alone do not assign n→π*, π→π*, charge-transfer character, or intersystem-crossing/cleavage yields. No such assignment is made here. A manually labeled, verified state/orbital bundle must come from upstream chemistry analysis.

**Observed — spectrum semantics:** area-normalized Gaussian broadening is in energy space. The wavelength view remaps the horizontal coordinate using `hc/E`; its vertical units remain oscillator strength/eV, not per-nm density, molar absorptivity or calibrated absorbance. The fixed grid may undersample narrow features or truncate tails. Inspect the returned sampling warnings and area diagnostics. FWHM 0.18 eV is not a measurement of this material, and a Gaussian tail is not proof of useful curing at a candidate LED wavelength. The CUBE is not an NTO; colors represent signed amplitude, not charge. See [the MCP limitations](../../docs/mcp.md#scientific-limitations).

**External knowledge:** equal dose does not universally imply equal cure; a NIST study found reciprocity valid only over a finite exposure-power range for its verification material [S3]. Do not transfer that material's parameters to this process. Missing quantum-yield data blocks a predictive initiation calculation, but does not prohibit empirical process qualification using appropriate material-specific experiments.

### Engineering calculations — relationships, not populated results

**Derived, conditional:** with irradiance `I` in W/cm² at the actual cure surface, dose `H = integral I(t) dt` is in J/cm². For a constant, qualified irradiance, `t = H_target / I`. This is energy bookkeeping, not a polymerization model or proof of reciprocity. A single nominal LED wattage does not supply work-plane irradiance. Measure irradiance and uniformity after intervening optics; manufacturer radiometry guidance explicitly addresses cure-site transmission [S2].

**Derived, conditional:** for a stationary illuminated area, `P_at_part = integral_area I(x,y) dA`. Only for a uniform field does this reduce to `I * area`. Source optical power also depends on optical delivery losses. Require emission spectrum/bandwidth, work-distance maps, hot/cold output, dimming behavior, uniformity, stability, window transmission, sensor spectral calibration and uncertainty before sizing power. Do not substitute electrical input watts for optical watts.

**Derived, conditional:** an initiation-rate estimate would integrate `spectral_irradiance * photon_conversion * fraction_absorbed_by_initiator * initiation_quantum_yield` over wavelength. The fraction must belong to the initiator, not all absorbing constituents. Inputs must share compatible spectral units; an f/eV envelope is not a measured absorption probability. None of the required material functions is supplied, so the integral is not evaluated.

**Derived, assumed sequential batch cycle:** `ideal_parts_per_hour = 3600 * parts_per_batch / (load_s + verify_s + exposure_s + cool_s + unload_s)`. Accepted throughput additionally depends on measured availability and yield. It is not `3600 / exposure_s`, and a pipelined machine requires a different cycle model.

## 4. Initial machine/process specification and BOM

**All entries below are Assumed engineering proposals requiring detailed design and validation.** Quantities are an initial station architecture, not measured material properties. Ratings, dimensions, vendor part numbers, costs and procurement approval remain open.

| Assembly / initial BOM item | Quantity | Specification and release dependency |
| --- | --- | --- |
| Replaceable LED flood head with optics | 1 | Candidate band only; actual spectrum, cure-area irradiance/uniformity and distance qualified with the chosen resin |
| Matched driver and power supply | 1 set | Manufacturer-compatible current/voltage; hardware disable input, default-off behavior, fault feedback; no generic wattage estimate |
| Source cooling assembly | 1 set | Heatsink/interface/fan or vendor-required cooling; size from rated dissipation and duty cycle, prove cooling failure shutdown |
| Work-plane radiometer and matched detector | 1 set | Calibrated for selected spectrum and intensity; map cure plane, including substrates/windows; calibration traceability recorded |
| Process optical monitor | 1 | Validated correlation to worst-exposed cure site; drift/no-light detection, never inferred from drive current alone |
| Part and source temperature probes | 2 | Appropriate range, calibration and placement; source probe alone cannot establish resin temperature |
| Keyed nest, clamps and height datum | 1 set | Repeatable positioning with no required surface shadowed; mechanical envelope/tolerances await actual part CAD |
| Adjustable source mount | 1 | Setup adjustment with locking and recorded working distance; changing height invalidates the irradiance map |
| Opaque enclosure, lid and light-trap vents | 1 | Full emission-band containment; default no viewing window; inspect seams/vents and validate leakage under worst-case operation |
| Guard interlocks, independent safety relay and source energy isolation | 1 set | Safety-rated architecture selected by competent risk assessment; monitored feedback, fault detection and defined test procedure |
| Emergency stop, manual reset, status indicators | 1 set | Latching shutdown; closing lid or restoring power never restarts exposure; separate commanded-on and verified emission states |
| Process controller/HMI with isolated I/O and logging | 1 set | PLC or industrial controller for recipes/timing/logging; not the sole safety device; no LLM in the safety chain |
| Fused distribution, disconnect, protective bonding and wiring | 1 set | Qualified electrical design; driver/thermal/fault loads determine ratings |
| Spill tray and material-specific extraction provisions | 1 set | Chemical compatibility and ventilation determined from the actual SDS and exposure assessment; no assumed filter chemistry |

**Assumed positioning strategy:** a fixed nest is preferred for initial flat coupons. Complex parts need an occlusion review and measured dose on every required surface. Rotation/indexing, extra heads or alternative curing methods are conditional changes, not a claim that one flood head cures hidden surfaces. Avoid buying motors before part geometry and throughput justify them.

**Assumed thermal strategy:** separate head cooling from part temperature control. At steady state, head dissipation is approximately electrical input minus optical power leaving that head's boundary; enclosure absorption and resin reaction heat are additional thermal loads elsewhere. Verify the complete temperature history over the intended duty cycle. Do not infer a safe resin temperature from a cool LED heatsink. Overtemperature and cooling loss must disable the source independently of the UI.

### Control sequence and safety validation

**Assumed functional specification, not delivered control firmware:** `SAFE_OFF → LOAD → VERIFY → EXPOSE → COOL → COMPLETE → UNLOAD`. Exposure requires an independently healthy guard/safety chain, verified fixture, valid calibrated sensor, adequate cooling and an approved material-specific recipe. During exposure, accumulate measured dose while enforcing the qualified irradiance and temperature windows. Stop and latch a fault on lost light/sensor data, out-of-window irradiance, overheating, cooling failure, open guard, emergency stop, control watchdog or power loss. Retain the interrupted job record and quarantine the part rather than silently continuing an uncertain cure.

Hardware isolation must override software commands. Source-off verification and any required cooldown precede access. Demonstrate no automatic restart after lid closure, reset, app crash or power restoration. Validate faults, leakage and stopping behavior on the assembled equipment before operation; component labels do not establish whole-machine compliance. A competent safety/electrical review must determine applicable requirements and acceptance limits. No exposure limit, window optical density, safety integrity level or certification is invented here.

## 5. Handoffs and manual work

| Handoff | Sender → receiver | Required artifact / manual action | Gate |
| --- | --- | --- | --- |
| H1: problem definition | Product owner → materials/process engineer | Actual resin/initiator identity, SDS, formulation/lot, layer thickness, part CAD, required properties and throughput | Cannot select a material-specific band without an identified process |
| H2: quantum data | Computational chemist → Orbital Studio analyst | Validated calculation output/CSV and optional CUBEs; method, geometry, environment, state IDs and manually checked NTO identities/weights | Synthetic fixtures cannot substitute; upstream calculations are outside this server |
| H3: spectrum interpretation | Analyst → optical engineer | Unit-preserving exported spectrum, raw provenance and uncertainties, plus measured formulation absorption | Candidate compatibility only, not quantum yield or cure dose |
| H4: chemical response | Materials scientist → process engineer | Defined initiating-event yield where needed; measured conversion/cure-property matrix across wavelength, irradiance, time, thickness and atmosphere | Qualify the actual response; a predictive model is optional, empirical validation is not |
| H5: optical delivery | Optical engineer → mechanical engineer | Measured LED spectrum and work-plane maps, working-distance constraints, optical path/occlusion review | Freeze fixture and optical geometry only after coverage is demonstrated |
| H6: thermal load | Process/optical engineers → thermal engineer | Electrical/radiant power, duty cycle, exotherm and part/head temperature traces | Cooling design and trip thresholds await actual limits |
| H7: safe controls | Safety/electrical engineers → controls engineer | Risk assessment, independent shutdown design, sensor diagnostics and witnessed fault/leakage tests | No software-only safety claim or automatic restart |
| H8: CAID specification | Engineering owners → CAID artifact pipeline | BOM, geometry/interfaces, wiring, approved recipe and evidence-linked acceptance tests | No CAID tool was invoked in this session; this is a documented manual handoff, not a generated CAD artifact |
| H9: production feedback | Operator/quality team → process owner | Calibration IDs, material lot, geometry version, irradiance/time/temperature logs, defects and property tests | Requalify after material, source, geometry or process-window changes |

The engineer must define acceptance endpoints such as conversion, depth, mechanical performance, adhesion or residual material for the actual use case. Surface tack alone is not the specification. Coupon testing, calibration, detailed CAD/electrical design, safety validation and production trials remain manual/external work. No physical machine was built or operated by this benchmark.

## 6. Missing tools/data and reusable CAID capabilities

| Reusable capability gap | Proposed contract, not a one-off workaround |
| --- | --- |
| Scientific evidence envelope | Identity/lot, claim class, synthetic-versus-material scope, units, source hashes, method/environment, uncertainty, validity domain and approvals; this PR implements only a fixture execution record |
| Excited-state/orbital bundle | Stable molecule/state IDs, geometry frames, spin/method metadata and explicit NTO provenance/weights; importer must not infer labels from filenames |
| Typed spectral interchange | Distinguish transition strengths, energy/wavelength spectral densities, measured absorptivity, emission and action spectra; explicit Jacobian/conversion rules and calibration |
| Optical-to-process qualification | Measured dose-response/cure-depth/property data with irradiance, atmosphere, thickness and temperature validity windows; no generic absorption-to-cure shortcut |
| CAD-linked exposure coverage | Associate source/fixture transforms and calibrated irradiance maps with required surfaces, shadowing and tolerance envelopes |
| Thermal and safety requirement blocks | Separate LED heat, resin exotherm, allowable temperatures and validated shutdown requirements from ordinary recipe code |
| Artifact transport | Persist local MCP exports with provenance, hashes and shareable artifact references; never claim a local file URI is remotely accessible |
| Evidence-based release gates | Keep tool execution success distinct from scientific sufficiency and physical-machine qualification; prevent demo fixtures from filling production parameters |

**Observed friction:** plugin discovery did not return a relevant connected CAID/Orbital Studio integration in this session. The repository's local stdio MCP server is therefore exercised through the reproducible runner/CI, not a hosted CAID service. The authoring container lacks MCP dependencies and cannot download them; local contract checks and CI execution must be reported separately. Other friction includes local-only export URIs, missing calculation metadata in simple CSV, manual NTO attribution, and missing material/process inputs.

**Confidence:** high in the boundary that synthetic visualization cannot establish a cure recipe; execution confidence is determined by the specific recorded run and tests. The station architecture is a provisional engineering proposal. Material-specific performance, thermal sizing, throughput and safety compliance are unvalidated.

## 7. Acceptance mapping

The successful MCP run and its artifacts address actual tool exercise; Sections 2–3 enforce scientific provenance and missing calculations; Section 5 records handoffs; Sections 1 and 4 translate the result into an explicitly blocked engineering decision and initial BOM; Section 6 identifies reusable gaps. A green test run does not change the scientific disposition.

## Sources

External sources were consulted on October 3, 2026 (America/New_York). They support general distinctions or commercially available source classes, not the unidentified resin's properties.

- **S1 — Dymax, Flood Curing Systems:** manufacturer source for LED flood-system wavelength classes. No vendor cure-time claim is transferred to this benchmark. https://dymax.com/products/equipment/light-curing-equipment/flood-curing-systems
- **S2 — Dymax, ACCU-CAL 160 Radiometers:** manufacturer guidance on intensity/dose measurement and transmission to the cure site. This is not selection of a final detector or proof of calibration for the unknown source. https://dymax.com/products/equipment/light-curing-equipment/radiometers/accu-cal%E2%84%A2-160-radiometers
- **S3 — Higgins et al., Monitoring Fast, Voxel-Scale Cure Kinetics via Sample-Coupled-Resonance Photorheology:** primary research, finite-range reciprocity in the studied material. https://www.nist.gov/publications/monitoring-fast-voxel-scale-cure-kinetics-sample-coupled-resonance-photorheology ; DOI 10.1002/smtd.201800275
- **S4 — IUPAC Gold Book, quantum yield:** definition of event-specific yield per absorbed photon. https://goldbook.iupac.org/terms/view/Q04991/plain ; DOI 10.1351/goldbook.Q04991
- **S5 — NIST, Stochastic Network Growth Simulation for Photopolymerization:** first-party description of the separate initiation/propagation/reaction-diffusion modeling problem. https://www.nist.gov/programs-projects/stochastic-network-growth-simulation-photopolymerization
