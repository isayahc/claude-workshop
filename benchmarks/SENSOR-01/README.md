# SENSOR-01 — 300 nm UV detector

Addresses [issue #10](https://github.com/isayahc/claude-workshop/issues/10).

**Decision: proceed to a reviewed COTS prototype; do not release a calibrated instrument.**
A filtered SiC photodiode with a transimpedance amplifier (TIA), ADC and I2C host
interface is a credible development path. Absolute irradiance range, detection
limit and accuracy remain **unknown**, not zero. No material-specific quantum
calculation, physical measurement, CAD assembly or CAID import was performed.

The four evidence classes used here are **Observed** (actual tool/file output),
**Derived** (explicit arithmetic, including conditional results from assumptions),
**External knowledge** (identified primary source), and **Assumed** (a proposed
setting or requirement awaiting validation). A tool returning a vendor statement
does not make that statement an independently measured material property.

## 1. Proposed sensing stack and scientific evidence chain

```text
Incident light
  -> aperture / near-normal-incidence baffle
  -> 300 nm bandpass filter, Edmund Optics #67-749
  -> SG01S-18S SiC photodiode, nominally zero bias
  -> LMP7721 transimpedance amplifier about a buffered 1.0 V reference
  -> ADS1115 differential ADC: TIA_OUT minus VREF
  -> I2C -> existing 3.3 V microcontroller
```

**External knowledge [D1, D2]:** The detector manufacturer's response graph is
labelled 4H SiC. Its datasheet gives a 0.06 mm² active area, typical peak
responsivity 0.160 A/W **at 280 nm**, a 221–358 nm interval at 10% of peak, and
15 pF capacitance. The plotted response includes 300 nm. These support a detector
candidate, not a lot-specific value of responsivity at 300 nm. The product page
also reports a 3.26 eV SiC bandgap in a linked publication abstract.

**Derived [N1, issue requirement]:** With exact SI constants,

`E = h c / lambda = 4.13280661444 eV at 300 nm`.

That energy exceeds the cited gap, an energetic eligibility check rather than a
calculated optical transition. **Engineering inference:** photogenerated carrier
collection is the selected mechanism; actual absorption, transition matrix
elements and carrier collection cannot be proved by a bandgap comparison alone.
The manufacturer's spectral-response evidence is more directly useful for this
COTS selection than an invented molecular HOMO–LUMO diagram.

**External knowledge [F1]:** The selected filter is nominally 300 nm, with a
+3/−0 nm center tolerance, 10 ±2 nm FWHM, specified at 0° incidence. Its listed
minimum transmission is >15% and average blocking optical density is ≥4.
Neither is a lot-specific `T(300 nm)` or a pointwise guarantee against every
out-of-band wavelength. Its mounted diameter is 12.5 mm, clear aperture 9 mm,
and thickness 3.5 mm. The listed operating range ends at +50°C.

**Assumed:** use that filter as the initial narrow-band option; measure the
installed passband and rejection before qualification. It is not a rectangular
295–305 nm response, a spectrometer, a solar-blind guarantee, or a UV Index sensor.

The evidence chain is therefore:

1. Manufacturer response and filter specifications support a candidate stack.
2. Exact photon-energy and conditional electrical calculations support sizing.
3. Lot-specific optical curves and prototype measurements establish the real transfer function.
4. Traceable calibration, uncertainty and acceptance tests are needed for release.

Successful synthetic orbital/spectrum visualization is **not** a link proving
that this detector works; it is separately recorded software evidence.

## 2. Initial BOM

All component choices and quantities are **Assumed engineering proposals**;
manufacturer facts retain their external source IDs. This is not a purchase order
or a fabrication-ready assembly, and no prices or stock claims are made.

| Item | Qty | Proposed part or requirement | Qualification still required |
|---|---:|---|---|
| UV detector | 1 | sglux SG01S-18S [D1, D2] | Lot response near 300 nm; confirm pin/case mapping |
| Bandpass filter | 1 | Edmund #67-749 [F1] | Lot transmission, leakage, angle and temperature response |
| TIA amplifier | 1 | TI LMP7721 [A1] | Input common mode, output loading, leakage, noise and stability at 3.3 V |
| ADC | 1 | TI ADS1115 [A2, A3] | Package selection, input drive/filtering and firmware configuration |
| Bias/reference circuit | 1 circuit | Low-noise buffered 1.0 V node; part selection pending | Must source/sink diode and ADC-related loading; noise budget and startup behavior |
| Feedback resistor | 1 fitted | 1 MΩ **or** 10 MΩ; proposed low-temperature-coefficient, 0.1% option | Actual tolerance, leakage and resistor noise |
| Feedback capacitor | 1 fitted | 10 nF with 1 MΩ, **or** 1 nF with 10 MΩ | Proposed C0G where practical; stability/settling measurement |
| ADC input/rail filtering | 1 set | Output-side RC, bypass and bulk capacitors | Values after switched-capacitor drive and anti-alias analysis |
| I2C interface | 1 set | SDA/SCL pull-ups, address strap, power/ground connector | Bus voltage, capacitance and host compatibility |
| Analog PCB | 1 | Short sensitive trace, guard, cleaned leakage-controlled layout | No solderless breadboard qualification; contamination/humidity tests |
| Optical housing | 1 | Opaque baffle, filter retention, detector alignment and dark cap | Mechanical tolerances and stray-light tests |
| Microcontroller | 1 host | Existing 3.3 V MCU with I2C | Host selection/firmware external to this repository |
| Calibration equipment | Test only | Traceable UV reference, characterized source/monochromator and electrical injection fixture | Not included in the sensor BOM or claimed available |

## 3. Signal conditioning, power and measurable range

### Circuit proposal

**Assumed:** run the amplifier and ADC on a regulated 3.3 V rail. Hold the
non-inverting amplifier input and photodiode anode at a low-impedance 1.0 V bias
node; connect the cathode to the summing input, with `Rf || Cf` feedback. The
photodiode is nominally at zero differential bias. Verify the physical diode
polarity before layout. This orientation targets `Vout ≈ Vref + Iphoto Rf`.
The bias node is not an external ADC voltage-reference input; ADS1115 has its
own internal reference [A2].

Measure `AIN0 = TIA_OUT` against `AIN1 = VREF`, select ±2.048 V full scale and
initially 128 samples/s. Keep **each** ADC input inside 0–3.3 V during normal
operation; a differential full-scale setting does not permit negative pin
voltages. Startup, fault protection and common-mode limits also need review [A2].

**Derived, conditional on proposed headroom:** using a 3.0 V output ceiling and
1.0 V bias allows 2.0 V positive excursion. The 16-bit ±2.048 V code width is
62.5 µV. The code caps headroom at the smaller of amplifier allowance and the
largest positive ADC code; it does not assume every full-scale setting is usable.

| Population option (Assumed) | Ideal current headroom (Derived) | Ideal current/code (Derived) | Feedback RC pole (Derived) |
|---|---:|---:|---:|
| 1 MΩ ∥ 10 nF | 2 µA | 62.5 pA | 15.9155 Hz |
| 10 MΩ ∥ 1 nF | 200 nA | 6.25 pA | 15.9155 Hz |

Equations: `Iheadroom = excursion/Rf`, `Icode = LSB/Rf`,
`fRC = 1/(2 pi Rf Cf)`. These are alternative resistor/capacitor populations,
not an unqualified high-leakage gain-switch circuit. The RC pole alone proves
neither closed-loop stability nor system bandwidth. ADC code width is **not**
noise-free resolution, minimum detectable current or an optical detection limit.

### Power

**External knowledge [A1, A3]:** LMP7721 supports 1.8–5.5 V operation and lists
1.3 mA typical supply current; its typical specifications are generally at 5 V,
25°C. ADS1115 supports 2.0–5.5 V and lists 150 µA in continuous conversion.
**Assumed sizing estimate:** reusing those typical currents at 3.3 V gives about
4.8 mW for those two ICs only. This is not a guaranteed 3.3 V measurement or a
complete board budget: reference/buffer, pull-ups, regulator losses and MCU are
excluded. Validate rail transients and actual current; no battery-life claim is made.

### Optical range and calibration boundary

For spectral irradiance `E_lambda` in W m⁻² nm⁻¹, a proposed transfer model is

`Iphoto = A integral[E_lambda(lambda) T(lambda,angle,temp) R(lambda,temp) G(lambda,angle) d lambda]`.

`A` is detector area, `T` filter transmission, `R` detector responsivity (A/W),
and `G` the characterized geometric throughput. Units yield amperes. A known,
sufficiently narrow 300 nm source can permit a point-response approximation;
a broadband field generally cannot. Source spectrum and calibration geometry
must therefore accompany any conversion to irradiance.

**Unknown:** actual `R(300 nm)`, installed `T(300 nm)`, noise spectrum, dark drift,
linearity, saturation under the intended source, uncertainty and calibrated W/m²
range. The 280 nm peak value is deliberately excluded from the sizing calculator.
A manufacturer's wavelength interval is not an irradiance range. No optical
minimum/maximum, accuracy percentage or detection threshold is claimed.

**Assumed firmware contract:** return raw signed ADC code, gain/configuration ID,
timestamp, saturation and calibration-valid flags. Subtract an experimentally
established dark baseline and apply an identified calibration only after it
exists. Do not emit a plausible-looking W/m² value from an absent coefficient.
Measurement bandwidth, averaging, response time and detection criterion must be
part of that calibration, not silently changed by firmware.

## 4. Mechanical and optical arrangement

**Assumed:** start with a 30 ×30 ×20 mm envelope, filter normal aligned with the
photodiode normal, a short opaque baffle, and a removable dark cap. This is a
packaging target, not generated CAD or demonstrated fit. Mount the filter in its
retaining ring without stressing it, center the active area behind the clear
aperture, and characterize field of view rather than equating aperture to detector
area. Specify datums, tolerances and light-tight joints in the later CAD drawing.

Keep any cover/window out of the optical path unless its 300 nm transmission is
qualified. Separate the sensitive node from digital switching and avoid placing
an uncharacterized coating or adhesive over the active optical path. Treat
filter temperature capability [F1], not the diode's higher material capability,
as a constraint on the assembly. Angle/temperature shifts and stray light are
explicit validation gates, not simulated results.

## 5. Required electronic-structure artifacts and Orbital Studio handoff

A new electronic-structure calculation is **not required to justify testing a
commercial detector** with manufacturer spectral evidence. It would be required
for a material-specific microscopic explanation or a newly designed detector.
No such inputs or calculated outputs were supplied in this benchmark.

| Missing input/calculation | Suitable engine class and required output | Orbital Studio path / boundary |
|---|---|---|
| Actual SiC polytype, lattice, orientation, dopants, defects, strain and surface/passivation | Validated periodic structure (CIF/POSCAR or equivalent), provenance and device stack | Structure acquisition is upstream; do not substitute a molecule |
| Converged ground-state bands/wavefunctions | Periodic DFT, e.g. Quantum ESPRESSO; functional, pseudopotentials, cutoff/k-mesh/band convergence, eigenvalues and raw wavefunctions | No engine execution tool exists here |
| Optical transition strength/absorption near 4.13 eV | Optical matrix elements and dielectric tensor [Q1]; validated gap treatment; GW/BSE if justified [Q2]; phonon-assisted treatment where needed | A bandgap alone is insufficient; no fabricated transition CSV |
| Device carrier collection | Transport/device model with junction, thickness, contacts and recombination inputs | Absorption is not external responsivity; drift-diffusion/TCAD and experiment are separate |
| Selected real scalar field for visualization | Truthfully exported CUBE with field kind/units, cell, origin, axes, band/k/spin metadata and source hashes | `inspect_cube` then `export_orbital`; no automatic complex-periodic-field interpretation |
| Actual finite-system excited-state transitions, only if that is genuinely the model | Energy in eV and dimensionless oscillator strength, with calculation provenance; supported ORCA output or CSV | `inspect_transitions`, `broaden_spectrum`, `export_spectrum` |

**External knowledge [Q1, Q2]:** the cited periodic postprocessor exposes optical
matrix elements/dielectric output, while the BSE workflow requires prior
electronic structure. Choosing a method is an engineering/scientific proposal,
not evidence that it was run or converged.

Never rename responsivity in A/W, measured transmission, bulk absorption or a
periodic dielectric spectrum to `oscillator_strength` to bypass the importer.
Nor does a molecular TD-DFT excitation list automatically represent a bulk SiC
junction. A periodic spectrum needs its own typed importer, units, normalization
and metadata. A CUBE image alone does not establish an allowed transition;
wavefunction sign is not charge, and an NTO pair was neither required nor inferred.

**Observed repository contract [R1]:** current spectrum broadening is normalized
in energy space. A wavelength plot still carries intensity in oscillator-strength
per eV; it is not absorbance or detector sensitivity. Thus neither a broadened
fixture nor a selected line near 4.13 eV can become a detector calibration.

## 6. Execution and artifact record

| Activity | Inputs | Output / limitation |
|---|---|---|
| GitHub issue, tree, documentation and PR reads | Issue #10; default revision `3d326f4d516bd6851c6e6eeb8cc68b1a0f361800`; shared recorder from PR #15 | Observed contract and synthetic fixture provenance |
| Plugin discovery | CAID / Orbital Studio search | No relevant connected action was returned; no CAID call or import claimed |
| Primary-source web reads | Sources below | External manufacturer/engine evidence, not new measurements |
| PDF visual inspection | Detector datasheet p.2; ADC datasheet pp.4,15 | Response graph/specifications and ADC limits inspected; unsuccessful detector pinout-page renders leave pin verification manual |
| Authoring-container Python | New plan, design record and tests | Arithmetic/contract checks run locally; MCP dependency absent, so local integration check is skipped |
| Dependency-backed CI | Full repository, declared synthetic files and `plan.json` | Runs full suite, real stdio MCP calls and arithmetic; actual status and counts live in the CI record, never assumed from this report |

The shared recorder is reused from PR #15. Its only conceptual extension is
optional, validated `unknown_quantities` so a sensor run does not report cure-dose
fields. All are forced to `null`; plans cannot override `release_allowed=false`.
Legacy PROCESS-01 plans retain their original missing-quantity names.

`plan.json` declares seven calls covering all five tools: inspect the CSV and
synthetic ORCA output, broaden the CSV, export CSV and wavelength HTML, inspect
the signed CUBE, and export its HTML. The existing examples are **synthetic
software fixtures, not SiC wavefunctions or absorption measurements**. Their
source blob hashes are checked before snapshotting. FWHM 0.18 eV and absolute
isovalue 0.5 are **Assumed display settings**, not material quantities.

A successful run creates `run.json` with the actual discovery schemas, raw MCP
responses, caveats, input/export hashes, package/code versions and timestamps;
three raw visualization exports; pinned input snapshots; and a warning. Numerical
spectral-area diagnostics are **Observed/Derived synthetic checks only**.
`design-preview.json` separately records photon energy, conditional headroom,
ADC code size, equations and input/implementation hashes. It never manufactures
missing calibration or quantum data. CI also preserves JUnit results and the
source design/report. A failed call records failure rather than success-shaped data.

## 7. Manual handoffs and confidence

| Handoff owner | Required input -> deliverable | Release gate |
|---|---|---|
| Detector/filter vendors | Exact parts/lots -> response and transmission curves with conditions | No substitution of peak sensitivity or nominal passband for lot data |
| Analog engineer | Netlist, packages, reference selection -> schematic, pinout review, stability/noise analysis | Common mode, leakage, loading, tolerance and fault behavior |
| Mechanical engineer | Actual package drawings -> CAD, datums, aperture and tolerance checks | Fit, light-tightness, incidence and retention verified |
| Test engineer | Current injection and darkness -> offsets, linearity, noise, gain and saturation | Measured electrical range and uncertainty |
| Optical/metrology lab | Traceable 300 nm source/reference -> calibrated transfer and usable irradiance range | Source bandwidth/geometry and uncertainty recorded |
| Qualification engineer | Spectral, angle, temperature and time sweeps -> rejection/drift/response results | Intended environment and detection criterion satisfied |
| Firmware/CAID integrator | Approved circuit and schema -> raw readout, calibration flags, validated IR import | No invented units/calibration or assumed schema compatibility |
| Computational scientist, if needed | Actual structure/device stack -> converged raw artifacts and typed exports | Material-specific explanation remains separate from empirical calibration |

UV exposure testing belongs in an enclosed, reviewed laboratory setup; no exposed
source or physical test was operated in this work. This prototype report is not
an exposure-safety approval.

**Confidence:** high for basic detection feasibility based on manufacturer
spectral coverage; medium for this initial integration proposal; unestablished
for absolute sensitivity, detection limit, accuracy and manufacturing readiness.
The main friction is missing calibration and device/optics integration data,
not a missing decorative orbital image.

## 8. Proposed CAID / Hardware IR representation and reusable gaps

[`design.json`](design.json) is an **engineering sidecar proposal**, not a claimed
valid instance of an inspected CAID schema. The actual schema/version and import
capability were unavailable. Preserve these semantics during a real integration:

| Field family | Required semantics |
|---|---|
| Hierarchy/BOM | Stable component IDs, parent/child assembly, quantity, manufacturer/part and fit state |
| Mechanical/optical | Coordinate frames, normals, aperture, envelope, datums/tolerances, optical path and field of view |
| Electrical | Pin/net identities, rail/reference nodes, diode polarity, gain/configuration and ADC interface |
| Spectral transfer | Detector `R(lambda)`, filter `T(lambda,angle,temp)`, geometry and units; measured/computed provenance |
| Measurement | Measurand, raw/calibrated units, calibration ID, gain, bandwidth, timestamp, saturation/validity flags |
| Evidence | Claim classification, URI/hash, conditions, uncertainty, derivation dependencies and tool-run identity |
| Validation | Unmet requirements, handoff owner, test artifact and explicit release gate |

Reusable capabilities exposed by this case are: a typed spectrum/material-property
registry (not a forced molecular transition format); upstream calculation-job and
artifact adapters; unit-aware optical/electrical transfer composition; traceable
calibration/uncertainty handling; schema-validated CAID circuit/optical assemblies;
and execution evidence kept separate from engineering release. These apply across
sensors and materials; they are not detector-specific MCP commands or hardcoded
scientific answers.

## 9. Reproduce

From this PR's checkout, install the existing dependencies. Python 3.11+ is
required. Output directories/files must be new, preventing mixed or overwritten
evidence. This uses the local stdio server; no model key or password is needed.

```bash
python -m pip install -r requirements.txt
python -m pytest -q
python -m orbital_viewer.benchmark --plan benchmarks/SENSOR-01/plan.json --data-dir examples/mcp --output .benchmark-runs/SENSOR-01
python -m orbital_viewer.sensor_design --design benchmarks/SENSOR-01/design.json --output .benchmark-runs/SENSOR-01/design-preview.json
```

Windows PowerShell, without activating a virtual environment:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m orbital_viewer.benchmark --plan benchmarks/SENSOR-01/plan.json --data-dir examples/mcp --output .benchmark-runs/SENSOR-01
.\.venv\Scripts\python.exe -m orbital_viewer.sensor_design --design benchmarks/SENSOR-01/design.json --output .benchmark-runs/SENSOR-01/design-preview.json
```

Review the workflow run and downloaded `run.json`, not just the existence of this
plan. Required outcomes are real tool responses where inputs permit, explicit
upstream gaps, recorded handoffs, no unsupported scientific values, the prototype
engineering decision above and reusable capability gaps. Software checks can pass
while `release_allowed` remains false. Missing real material transitions are an
honestly blocked scientific subtask, not filled with the synthetic examples.

## Primary sources

Source IDs, review dates and locators also appear in `design.json`.

- **N1:** [NIST SI constants](https://www.nist.gov/si-redefinition/meet-constants).
- **D1:** [SG01S-18S datasheet, Rev. 6.4](https://download.sglux.de/photodiodes/SG01S-18S.pdf), p.2.
- **D2:** [sglux product/publications](https://sglux.de/en/product/sg01s-18s-en/).
- **F1:** [Edmund Optics #67-749 specifications](https://www.edmundoptics.com/p/300nm-cwl-10nm-fwhm-125mm-mounted-diameter/22416/).
- **A1:** [TI LMP7721](https://www.ti.com/product/LMP7721).
- **A2:** [ADS1115 datasheet Rev. E](https://www.ti.com/lit/gpn/ADS1115), pp.4,15 and input-drive guidance.
- **A3:** [TI ADS1115](https://www.ti.com/product/ADS1115).
- **Q1:** [Quantum ESPRESSO optical postprocessing](https://www.quantum-espresso.org/Doc/INPUT_pw2gw.html).
- **Q2:** [Yambo BSE workflow](https://wiki.yambo-code.eu/wiki/index.php/Two_particle_excitations).
- **R1:** [Pinned Orbital Studio MCP contract](https://github.com/isayahc/claude-workshop/blob/3d326f4d516bd6851c6e6eeb8cc68b1a0f361800/docs/mcp.md).
