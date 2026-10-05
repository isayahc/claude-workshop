"""Verify ABL1 numbering, evidence, offline CLI flow and failed retrieval cleanup."""

from __future__ import annotations

from email.message import Message
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any
from urllib.error import URLError

import pytest

from protein_workflow import sequences as seq

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/abl1/P00519.cache.json"


@pytest.fixture
def record() -> seq.SourceRecord:
    """Load the unmodified, real UniProt response through the offline cache API."""
    return seq.load_source(FIXTURE, offline=True)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any unmocked network request fail the ordinary test suite."""
    def blocked(*args: Any, **kwargs: Any) -> None:
        """Expose accidental network access immediately."""
        raise AssertionError("Network access is forbidden in sequence tests")
    monkeypatch.setattr(seq, "urlopen", blocked)


def test_real_source_and_domain_offset(record: seq.SourceRecord) -> None:
    """Verify the actual IA sequence and both zero-based and one-based offsets."""
    reference = seq.validate_entry(record.response_text)
    pair = seq.make_pair(reference)
    assert len(reference.sequence) == 1130
    assert hashlib.sha256(reference.sequence.encode()).hexdigest() == "bf5ccc817349256c1c2f16dd66d61bfcd29ac4897fdead01d85e01cd84e33670"
    assert (pair.start, pair.end, len(pair.wild_type), pair.target_index) == (242, 493, 252, 73)
    assert pair.wild_type[73] == "T" and pair.mutant[73] == "I"
    assert [i for i, residues in enumerate(zip(pair.wild_type, pair.mutant)) if residues[0] != residues[1]] == [73]
    assert pair.wild_type == reference.sequence[241:493]
    extended = seq.make_pair(reference, 229, 511)
    assert (len(extended.wild_type), extended.target_index) == (283, 86)
    assert extended.mutant[86] == "I"


@pytest.mark.parametrize("start,end", [(0, 493), (493, 242), (316, 493), (242, 314),
                                      (242, 1131), (242, None), (None, 493), (True, 493), (242.5, 493)])
def test_invalid_domain_is_rejected(record: seq.SourceRecord, start: Any, end: Any) -> None:
    """Reject out-of-range, incomplete and ambiguously typed domain coordinates."""
    with pytest.raises(seq.SequenceError):
        seq.make_pair(seq.validate_entry(record.response_text), start, end)


@pytest.mark.parametrize("change", ["accession", "organism", "isoform", "residue", "alphabet", "length",
                                    "feature", "uncertain_boundary", "duplicate_domain", "version", "missing"])
def test_bad_source_fails_before_output(record: seq.SourceRecord, tmp_path: Path, change: str) -> None:
    """Fail clearly on source identity, residue, annotation and schema problems."""
    entry = json.loads(record.response_text)
    products = next(c for c in entry["comments"] if c["commentType"] == "ALTERNATIVE PRODUCTS")
    domain = next(f for f in entry["features"] if f.get("description") == "Protein kinase")
    if change == "accession": entry["primaryAccession"] = "P00520"
    if change == "organism": entry["organism"]["taxonId"] = 10090
    if change == "isoform": products["isoforms"][0]["isoformIds"] = ["P00519-2"]
    if change == "residue": entry["sequence"]["value"] = entry["sequence"]["value"][:314] + "A" + entry["sequence"]["value"][315:]
    if change == "alphabet": entry["sequence"]["value"] = "X" + entry["sequence"]["value"][1:]
    if change == "length": entry["sequence"]["length"] -= 1
    if change == "feature": entry["features"].remove(domain)
    if change == "uncertain_boundary": domain["location"]["start"]["modifier"] = "UNCERTAIN"
    if change == "duplicate_domain": entry["features"].append(domain)
    if change == "version": entry["entryAudit"]["sequenceVersion"] = True
    if change == "missing": entry.pop("sequence")
    altered = seq.SourceRecord(json.dumps(entry), record.retrieved_at, {}, "cache")
    with pytest.raises(seq.SequenceError):
        seq.export_sequences(altered, tmp_path / "output")
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("payload", ["not json", "[]", "null", "{}", '{"sequence": null}'])
def test_malformed_json(payload: str) -> None:
    """Convert malformed or structurally invalid JSON into a stage error."""
    with pytest.raises(seq.SequenceError, match="Malformed"):
        seq.validate_entry(payload)


def test_bundle_provenance_and_every_residue(record: seq.SourceRecord, tmp_path: Path) -> None:
    """Trace every exported residue and file back to the cached original source."""
    path = seq.export_sequences(record, tmp_path / "run")
    manifest = json.loads(path.read_text())
    assert manifest["status"] == "complete"
    assert manifest["source"]["retrieved_at"] == record.retrieved_at
    assert manifest["source"]["loaded_via"] == "cache"
    assert manifest["source"]["isoform"] == "P00519-1"
    assert manifest["mutation"]["domain_position"] == 74
    assert manifest["mutation"]["domain_index"] == 73
    assert manifest["structure_prediction_performed"] is False
    assert manifest["domain"]["selection"] == "uniprot_annotated_kinase"
    assert (path.parent / "P00519.source.json").read_bytes() == record.response_text.encode()
    wt = "".join((path.parent / "ABL1_WT.fasta").read_text().splitlines()[1:])
    mut = "".join((path.parent / "ABL1_T315I.fasta").read_text().splitlines()[1:])
    reference = json.loads(record.response_text)["sequence"]["value"]
    assert len(manifest["residue_mapping"]) == len(wt) == len(mut) == 252
    for row in manifest["residue_mapping"]:
        i = row["domain_index"]
        assert row["domain_position"] == i + 1
        assert row["source_position"] == i + 242
        assert row["wild_type"] == wt[i] == reference[row["source_position"] - 1]
        assert row["mutant"] == mut[i]
    for name, meta in manifest["artifacts"].items():
        data = (path.parent / name).read_bytes()
        assert (hashlib.sha256(data).hexdigest(), len(data)) == (meta["sha256"], meta["bytes"])
    assert manifest["sequences"]["WT"]["sha256"] == hashlib.sha256(wt.encode()).hexdigest()
    assert manifest["sequences"]["T315I"]["sha256"] == hashlib.sha256(mut.encode()).hexdigest()
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        seq.export_sequences(record, path.parent)
    assert path.read_bytes() == before


@pytest.mark.parametrize("change", ["checksum", "timestamp", "source_url", "schema", "truncated"])
def test_corrupt_cache_is_not_silently_refetched(tmp_path: Path, change: str) -> None:
    """Require explicit refresh of invalid cached evidence, even in default mode."""
    payload = json.loads(FIXTURE.read_text())
    if change == "checksum": payload["response_sha256"] = "0" * 64
    if change == "timestamp": payload["retrieved_at"] = "2026-10-05T00:00:00"
    if change == "source_url": payload["source_url"] = "https://example.org/sequence"
    if change == "schema": payload["schema_version"] = True
    cache = tmp_path / "cache.json"
    cache.write_text("{" if change == "truncated" else json.dumps(payload))
    with pytest.raises(seq.SequenceError, match="Cannot use cache"):
        seq.load_source(cache)


def test_cache_miss_is_actionable_and_offline(tmp_path: Path) -> None:
    """Never contact UniProt when an offline cache is missing."""
    with pytest.raises(seq.SequenceError, match="Fetch once online"):
        seq.load_source(tmp_path / "missing.json", offline=True)
    with pytest.raises(seq.SequenceError, match="cannot be combined"):
        seq.load_source(FIXTURE, offline=True, refresh=True)


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), True])
def test_invalid_timeout(timeout: float) -> None:
    """Reject invalid network settings before starting a request."""
    with pytest.raises(seq.SequenceError, match="Timeout"):
        seq.load_source(FIXTURE, timeout=timeout)


class FakeResponse(io.BytesIO):
    """Minimal context-managed HTTP response for offline retrieval tests."""

    def __init__(self, data: bytes, content_type: str = "application/json") -> None:
        """Create a successful HTTP response with explicit content metadata."""
        super().__init__(data)
        self.status = 200
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        self.headers["X-UniProt-Release"] = "fixture-release"


def test_fetch_then_cache_reuses_original_receipt(record: seq.SourceRecord, tmp_path: Path,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    """Validate fresh responses before cache publication and preserve fetch time."""
    calls: list[str] = []
    def fetch(request: Any, timeout: float) -> FakeResponse:
        """Record the exact endpoint and return real source bytes without network."""
        assert timeout == 12
        calls.append(request.full_url)
        return FakeResponse(record.response_text.encode())
    monkeypatch.setattr(seq, "urlopen", fetch)
    cache = tmp_path / "cache/source.json"
    live = seq.load_source(cache, timeout=12)
    cached = seq.load_source(cache)
    assert calls == [seq.SOURCE_URL]
    assert live.loaded_via == "network" and cached.loaded_via == "cache"
    assert cached.response_text == live.response_text == record.response_text
    assert cached.retrieved_at == live.retrieved_at
    assert cached.response_headers["X-UniProt-Release"] == "fixture-release"


@pytest.mark.parametrize("failure", ["network", "timeout", "html", "json", "oversize"])
def test_failed_refresh_keeps_cache_and_no_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                 failure: str) -> None:
    """Keep known-good evidence intact when retrieval or source validation fails."""
    cache = tmp_path / "cache.json"
    shutil.copyfile(FIXTURE, cache)
    before = cache.read_bytes()
    def fetch(*args: Any, **kwargs: Any) -> FakeResponse:
        """Simulate each transport or response-validation failure."""
        if failure == "network": raise URLError("unavailable")
        if failure == "timeout": raise TimeoutError("timed out")
        if failure == "html": return FakeResponse(b"<html>unavailable</html>", "text/html")
        if failure == "json": return FakeResponse(b"{broken")
        return FakeResponse(b"x" * (seq.MAX_RESPONSE_BYTES + 1))
    monkeypatch.setattr(seq, "urlopen", fetch)
    output = tmp_path / "run"
    with pytest.raises(SystemExit) as error:
        seq.main(["--refresh", "--cache", str(cache), "--output", str(output)])
    assert error.value.code == 2
    assert cache.read_bytes() == before
    assert not output.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["cache.json"]


def test_write_failure_removes_partial_bundle(record: seq.SourceRecord, tmp_path: Path,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    """A disk failure after the first file must not leave a completion manifest."""
    original = Path.write_bytes
    def write(path: Path, data: bytes) -> int:
        """Fail on the second artifact while preserving other filesystem behavior."""
        if path.name == "ABL1_T315I.fasta": raise OSError("disk full")
        return original(path, data)
    monkeypatch.setattr(Path, "write_bytes", write)
    with pytest.raises(OSError, match="disk full"):
        seq.export_sequences(record, tmp_path / "run")
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize("entrypoint", [["-m", "protein_workflow.sequences"], ["data/fetch_sequences.py"]])
def test_offline_cli_end_to_end(tmp_path: Path, entrypoint: list[str]) -> None:
    """Exercise both documented commands, including no-overwrite and custom bounds."""
    output = tmp_path / "run"
    command = [sys.executable, *entrypoint, "--offline", "--cache", str(FIXTURE), "--output", str(output),
               "--domain-start", "229", "--domain-end", "511"]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["domain"]["length"] == 283
    assert manifest["domain"]["selection"] == "user_supplied_interval"
    assert manifest["mutation"]["domain_position"] == 87
    assert manifest["source"]["loaded_via"] == "cache"
    before = (output / "manifest.json").read_bytes()
    retry = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=15)
    assert retry.returncode == 2 and "Output already exists" in retry.stderr
    assert (output / "manifest.json").read_bytes() == before


@pytest.mark.parametrize("cache_suffix", ["", "/source.json"])
def test_cache_cannot_occupy_output(tmp_path: Path, cache_suffix: str) -> None:
    """Reject cache/output overlap before any network access or file creation."""
    output = tmp_path / "run"
    with pytest.raises(SystemExit) as error:
        seq.main(["--output", str(output), "--cache", str(output) + cache_suffix])
    assert error.value.code == 2
    assert not output.exists()
