"""Run, validate and cache local ESMFold predictions for validated ABL1 inputs."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime
import errno
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any, Literal

from protein_workflow.esmfold_worker import MODEL_ID, MODEL_REVISION, TRANSFORMERS_VERSION
from protein_workflow.sequences import make_pair, sha256, utc_now, validate_entry
from protein_workflow.structures import validate_structure

WORKER = Path(__file__).with_name("esmfold_worker.py")
RAW_FILES = ("structure.pdb", "confidence.json", "backend.json")


class PredictionError(ValueError):
    """Invalid input or a failed backend/cache validation, with no usable result."""


class PredictionTimeout(PredictionError):
    """The isolated backend exceeded its wall-clock deadline and was terminated."""


@dataclass(frozen=True)
class PredictionConfig:
    """Scientific backend settings included in every request and cache identity."""

    backend: Literal["esmfold", "fixture"] = "esmfold"
    device: Literal["cuda", "cpu"] = "cuda"
    num_recycles: int = 3
    chunk_size: int = 128
    seed: int = 0

    def validate(self) -> None:
        """Reject unsupported settings instead of silently changing model behavior."""
        if self.backend not in ("esmfold", "fixture") or self.device not in ("cuda", "cpu"):
            raise PredictionError("Unsupported backend or device.")
        for name, value, lower, upper in (("num_recycles", self.num_recycles, 0, 20),
                                          ("chunk_size", self.chunk_size, 1, 1024),
                                          ("seed", self.seed, 0, 2**32 - 1)):
            if type(value) is not int or not lower <= value <= upper:
                raise PredictionError(f"{name} must be an integer in {lower}..{upper}.")


@dataclass(frozen=True)
class SequenceInput:
    """Verified sequence plus a self-contained copy of its entire input bundle."""

    sequence: str
    variant: str
    start: int
    end: int
    fasta_name: str
    files: dict[str, bytes]


@dataclass(frozen=True)
class PredictionResult:
    """Terminal stage state and reviewable paths, including failed run manifests."""

    status: str
    manifest_path: Path
    structure_path: Path | None
    validation_path: Path | None
    cache_hit: bool


def _read(path: Path, limit: int = 5 * 1024 * 1024) -> bytes:
    """Read a bounded ordinary artifact, rejecting oversized files before parsing."""
    if path.stat().st_size > limit:
        raise PredictionError(f"Artifact exceeds {limit} bytes: {path}")
    return path.read_bytes()


def _json(path: Path) -> dict[str, Any]:
    """Read an object-valued JSON artifact without accepting nonfinite numbers."""
    value = json.loads(_read(path))
    if not isinstance(value, dict):
        raise PredictionError(f"Expected a JSON object: {path}")
    json.dumps(value, allow_nan=False)
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    """Atomically replace a status/receipt so readers do not observe partial JSON."""
    temporary = path.with_name(path.name + ".pending")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_sequence_input(fasta: Path, manifest: Path | None = None) -> SequenceInput:
    """Revalidate the #4 source, both FASTAs and all mappings before prediction."""
    manifest = manifest or fasta.parent / "manifest.json"
    try:
        raw_manifest = _read(manifest)
        data = json.loads(raw_manifest)
        if data["schema_version"] != 1 or data["status"] != "complete" or data["stage"] != "sequence_preparation":
            raise PredictionError("Expected a complete version-1 sequence-preparation manifest from issue #4.")
        files = {"manifest.json": raw_manifest}
        for name in ("ABL1_WT.fasta", "ABL1_T315I.fasta", "P00519.source.json"):
            content = _read(manifest.parent / name)
            if data["artifacts"][name] != {"sha256": sha256(content), "bytes": len(content)}:
                raise PredictionError(f"Input artifact checksum/size mismatch: {name}")
            files[name] = content
        reference = validate_entry(files["P00519.source.json"].decode("utf-8"))
        pair = make_pair(reference, data["domain"]["start"], data["domain"]["end"])
        if not 1 <= len(pair.wild_type) <= 1024:
            raise PredictionError("This prediction adapter accepts 1..1024 residues; choose an explicit smaller input interval.")
        if (data["source"]["isoform"] != "P00519-1" or data["source"]["accession"] != "P00519"
                or data["source"]["sequence_sha256"] != sha256(reference.sequence.encode("ascii"))
                or data["domain"]["length"] != len(pair.wild_type)):
            raise PredictionError("Source identity, sequence hash or domain length disagrees with the archived source.")
        expected_mapping = [{"source_position": pair.start + i, "domain_position": i + 1,
                             "domain_index": i, "wild_type": wt, "mutant": mut}
                            for i, (wt, mut) in enumerate(zip(pair.wild_type, pair.mutant, strict=True))]
        expected_mutation = {"label": "T315I", "source_position": 315,
                             "domain_position": pair.target_index + 1, "domain_index": pair.target_index,
                             "from": "T", "to": "I", "verified_difference_count": 1}
        if data["residue_mapping"] != expected_mapping or data["mutation"] != expected_mutation:
            raise PredictionError("Input residue mapping or mutation does not match the verified IA source.")
        for variant, sequence in (("WT", pair.wild_type), ("T315I", pair.mutant)):
            name = f"ABL1_{variant}.fasta"
            lines = files[name].decode("ascii").splitlines()
            if (not lines or not lines[0].startswith(">") or any(line.startswith(">") for line in lines[1:])
                    or "".join(lines[1:]) != sequence
                    or data["sequences"][variant] != {"artifact": name, "sha256": sha256(sequence.encode("ascii"))}):
                raise PredictionError(f"{variant} FASTA does not match the verified source/mutation.")
        if fasta.name not in ("ABL1_WT.fasta", "ABL1_T315I.fasta") or _read(fasta) != files[fasta.name]:
            raise PredictionError("Select either validated ABL1_WT.fasta or ABL1_T315I.fasta from the input bundle.")
        variant = "WT" if fasta.name == "ABL1_WT.fasta" else "T315I"
        return SequenceInput(pair.wild_type if variant == "WT" else pair.mutant,
                             variant, pair.start, pair.end, fasta.name, files)
    except (KeyError, TypeError, IndexError, UnicodeError, json.JSONDecodeError) as exc:
        raise PredictionError(f"Malformed sequence input bundle: {exc}") from exc


