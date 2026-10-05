# UniProt P00519 offline snapshot

`P00519.cache.json` is the **complete real UniProt response**, with its retrieval
receipt, downloaded by `protein_workflow.sequences` on October 5, 2026. It is not
a synthetic sequence or a structure prediction. It uses the same cache format as
live runs, so the offline walkthrough and CI exercise the actual parsing path.

- Source: https://rest.uniprot.org/uniprotkb/P00519.json
- Retrieval: `2026-10-05T07:00:46.249888+00:00`
- UniProt release: `2026_03`; entry version: `294`; sequence version: `4`
- Raw response SHA-256: `5b0171beb95c871df1f6556a2eb198976a3834c9ea3a8134dab893f3947b72db`
- Cache file SHA-256: `a37f792b113966dfa0abf9cf1148b8d28304173e32b5f6a47e5e345c0b9020d7`
- Full IA sequence SHA-256: `bf5ccc817349256c1c2f16dd66d61bfcd29ac4897fdead01d85e01cd84e33670`

UniProt data are provided under [CC BY 4.0](https://www.uniprot.org/help/license).
Credit: UniProt Consortium. Preserve the source URL and retrieval receipt when
redistributing. Do not use `--refresh` against this fixture; create a separate
cache for live work. A deliberate fixture update should review sequence,
isoform/domain annotations, hashes and the expected mappings together.
