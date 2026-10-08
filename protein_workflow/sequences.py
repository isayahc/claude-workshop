"""Retrieve UniProt ABL1 isoform IA and export a verified T315I domain pair."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from http.client import HTTPException
import json
import math
from pathlib import Path
import shutil
import tempfile
from typing import Any, Literal
from urllib.error import URLError
from urllib.request import Request, urlopen

SOURCE_URL = "https://rest.uniprot.org/uniprotkb/P00519.json"
ISOFORM = "P00519-1"
TARGET_POSITION = 315
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
AMINO_ACIDS = frozenset("ACDEFGHIKLMNPQRSTVWY")


class SequenceError(ValueError):
    """An input, retrieval or provenance failure that prevents sequence export."""


@dataclass(frozen=True)
class Reference:
    """Validated full-length isoform IA sequence and its kinase annotation."""

    sequence: str
    kinase_start: int
    kinase_end: int
    entry_version: int
    sequence_version: int


@dataclass(frozen=True)
class SourceRecord:
    """Exact source response and original retrieval receipt, including cache use."""

    response_text: str
    retrieved_at: str
    response_headers: dict[str, str]
    loaded_via: Literal["network", "cache"]


@dataclass(frozen=True)
class SequencePair:
    """One inclusive source-domain interval and its single T315I substitution."""

    wild_type: str
    mutant: str
    start: int
    end: int
    target_index: int


def sha256(data: bytes) -> str:
    """Return a SHA-256 digest of exact artifact bytes."""
    return hashlib.sha256(data).hexdigest()


def utc_now() -> str:
    """Return the current timezone-aware UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _positive_int(value: Any, name: str) -> int:
    """Require a positive JSON integer, excluding booleans and lossy coercion."""
    if type(value) is not int or value < 1:
        raise SequenceError(f"{name} must be a positive integer.")
    return value


def validate_entry(response_text: str) -> Reference:
    """Reject wrong identities, isoforms, sequences and ambiguous kinase features."""
    try:
        entry = json.loads(response_text)
        if (entry["primaryAccession"] != "P00519"
                or entry["uniProtkbId"] != "ABL1_HUMAN"
                or entry["entryType"] != "UniProtKB reviewed (Swiss-Prot)"
                or entry["organism"]["taxonId"] != 9606
                or "ABL1" not in [g["geneName"]["value"] for g in entry["genes"]]):
            raise SequenceError("Expected reviewed human ABL1 (UniProt P00519).")
        displayed = [i for c in entry["comments"]
                     if c["commentType"] == "ALTERNATIVE PRODUCTS"
                     for i in c["isoforms"] if i["isoformSequenceStatus"] == "Displayed"]
        if (len(displayed) != 1 or displayed[0]["isoformIds"] != [ISOFORM]
                or displayed[0]["name"]["value"] != "IA"):
            raise SequenceError("Expected displayed isoform IA / P00519-1; review numbering before proceeding.")
        sequence = entry["sequence"]["value"]
        length = _positive_int(entry["sequence"]["length"], "Source length")
        if (not isinstance(sequence, str) or len(sequence) != length
                or not sequence or not set(sequence) <= AMINO_ACIDS):
            raise SequenceError("Source sequence must match its length and contain only uppercase standard amino acids.")
        domains = [f for f in entry["features"]
                   if f["type"] == "Domain" and f.get("description") == "Protein kinase"]
        if len(domains) != 1:
            raise SequenceError("Expected exactly one annotated Protein kinase domain.")
        location = domains[0]["location"]
        if any(location[key]["modifier"] != "EXACT" for key in ("start", "end")):
            raise SequenceError("Kinase domain boundaries must be exact.")
        start = _positive_int(location["start"]["value"], "Kinase start")
        end = _positive_int(location["end"]["value"], "Kinase end")
        if not 1 <= start <= TARGET_POSITION <= end <= length:
            raise SequenceError("Kinase domain must include source residue 315 and fit the full sequence.")
        if sequence[TARGET_POSITION - 1] != "T":
            raise SequenceError(f"Expected T at {ISOFORM}:315; found {sequence[TARGET_POSITION - 1]}. Refusing mutation.")
        audit = entry["entryAudit"]
        return Reference(sequence, start, end,
                         _positive_int(audit["entryVersion"], "Entry version"),
                         _positive_int(audit["sequenceVersion"], "Sequence version"))
    except (KeyError, TypeError, IndexError, json.JSONDecodeError) as exc:
        raise SequenceError(f"Malformed UniProt source data: {exc}") from exc