def run_process(command: list[str], directory: Path, prefix: str, timeout: float) -> None:
    """Run without a shell, capture logs, and terminate the POSIX process group on timeout."""
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "HF_HUB_DISABLE_TELEMETRY": "1"}
    with (directory / f"{prefix}.stdout.log").open("wb") as stdout, (directory / f"{prefix}.stderr.log").open("wb") as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr, env=env, start_new_session=os.name == "posix")
        try:
            code = process.wait(timeout=timeout)
        except BaseException as exc:
            if process.poll() is None:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            process.wait()
            if isinstance(exc, subprocess.TimeoutExpired):
                raise PredictionTimeout(f"{prefix} exceeded {timeout:g}s; worker terminated. Inspect {prefix}.stderr.log.") from exc
            raise
        if code != 0:
            raise PredictionError(f"{prefix} exited with code {code}; inspect {prefix}.stderr.log. For ESMFold install the fold extra and check weights/device settings.")


def cache_identity(sequence: str, config: PredictionConfig, environment: dict[str, Any]) -> dict[str, Any]:
    """Include input, checkpoint, runtime, settings and adapter code in a reusable key."""
    directory = Path(__file__).parent
    return {"schema_version": 1, "sequence_sha256": sha256(sequence.encode("ascii")),
            "configuration": asdict(config), "environment": environment,
            "model": {"id": MODEL_ID, "revision": MODEL_REVISION, "transformers": TRANSFORMERS_VERSION}
            if config.backend == "esmfold" else {"id": "illustrative-backbone", "revision": "1"},
            "implementation": {name: sha256((directory / name).read_bytes()) for name in
                               ("folding.py", "esmfold_worker.py", "structures.py", "sequences.py")}}


def _validate_raw(directory: Path, inputs: SequenceInput, config: PredictionConfig,
                  runtime: dict[str, Any], report: Path) -> dict[str, Any]:
    """Check backend identity, structure and confidence before accepting any result."""
    backend = _json(directory / "backend.json")
    predicted = config.backend == "esmfold"
    expected_class = "computed_prediction" if predicted else "illustrative"
    if (backend["schema_version"] != 1 or backend["classification"] != expected_class
            or backend["sequence_sha256"] != sha256(inputs.sequence.encode("ascii"))
            or backend["configuration"] != asdict(config) or backend["environment"] != runtime
            or backend["sequence_sent_to_external_service"] is not False
            or type(backend["runtime_seconds"]) not in (int, float)
            or not math.isfinite(backend["runtime_seconds"]) or backend["runtime_seconds"] < 0):
        raise PredictionError("Backend receipt disagrees with the requested sequence, configuration or runtime.")
    if datetime.fromisoformat(backend["completed_at"]).tzinfo is None:
        raise PredictionError("Backend completion time must include its timezone.")
    expected_model = (MODEL_ID, MODEL_REVISION) if predicted else ("illustrative-backbone", "1")
    if (backend["model"]["id"], backend["model"]["revision"]) != expected_model:
        raise PredictionError("Backend model identity mismatch.")
    if predicted and backend["model"]["resolved_config_revision"] != MODEL_REVISION:
        raise PredictionError("Backend checkpoint revision mismatch.")
    validation = validate_structure(_read(directory / "structure.pdb").decode("ascii"), inputs.sequence,
                                    inputs.start, predicted=predicted)
    _write_json(report, validation)
    if not validation["valid"]:
        raise PredictionError("Structure does not match the requested sequence/numbering or backbone; inspect validation.json for missing/unmapped residues.")
    confidence = _json(directory / "confidence.json")
    values = confidence["raw_ca_values"]
    if predicted:
        if (confidence["kind"] != "predicted_lddt" or confidence["raw_scale"] != [0, 1]
                or confidence["pdb_scale"] != [0, 100] or not isinstance(values, list)
                or len(values) != len(inputs.sequence)):
            raise PredictionError("Confidence values/scale do not match the predicted sequence.")
        for value, row in zip(values, validation["residue_mapping"], strict=True):
            if (type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1
                    or abs(row["plddt"] - value * 100) > 0.011):
                raise PredictionError("Raw confidence and PDB pLDDT disagree.")
    elif confidence != {"kind": "unavailable_fixture", "raw_scale": None, "raw_ca_values": None,
                        "pdb_scale": None, "pdb_conversion": None}:
        raise PredictionError("Illustrative fixture must not claim scientific confidence.")
    return backend


