# BAT-01 — High-voltage Li-ion electrolyte screening

Addresses [issue #11](https://github.com/isayahc/claude-workshop/issues/11).

**Decision: proceed with a literature-led comparison and an upstream calculation/test plan; do not select or release an electrolyte.** There is no defensible overall winner from the supplied inputs. Sulfolane (SL) is a proposed oxidation-focused research lead, not a qualified replacement. Keep a carbonate formulation as a control and consider an EC-free EMC/FEC comparator only after confirming that the electrode system makes that comparison relevant.

**No candidate-specific quantum calculation or battery measurement was performed.** All candidate oxidation/reduction potentials, orbital energies, barriers and transport properties remain unknown. The CUBE exercise is an explicitly synthetic **software** check, not electrolyte evidence. Passing CI never approves a cell, charger setting or BMS limit.

## 1. Scope and evidence ledger

Labels throughout this benchmark mean: **Observed** = returned by a tool or supplied input; **Derived** = arithmetic from those inputs; **External knowledge** = literature or another documented source; **Assumed** = proposal requiring validation. Observed does not mean independently measured or physically accurate.

| Class | What is actually available | Decision consequence |
|---|---|---|
| Observed | The issue requests a rechargeable Li-ion subsystem and an approximately **4.3 V cathode**. It supplies no candidate list, structures, formulation, electrode identities, operating temperature, redox data or experimental artifacts. The voltage reference is unspecified. | Preserve 4.3 V as an unresolved requirement, not a terminal charge-voltage instruction. |
| Observed | The repository has inspection/export tools and a synthetic scalar-field fixture; the shared recorder preserves actual MCP responses and artifact hashes. | Exercise available CUBE handling, while keeping it separate from scientific qualification. |
| External knowledge | Seven source records, with access limitations and applicability, are in [sources.json](sources.json). | Support qualitative comparison and method choice, not fabricated candidate values. |
| Assumed | EC, EMC, DMC, PC, SL and FEC are an author-proposed comparison set. FEC is included as an additive comparator rather than a neat-solvent winner. | The cell designer must confirm the actual candidate set and identities. |
| Derived | The supplied design produces six candidate assessments, with both intrinsic redox gates unknown for each. | There is no numerical redox ranking or approved formulation. |

The executable record is [design.json](design.json); the proposed, **unexecuted** upstream job graph is [workflow.json](workflow.json). `assessment.json` is generated from the design, not hand-entered evidence. `run.json` records actual MCP execution when the commands below run; a plan alone is not proof of execution.

## 2. Candidate comparison and recommendation

All statements in the evidence column are **External knowledge**, scoped to their sources. Proposed roles are **Assumed** engineering choices. No comparison below assigns a numerical stability window to a neat molecule.

| Candidate | Role in this study | Evidence and limitation |
|---|---|---|
| Ethylene carbonate (EC) | Baseline co-solvent | Established graphite-interphase role does not make EC universally preferable at a charged cathode. The Ni-rich study in S5 motivates an EC-free comparison. [S3, S5] |
| Ethyl methyl carbonate (EMC) | Linear-carbonate comparator | S5 supports a particular EMC/FEC formulation in NMC811/graphite cells, not neat EMC or an electrode-independent claim. [S5] |
| Dimethyl carbonate (DMC) | Co-solvent comparator | Included in studied carbonate and SL mixtures; mixture results cannot be assigned to DMC alone. [S3, S7] |
| Propylene carbonate (PC) | Conditional comparator | Graphite interphase compatibility can be problematic; salt/additive changes mean this is not a universal rejection. [S3] |
| Sulfolane (SL) | Oxidation-focused research lead | Published formulations motivate screening, but graphite behavior depends on the formulation. Transport, wetting and passivation also matter. [S3, S4, S7] |
| Fluoroethylene carbonate (FEC) | Additive comparator | Its role in a protective interphase must be assessed in the complete formulation. Sacrificial reduction and useful cell behavior are not opposites. [S5, S7] |

**Engineering inference, requiring validation:** prioritize an SL-containing formulation for the oxidation-focused research branch, while retaining an electrode-appropriate carbonate control. For a confirmed Ni-rich/graphite system, include the EC-free EMC/FEC approach as a separate comparator. Neither an intrinsic oxidation descriptor nor one paper's formulation establishes which option is best for this unspecified subsystem. Do not choose solvent ratios, salt concentration, additives or a charge cutoff from this benchmark.

The different graphite outcomes reported for SL formulations are a warning against a universal solvent ranking, not evidence that one of the studies must be wrong. Their salts, additives, electrodes and histories differ. [S3, S7]

## 3. What orbital analysis can and cannot establish

**External knowledge:** a HOMO–LUMO gap is not an electrochemical stability window. The relevant redox reactions may involve different species, geometries and solvent environments. [S1] Neutral/charged total-energy differences and local solvation offer more defensible oxidation descriptors than a plot of one isolated molecule. [S2]

| Analysis | Legitimate use | Not established |
|---|---|---|
| Provenance-linked occupied/unoccupied orbital CUBEs | Inspect spatial character and propose reaction sites for further testing. | Oxidation onset, reduction onset, electrolyte lifetime, safe voltage or the identity of the actually oxidized species. |
| HOMO/LUMO energies from a documented calculation | A method- and environment-dependent descriptor; useful only with appropriate validation. | Direct equality to measured redox potentials or a complete cell stability window. |
| Charge/spin and density differences between calculated states | Help identify whether solvent, anion or a complex bears the added/removed electron. | A reaction rate or dominant decomposition pathway without additional evidence. |
| Neutral/charged solution free energies | Estimate specified thermodynamic redox couples with a reference convention and uncertainty. | Kinetic onset, protective interphase formation, gas evolution or full-cell durability. |

**Proposed boundary:** interpreting electron-transfer *tendency* needs consistent free-energy differences; predicting *rates* additionally needs a justified kinetic model, reorganization and coupling information, and electrode/potential dependence. These are missing. Orbital images cannot supply them.

`inspect_cube` cannot infer a HOMO assignment, occupation, orbital energy or molecular identity merely from the scalar grid. Supply a sidecar from the upstream engine. Registration and field units must be checked before comparing grids. Optical transitions, broadened spectra, NTOs, TD-DFT and band structures are not the minimum route to this ground-state molecular redox question; no optical tools are exercised to pad the tool count.

## 4. Minimum defensible automated compute workflow

The following is a **proposed workflow**, not a claim that an upstream adapter exists or has run. Geometry and charged-state calculations are motivated by S2; S6 documents an available upstream continuum-solvation implementation. The model must be validated for the actual chemistry rather than copying a published functional or solvent parameter blindly.

### A. Freeze the scientific problem

Resolve whether 4.3 V denotes cathode potential versus a reference or full-cell terminal voltage. Define the electrode pair, formulation, concentrations, temperature, state of charge, rates, impurity limits, formation history and decision criteria. Supply validated molecular identities, structures and conformers. Do not silently assume graphite or Li/Li+.

A full-cell voltage is the difference between electrode potentials on a consistent scale, with polarization and resistive contributions under load. Therefore the cathode requirement cannot simply be copied to a charger setting. This distinction is enforced in `design.json` and the generated decision.

### B. Compute and verify the relevant electronic states

Optimize conformers of the molecular control and representative solvated species. Include neutral, oxidized and reduced states where meaningful; clusters use their actual total charge and the corresponding electron-added/removed states, not an automatic neutral-cluster assumption. Record multiplicity, SCF convergence, spin diagnostics, geometry and frequency checks.

For free-energy use, validate minima and thermal corrections. An unstable or fragmented radical ion is a result to inspect, not a successful intact-molecule redox state to force into a table. Check basis/method sensitivity, including adequate treatment of diffuse charge for anions. Preserve failed calculations and reasons.

Keep vertical and adiabatic quantities separate. For example, at neutral geometry R0:

```text
IP_vertical = E(M+, R0) - E(M, R0)
EA_vertical = E(M, R0) - E(M-, R0)
IP_adiabatic = E(M+, R+) - E(M, R0)
```

These are definitions for upstream electronic-energy diagnostics, **not BAT-01 results**. A gas-phase ionization energy is not a voltage against Li/Li+. Solvent response appropriate to a vertical process differs from equilibrated-state thermochemistry.

### C. Model the electrolyte environment

Use documented solution treatment rather than vacuum orbitals alone: a validated continuum model plus representative local Li+/counterion/co-solvent complexes when speciation matters. Sample conformers and cluster alternatives. Preserve the solvent parameters and their provenance; a mixture is not automatically described by one pure-solvent dielectric constant. S2 explicitly demonstrates that local electrolyte components affect the oxidation descriptor; this study does not import that paper's numerical fit or errors. [S2, S6]

### D. Derive referenced solution redox potentials

Produce consistently defined solution Gibbs energies with the method, temperature, standard state and correction convention recorded. Do not add a second solvation correction to an energy that already contains it. Use balanced reactions and a validated reference couple in the matching medium, with calibration and uncertainty.

For a balanced relative reaction `Ox + Red_ref -> Red + Ox_ref`, transferring n electrons:

```text
Delta_G_rxn = G(Red) + G(Ox_ref) - G(Ox) - G(Red_ref)
E_red(X) = E_red(ref) - Delta_G_rxn / (n F)
```

Here Delta_G is per mole of the balanced reaction and F is charge per mole of electrons. Stoichiometric coefficients must match n. For oxidation of M use the M+/M reduction couple; for electron addition use M/M-. No numerical conversion or redox result is performed here. Do not subtract an undocumented universal vacuum-to-Li offset.

The implemented `orbital_viewer.electrolyte_screen` consumes already-sourced thermodynamic potentials; it does **not** calculate them. It checks conservative uncertainty intervals for:

```text
oxidation: E(M+/M) - E(cathode) >= required_margin
reduction: E(anode) - E(M/M-) >= required_margin
```

Unknown inputs, assumed evidence, mismatched references/conditions, or overlapping uncertainty intervals stay **unknown**. Nonfinite numbers, negative uncertainties, booleans, orbital energies mislabeled as potentials, and measured-onset kinds are rejected. The reference, conditions and evidence IDs are caller declarations, **not independently authenticated scientific evidence**. Even all intrinsic gates passing leaves formulation qualification unknown and release disallowed. Intrinsic reduction failure may coexist with beneficial passivation; it is not itself a cell failure.

### E. Evaluate decomposition and practical utility

A redox estimate is enough only for an explicitly limited thermodynamic screen. To explain decomposition risk, examine accessible products and competing reactions: fragmentation, proton transfer, salt/additive chemistry and electrode-assisted reactions. Where barriers or mechanisms are claimed, compute and validate the relevant pathways/transition states and account for uncertainty. Do not infer a barrier from orbital shape or invent an intact radical anion when optimization decomposes it.

A full reaction network is not required before every first-pass screen, but a molecular redox calculation cannot establish SEI/CEI quality or exclude chemical attack at the actual cathode. S5's interfacial/degradation study illustrates why the complete cell matters. [S5]

Separately obtain mixture-specific solvation/speciation, conductivity, viscosity, phase behavior, wetting, thermal and materials-compatibility evidence. Use validated simulation and/or measurements; orbital analysis does not predict these automatically. A formulation that resists oxidation but cannot provide practical ion transport is not qualified. [S4]

### F. Validate the formulation on the target electrodes and full cell

Define the acceptance criteria before testing. Record electrode identity, reference calibration, area, scan/hold protocol, temperature, concentration and impurity history for electrochemistry. Combine relevant potentiostatic holds and scans with full-cell cycling/calendar, impedance, gas and interphase evidence. A sweep with a small current on an inert electrode does not validate the target cathode or lifetime. Final operating-envelope and safety review remains a laboratory/human handoff, not a computational approval.

## 5. Scientific artifacts required downstream

| Artifact family | Required contents | Current state |
|---|---|---|
| Identity/formulation | Structure identifiers, stereochemistry, conformer mapping, lot/purity, salt and fractions with their basis. | Missing; names are only a proposed shortlist. |
| Quantum inputs and outputs | Input decks, engine/version/method/basis, charge/multiplicity, geometries, raw logs, wavefunctions, convergence/spin/frequency diagnostics. | Missing. |
| Thermochemistry and redox | State-linked energies with units, thermal/solvation/standard-state convention, balanced reactions, reference calibration, uncertainty/sensitivity. | Missing; no candidate potential is populated. |
| Orbital interpretation | CUBEs plus species/state/conformer identity, grid units and axes, orbital index/occupation/energy, hashes and upstream calculation link. | No candidate CUBEs; synthetic fixture only. |
| Reaction and transport | Reaction network, validated pathways/barriers, speciation and mixture transport/phase/wetting data. | Missing. |
| Experimental validation | Raw traces and protocol metadata, replicates/uncertainty, gas/impedance/interphase analysis and reviewed pass/fail results. | Missing. |
| Engineering traceability | Requirements, proposed/approved selections, evidence links, conditions, unresolved gates, reviewers and schema validation. | Proposed sidecar only. |

Preserve immutable hashes from input to output. Keep literature evidence, actual calculated outputs, derived quantities and assumptions in different fields. CUBE is a visualization artifact, not the primary thermochemical record.

## 6. Propagation into CAID

[design.json](design.json) proposes a sidecar under the semantic path `battery.cell.electrolyte`. **This is not a schema-validated Hardware IR document and was not imported into CAID.** The sidecar retains the unresolved requirement and proposed alternatives while leaving the approved formulation, terminal charge voltage, temperature envelope, capacity and lifetime null.

The dependency is:

```text
candidate/formulation evidence
  -> electrode and interphase compatibility
  -> validated cell operating envelope
  -> battery subsystem requirements
  -> reviewed charger/BMS constraints and thermal/mechanical design
```

Changing a solvent recommendation must invalidate dependent assumptions rather than silently changing a charger. The module always emits `release_allowed=false`; `charger_or_bms_change_allowed` is false in the sidecar. A CAID integrator must map the reviewed evidence into the actual target schema and run its validator before an import. No battery BOM, electrolyte mixing recipe, cell manufacture or configuration deployment is authorized here.

## 7. Tools, execution, friction and handoffs

The work uses GitHub issue/repository/file reads, literature web search/open (including visual checks of S2's method pages), plugin discovery, Python and pytest. No matching CAID or Orbital Studio ChatGPT plugin was returned by the session's discovery query. That does not establish global unavailability. Orbital Studio is exercised through the repository's actual stdio server in CI, not a mocked response or a claimed direct ChatGPT MCP connection.

[plan.json](plan.json) schedules exactly two relevant capability checks: `inspect_cube` and `export_orbital`. The existing five-tool inventory is recorded by `list_tools`; spectrum tools are intentionally unused. The fixture is pinned by its repository blob hash. **Actual status, counts, parameters, raw responses, caveats, package versions, source revision, input hashes and the generated HTML hash are in the resulting `run.json`.** No scientific candidate result is generated from this run.

The authoring container lacked the optional MCP package and could not resolve GitHub for `git clone`; local tests therefore distinguish a skipped integration check from successful pure-Python checks. GitHub connector writes and the existing Actions environment provide the publication/execution route without adding credentials, services or a quantum engine. CI must be inspected before claiming the real MCP check passed.

Manual handoffs H1–H7 in [workflow.json](workflow.json) name the cell designer, electrochemist, quantum-workflow operator, thermochemistry reviewer, transport/laboratory operator, battery laboratory, and safety/CAID reviewers. Their deliverables cover scope confirmation, formulation approval, actual calculations, reference/uncertainty review, mixture evidence, target-cell validation and the reviewed subsystem import.

**Missing reusable capabilities, not case-specific hacks:** validated identity and scientific artifact ingestion; job scheduling with charge/spin/convergence-aware state provenance; calibrated solution-redox and reference conversion; reaction/pathway and solvation sampling; experiment/transport data registration; uncertainty-aware requirement evaluation; schema-validated CAID evidence import with release authorization distinct from software success. This PR implements only the small reference-aware screening check and the benchmark evidence path, not those entire platforms.

**Confidence:** high in the identified evidence boundary; low-to-moderate in transferring the literature shortlist to an unspecified cell; insufficient evidence for a qualified winner or operating voltage. Principal friction is missing upstream scientific inputs and complete formulation/target-cell data, not a missing orbital screenshot.

## 8. Reproduce and inspect the evidence

This branch reuses the evidence runner from PRs #15 and #16. It is stacked on `benchmark/sensor-01-300nm-detector`; merge the prerequisites and retarget to `docs/readme` before merging this branch. No prerequisite PR is merged by this work.

From this branch's checkout, on Windows PowerShell or a standard shell with Python available:

```text
python -m pip install -r requirements.txt
python -m pytest -q --junitxml=.benchmark-runs/test-results.xml
python -m orbital_viewer.benchmark --plan benchmarks/BAT-01/plan.json --data-dir examples/mcp --output .benchmark-runs/BAT-01-local
python -m orbital_viewer.electrolyte_screen --design benchmarks/BAT-01/design.json --output .benchmark-runs/BAT-01-local/assessment.json
```

Use a fresh output directory/name for another run; existing evidence is never overwritten by either CLI. `0` from the screening CLI means evidence processing succeeded, **not that the engineering decision passed**. The MCP recorder accepts only synthetic plans; do not relabel real candidate data as synthetic to force it through this recorder.

CI runs the full tests, the actual BAT-01 stdio plan, and the screening CLI. Its BAT-01 artifact includes the raw run, input fixture, exported HTML, generated assessment, source design/plan/workflow/report, and JUnit results. The run records code/input/export hashes and the assessment records design/implementation hashes. Read the actual workflow result and receipts rather than inferring success from this README.

## Source links

Access scope and limitations are in `sources.json`. These are external sources, not BAT-01 measurements.

- **S1:** Peljo and Girault, 2018, [HOMO–LUMO misconception](https://doi.org/10.1039/C8EE01286E).
- **S2:** Pande and Viswanathan, 2019, [electrolyte-renormalized oxidation descriptors](https://arxiv.org/abs/1908.03285), author preprint.
- **S3:** 2018, [salt choice in SL-based electrolytes](https://doi.org/10.1016/j.jpowsour.2018.05.077).
- **S4:** 2023, [SL in LNMO–graphite full cells](https://doi.org/10.1002/batt.202200565).
- **S5:** Terreblanche et al., 2025, [EC-free electrolyte degradation pathways](https://doi.org/10.1002/aenm.202404427).
- **S6:** [Official ORCA implicit-solvation documentation](https://www.faccts.de/docs/orca/6.1/manual/contents/essentialelements/solvationmodels.html).
- **S7:** Zhao et al., 2024, [SL–graphite compatibility with additives](https://doi.org/10.1016/j.electacta.2023.143592).