def make_pair(reference: Reference, start: int | None = None, end: int | None = None) -> SequencePair:
    """Extract a source-numbered interval and verify exactly one T-to-I change."""
    if (start is None) != (end is None):
        raise SequenceError("Supply both --domain-start and --domain-end, or neither.")
    start = reference.kinase_start if start is None else _positive_int(start, "Domain start")
    end = reference.kinase_end if end is None else _positive_int(end, "Domain end")
    if not 1 <= start <= TARGET_POSITION <= end <= len(reference.sequence):
        raise SequenceError("Domain boundaries must include residue 315 and fit the full sequence (1-based, inclusive).")
    wild_type = reference.sequence[start - 1:end]
    index = TARGET_POSITION - start
    if wild_type[index] != "T":
        raise SequenceError(f"Expected T at {ISOFORM}:315; refusing to mutate another residue.")
    mutant = wild_type[:index] + "I" + wild_type[index + 1:]
    differences = [i for i, (wt, mut) in enumerate(zip(wild_type, mutant, strict=True)) if wt != mut]
    if differences != [index]:
        raise SequenceError("Mutation validation failed: expected exactly one T315I substitution.")
    return SequencePair(wild_type, mutant, start, end, index)


def _cache_payload(record: SourceRecord) -> dict[str, Any]:
    """Serialize an exact UTF-8 response with a stable original retrieval receipt."""
    return {"schema_version": 1, "source_url": SOURCE_URL,
            "retrieved_at": record.retrieved_at, "response_headers": record.response_headers,
            "response_sha256": sha256(record.response_text.encode("utf-8")),
            "response_text": record.response_text}


def _read_cache(path: Path) -> SourceRecord:
    """Load and validate a cached receipt without changing its retrieval timestamp."""
    try:
        if path.stat().st_size > MAX_RESPONSE_BYTES * 2:
            raise SequenceError("Cache exceeds the size limit.")
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw = payload["response_text"]
        timestamp = datetime.fromisoformat(payload["retrieved_at"])
        headers = payload["response_headers"]
        if (type(payload["schema_version"]) is not int or payload["schema_version"] != 1
                or payload["source_url"] != SOURCE_URL
                or not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_RESPONSE_BYTES
                or payload["response_sha256"] != sha256(raw.encode("utf-8"))
                or timestamp.tzinfo is None
                or not isinstance(headers, dict)
                or any(not isinstance(k, str) or not isinstance(v, str) for k, v in headers.items())):
            raise SequenceError("Invalid cache schema, source URL, timestamp, headers or response checksum.")
        validate_entry(raw)
        return SourceRecord(raw, payload["retrieved_at"], headers, "cache")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SequenceError(f"Cannot use cache {path}: {exc} Use --refresh when online, or supply an intact cache.") from exc