def _cache_read(path: Path, identity: dict[str, Any], destination: Path) -> None:
    """Copy immutable cache bytes only after checking identity and all raw-file hashes."""
    receipt = _json(path / "cache.json")
    if receipt.get("identity") != identity or set(receipt.get("artifacts", {})) != set(RAW_FILES):
        raise PredictionError("Cache identity/artifact list mismatch; use --no-cache or inspect the entry.")
    contents = {name: _read(path / name) for name in RAW_FILES}
    for name, content in contents.items():
        if receipt["artifacts"][name] != {"sha256": sha256(content), "bytes": len(content)}:
            raise PredictionError(f"Cache checksum/size mismatch for {name}; use --no-cache or inspect the entry.")
    destination.mkdir()
    for name, content in contents.items():
        (destination / name).write_bytes(content)


def _cache_write(path: Path, identity: dict[str, Any], source: Path) -> None:
    """Publish a complete successful entry by directory rename, never failed output."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".pending-", dir=path.parent) as temporary:
        staging = Path(temporary) / "entry"
        staging.mkdir()
        artifacts = {}
        for name in RAW_FILES:
            content = _read(source / name)
            (staging / name).write_bytes(content)
            artifacts[name] = {"sha256": sha256(content), "bytes": len(content)}
        _write_json(staging / "cache.json", {"identity": identity, "artifacts": artifacts})
        try:
            staging.rename(path)
        except OSError as exc:
            # A concurrent successful writer owns this key; never overwrite it.
            if exc.errno not in (errno.EEXIST, errno.ENOTEMPTY):
                raise


def run_prediction(fasta: Path, output: Path, *, manifest: Path | None = None,
                   config: PredictionConfig = PredictionConfig(), python: str = sys.executable,
                   cache: Path | None = Path(".protein-cache/structures"), timeout: float = 1200,
                   local_files_only: bool = True) -> PredictionResult:
    """Predict either variant with typed results, inspectable failures and verified reuse."""
    config.validate()
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise PredictionError("Timeout must be finite and positive.")
    if cache is not None and (cache.resolve() == output.resolve()
                              or output.resolve() in cache.resolve().parents
                              or cache.resolve() in output.resolve().parents):
        raise PredictionError("Output and cache directories must not contain each other.")
    inputs = load_sequence_input(fasta, manifest)
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(exist_ok=False)
    started, started_at = time.monotonic(), utc_now()
    state: dict[str, Any] = {"schema_version": 1, "stage": "structure_prediction", "status": "running",
                             "started_at": started_at, "variant": inputs.variant, "configuration": asdict(config),
                             "cache_hit": False, "structure_artifact": None, "error": None,
                             "inference_attempted": False, "prediction_validated": False,
                             "structure_prediction_performed": False, "inference_executed_this_run": False}
    cache_key: str | None = None
    result_path = output / "result.json"
    validation_path = output / "validation.json"

    def progress(step: str) -> None:
        """Publish a durable stage boundary and a concise live CLI progress message."""
        state["step"] = step
        _write_json(output / "status.json", {**state, "updated_at": utc_now()})
        with (output / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"at": utc_now(), "step": step, "status": state["status"]}) + "\n")
        print(f"[{inputs.variant}] {step}", file=sys.stderr, flush=True)

    try:
        progress("validated_input")
        input_dir = output / "inputs"
        input_dir.mkdir()
        for name, content in inputs.files.items():
            (input_dir / name).write_bytes(content)
        state["input"] = {"fasta": f"inputs/{inputs.fasta_name}", "manifest": "inputs/manifest.json",
                          "sequence_sha256": sha256(inputs.sequence.encode("ascii")),
                          "source_isoform": "P00519-1", "domain_start": inputs.start, "domain_end": inputs.end}
        request = {"sequence": inputs.sequence, "configuration": asdict(config), "local_files_only": local_files_only}
        _write_json(output / "request.json", request)
        progress("probing_backend")
        run_process([python, str(WORKER), "--probe", "--backend", config.backend, "--device", config.device],
                    output, "probe", min(timeout, 60))
        runtime = _json(output / "probe.stdout.log")
        identity = cache_identity(inputs.sequence, config, runtime)
        cache_key = sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        state["cache_key"] = cache_key
        state["identity"] = identity
        raw = output / "raw"
        entry = cache / cache_key if cache is not None else None
        if entry is not None and entry.exists():
            progress("loading_cache")
            _cache_read(entry, identity, raw)
            state["cache_hit"] = True
        else:
            progress("running_backend")
            if config.backend == "esmfold":
                state.update({"inference_attempted": True, "structure_prediction_performed": None,
                              "inference_executed_this_run": None})
            run_process([python, str(WORKER), "--request", str(output / "request.json"), "--output", str(raw)],
                        output, "worker", timeout)
        progress("validating_structure")
        backend = _validate_raw(raw, inputs, config, runtime, validation_path)
        if entry is not None and not state["cache_hit"]:
            progress("saving_cache")
            _cache_write(entry, identity, raw)
        state.update({"status": "succeeded", "classification": backend["classification"],
                      "prediction_validated": True,
                      "structure_artifact": "raw/structure.pdb", "validation_artifact": "validation.json",
                      "backend": backend, "structure_prediction_performed": config.backend == "esmfold",
                      "inference_executed_this_run": config.backend == "esmfold" and not state["cache_hit"],
                      "docking_ready": False})
    except (OSError, ValueError, KeyError, TypeError) as exc:
        state.update({"status": "timed_out" if isinstance(exc, PredictionTimeout) else "failed",
                      "error": str(exc), "failed_step": state.get("step"), "structure_artifact": None,
                      "docking_ready": False})
    except KeyboardInterrupt:
        state.update({"status": "cancelled", "error": "Interrupted by user", "structure_artifact": None})
        raise
    finally:
        state["runtime_seconds"] = time.monotonic() - started
        state["completed_at"] = utc_now()
        state["artifacts"] = {str(path.relative_to(output)): {"sha256": sha256(path.read_bytes()), "bytes": path.stat().st_size}
                              for path in output.rglob("*") if path.is_file()
                              and path.name not in ("status.json", "result.json", "events.jsonl")}
        _write_json(result_path, state)
        progress(state["status"])
    return PredictionResult(state["status"], result_path,
                            output / "raw/structure.pdb" if state["status"] == "succeeded" else None,
                            validation_path if validation_path.exists() else None, state["cache_hit"])


def main(argv: list[str] | None = None) -> int:
    """Expose the same prediction command for either validated WT or T315I FASTA."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fasta", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, help="Defaults to manifest.json alongside the FASTA")
    parser.add_argument("--output", type=Path, required=True, help="New run directory, also retained on backend failure")
    parser.add_argument("--backend", choices=["esmfold", "fixture"], default="esmfold")
    parser.add_argument("--python", default=sys.executable, help="Python executable with the optional fold dependencies")
    parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    parser.add_argument("--num-recycles", type=int, default=3, help="Additional passes after the initial pass; default 3 = 4 total")
    parser.add_argument("--chunk-size", type=int, default=128)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=1200, help="Inference wall-clock limit; probe gets at most 60s separately")
    parser.add_argument("--cache", type=Path, default=Path(".protein-cache/structures"))
    parser.add_argument("--no-cache", action="store_true", help="Bypass prediction-cache reads and writes")
    parser.add_argument("--allow-model-download", action="store_true", help="Permit pinned checkpoint download; sequences stay local")
    args = parser.parse_args(argv)
    try:
        config = PredictionConfig(args.backend, "cpu" if args.backend == "fixture" else args.device,
                                  args.num_recycles, args.chunk_size, args.seed)
        result = run_prediction(args.fasta, args.output, manifest=args.manifest, config=config,
                                python=args.python, cache=None if args.no_cache else args.cache,
                                timeout=args.timeout, local_files_only=not args.allow_model_download)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Structure input failed: {exc}\n")
    print(json.dumps({"status": result.status, "manifest": str(result.manifest_path),
                      "structure": str(result.structure_path) if result.structure_path else None,
                      "cache_hit": result.cache_hit}))
    if result.status != "succeeded":
        print(f"Structure prediction failed: {_json(result.manifest_path)['error']}", file=sys.stderr)
    return 0 if result.status == "succeeded" else 2


if __name__ == "__main__":
    raise SystemExit(main())
