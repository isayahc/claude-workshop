# fpocket parser fixtures

`receptor_out/` contains two complete pocket records from a real, locally compiled
fpocket 4.2.3 run on upstream's experimental `1UYD.pdb` example. The source commit,
input transformation, hashes, binary hash, and captured banner are recorded in
`provenance.json`. The banner says **4.0**, even though the source tag is 4.2.3.
The full run found 13 pockets; this excerpt keeps ranks 1 and 2.

`contact-reference.pdb` is the union of these pockets' contacted atoms, sorted by
original serial. It is only a parsing reference fragment, not a complete receptor
for a new detection run. This protein is not ABL1: tests leave source/domain
positions and pLDDT null. The upstream MIT notice is in `LICENSE.fpocket`.

`stub_fpocket.py` is a separate **illustrative test double**, not recorded detector
output. It exercises the actual process boundary and simulated failures using
stage #5's artificial WT/T315I structures. It must never be used as fpocket for
scientific work. Tests clearly preserve their `illustrative` classification.

For complete fresh output from the real binary, see `protein_workflow.pocket_smoke`
and the `fpocket-reference` CI job. Monte Carlo volume estimates can vary between
runs; fpocket's wall-clock random seed is not controlled by this adapter.