def _write_cache(path: Path, record: SourceRecord) -> None:
    """Replace a cache only after a complete, validated response is available."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(_cache_payload(record), handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_source(cache: Path, *, offline: bool = False, refresh: bool = False,
                timeout: float = 30.0) -> SourceRecord:
    """Use a verified cache by default, fetching only on a miss or explicit refresh."""
    if offline and refresh:
        raise SequenceError("--offline and --refresh cannot be combined.")
    if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
        raise SequenceError("Timeout must be a finite positive number of seconds.")
    if cache.exists() and not refresh:
        return _read_cache(cache)
    if offline:
        raise SequenceError(f"Offline cache is missing: {cache}. Fetch once online or use tests/fixtures/abl1/P00519.cache.json.")
    try:
        request = Request(SOURCE_URL, headers={"Accept": "application/json", "User-Agent": "nano-tech-harness/0.1 ABL1-sequences"})
        with urlopen(request, timeout=timeout) as response:
            if response.status != 200 or response.headers.get_content_type() != "application/json":
                raise SequenceError("UniProt must return HTTP 200 with an application/json response.")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            headers = {name: response.headers[name] for name in
                       ("X-UniProt-Release", "X-UniProt-Release-Date", "ETag", "Last-Modified")
                       if response.headers.get(name) is not None}
        if len(raw) > MAX_RESPONSE_BYTES:
            raise SequenceError("UniProt response exceeds the 5 MiB limit.")
        record = SourceRecord(raw.decode("utf-8"), utc_now(), headers, "network")
        validate_entry(record.response_text)
    except (URLError, OSError, UnicodeError, HTTPException) as exc:
        raise SequenceError(f"Cannot retrieve {SOURCE_URL}: {exc}. Check connectivity and retry, or use --offline with a saved --cache.") from exc
    _write_cache(cache, record)
    return record


def _fasta(sequence: str, variant: str, pair: SequencePair) -> bytes:
    """Encode a wrapped FASTA with explicit source coordinates and mutation label."""
    header = f">ABL1_{variant} accession=P00519 isoform={ISOFORM} source_range={pair.start}-{pair.end} numbering=1-based-inclusive"
    if variant == "T315I":
        header += f" mutation=T315I domain_position={pair.target_index + 1}"
    return (header + "\n" + "\n".join(sequence[i:i + 60] for i in range(0, len(sequence), 60)) + "\n").encode("ascii")


def export_sequences(record: SourceRecord, output: Path, *, start: int | None = None,
                     end: int | None = None) -> Path:
    """Write a new complete bundle, cleaning partial writes and refusing replacement."""
    reference = validate_entry(record.response_text)
    pair = make_pair(reference, start, end)
    artifacts = {"ABL1_WT.fasta": _fasta(pair.wild_type, "WT", pair),
                 "ABL1_T315I.fasta": _fasta(pair.mutant, "T315I", pair),
                 "P00519.source.json": record.response_text.encode("utf-8")}
    manifest = {
        "schema_version": 1, "status": "complete", "created_at": utc_now(),
        "stage": "sequence_preparation", "structure_prediction_performed": False,
        "source": {"url": SOURCE_URL, "accession": "P00519", "isoform": ISOFORM,
                   "isoform_name": "IA", "taxon_id": 9606, "gene": "ABL1",
                   "retrieved_at": record.retrieved_at, "loaded_via": record.loaded_via,
                   "response_headers": record.response_headers, "artifact": "P00519.source.json",
                   "entry_version": reference.entry_version, "sequence_version": reference.sequence_version,
                   "sequence_length": len(reference.sequence),
                   "sequence_sha256": sha256(reference.sequence.encode("ascii"))},
        "domain": {"start": pair.start, "end": pair.end, "length": len(pair.wild_type),
                   "coordinate_convention": "1-based inclusive, full-length P00519-1 isoform IA",
                   "selection": "uniprot_annotated_kinase" if start is None else "user_supplied_interval",
                   "annotated_kinase_start": reference.kinase_start, "annotated_kinase_end": reference.kinase_end},
        "mutation": {"label": "T315I", "source_position": TARGET_POSITION,
                     "domain_position": pair.target_index + 1, "domain_index": pair.target_index,
                     "from": "T", "to": "I", "verified_difference_count": 1},
        "sequences": {"WT": {"artifact": "ABL1_WT.fasta", "sha256": sha256(pair.wild_type.encode("ascii"))},
                      "T315I": {"artifact": "ABL1_T315I.fasta", "sha256": sha256(pair.mutant.encode("ascii"))}},
        "residue_mapping": [{"source_position": pair.start + i, "domain_position": i + 1,
                             "domain_index": i, "wild_type": wt, "mutant": mut}
                            for i, (wt, mut) in enumerate(zip(pair.wild_type, pair.mutant, strict=True))],
        "artifacts": {name: {"sha256": sha256(data), "bytes": len(data)} for name, data in artifacts.items()},
        "implementation": {"module": "protein_workflow.sequences", "sha256": sha256(Path(__file__).read_bytes())},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(exist_ok=False)
    complete = False
    try:
        for name, data in artifacts.items():
            (output / name).write_bytes(data)
        # The completion manifest is published last; failures never leave a complete bundle.
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        complete = True
    finally:
        if not complete:
            shutil.rmtree(output)
    return output / "manifest.json"


def main(argv: list[str] | None = None) -> int:
    """Run the sequence-input CLI and report actionable failures without tracebacks."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New output directory; existing paths are refused")
    parser.add_argument("--cache", type=Path, default=Path(".sequence-cache/P00519.cache.json"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", help="Read cache only; never contact UniProt")
    mode.add_argument("--refresh", action="store_true", help="Fetch and validate a new source, replacing cache on success")
    parser.add_argument("--timeout", type=float, default=30.0, help="Network socket timeout in seconds")
    parser.add_argument("--domain-start", type=int, help="Optional full-source start (1-based, inclusive)")
    parser.add_argument("--domain-end", type=int, help="Optional full-source end (1-based, inclusive)")
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise SequenceError(f"Output already exists: {args.output}. Choose a new directory.")
        if (args.domain_start is None) != (args.domain_end is None):
            raise SequenceError("Supply both --domain-start and --domain-end, or neither.")
        if args.output.resolve() == args.cache.resolve() or args.output.resolve() in args.cache.resolve().parents:
            raise SequenceError("Cache must be outside the new output directory.")
        record = load_source(args.cache, offline=args.offline, refresh=args.refresh, timeout=args.timeout)
        manifest = export_sequences(record, args.output, start=args.domain_start, end=args.domain_end)
    except (SequenceError, OSError) as exc:
        parser.exit(2, f"ABL1 sequence input failed: {exc}\n")
    print(f"Validated WT and T315I sequences; manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
