"""Run fpocket on a validated ABL1 structure, then explicitly select a docking box."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any

from protein_workflow import folding
from protein_workflow.pocket_io import (PocketError, PocketTimeout, parse_pockets,
                                       pdb_atoms, propose_box, read_bytes, read_text)
from protein_workflow.sequences import sha256, utc_now


@dataclass(frozen=True)
class PocketConfig:
    """Explicit fpocket detection settings; lengths are angstroms, counts are integers."""

    min_alpha_radius: float = 3.4
    max_alpha_radius: float = 6.2
    clustering_distance: float = 2.4
    min_spheres: int = 15
    monte_carlo_iterations: int = 300

    def arguments(self) -> list[str]:
        """Validate and translate the supported settings to fpocket 4.x arguments."""
        for value in (self.min_alpha_radius, self.max_alpha_radius, self.clustering_distance):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 100:
                raise PocketError("Detection distances must be finite, positive and at most 100 angstroms.")
        if self.min_alpha_radius >= self.max_alpha_radius:
            raise PocketError("Minimum alpha radius must be smaller than maximum alpha radius.")
        for value in (self.min_spheres, self.monte_carlo_iterations):
            if type(value) is not int or not 1 <= value <= 1_000_000:
                raise PocketError("Sphere/Monte Carlo counts must be integers in 1..1000000.")
        return ["-m", str(self.min_alpha_radius), "-M", str(self.max_alpha_radius),
                "-D", str(self.clustering_distance), "-i", str(self.min_spheres),
                "-v", str(self.monte_carlo_iterations)]


@dataclass(frozen=True)
class StructureInput:
    """Verified #5 structure and all archived artifacts needed to reproduce its mapping."""

    manifest: dict[str, Any]
    validation: dict[str, Any]
    pdb: str
    files: dict[str, bytes]


@dataclass(frozen=True)
class PocketResult:
    """Terminal detection state, including inspectable failure receipts."""

    status: str
    manifest_path: Path
    pockets_path: Path | None
    count: int


def read_json(path: Path) -> dict[str, Any]:
    """Read finite, object-valued JSON with the same bounds as other pocket artifacts."""
    value = json.loads(read_bytes(path))
    if not isinstance(value, dict):
        raise PocketError(f"Expected JSON object: {path}")
    json.dumps(value, allow_nan=False)
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    """Atomically publish a receipt or status update with finite JSON values."""
    temporary = path.with_name(path.name + ".pending")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="ascii")
    temporary.replace(path)


def receipt(content: bytes) -> dict[str, Any]:
    """Describe the exact bytes of an artifact, independent of its location."""
    return {"sha256": sha256(content), "bytes": len(content)}


def verified_files(directory: Path, artifacts: dict[str, Any]) -> dict[str, bytes]:
    """Verify relative regular-file artifacts without following links outside the bundle."""
    files: dict[str, bytes] = {}
    for name, expected in artifacts.items():
        relative = Path(name)
        path = directory / relative
        if (relative.is_absolute() or ".." in relative.parts or not relative.parts
                or any((directory / Path(*relative.parts[:i])).is_symlink()
                       for i in range(1, len(relative.parts) + 1))):
            raise PocketError("Artifact path must stay inside its bundle without symlinks.")
        content = read_bytes(path)
        if receipt(content) != expected:
            raise PocketError(f"Artifact checksum/size mismatch: {name}")
        files[name] = content
    return files


def load_structure_input(manifest_path: Path) -> StructureInput:
    """Revalidate the archived sequence, backend receipt, PDB and complete residue map from #5."""
    data = read_json(manifest_path)
    if (data.get("schema_version") != 1 or data.get("stage") != "structure_prediction"
            or data.get("status") != "succeeded" or data.get("prediction_validated") is not True
            or data.get("structure_artifact") != "raw/structure.pdb"
            or data.get("validation_artifact") != "validation.json"):
        raise PocketError("Expected a successful version-1 structure result from issue #5.")
    files = verified_files(manifest_path.parent, data["artifacts"])
    required = {"raw/structure.pdb", "raw/backend.json", "raw/confidence.json", "validation.json",
                "inputs/manifest.json", "inputs/ABL1_WT.fasta", "inputs/ABL1_T315I.fasta", "inputs/P00519.source.json"}
    if not required <= files.keys():
        raise PocketError("Structure bundle is missing required provenance artifacts.")
    variant = data["variant"]
    if variant not in ("WT", "T315I"):
        raise PocketError("Unknown ABL1 variant.")
    source = folding.load_sequence_input(manifest_path.parent / "inputs" / f"ABL1_{variant}.fasta")
    config = folding.PredictionConfig(**data["configuration"])
    config.validate()
    expected_input = {"fasta": f"inputs/{source.fasta_name}", "manifest": "inputs/manifest.json",
                      "sequence_sha256": sha256(source.sequence.encode("ascii")), "source_isoform": "P00519-1",
                      "domain_start": source.start, "domain_end": source.end}
    if data["input"] != expected_input:
        raise PocketError("Structure receipt disagrees with its archived sequence inputs.")
    with tempfile.TemporaryDirectory(prefix="validate-pocket-input-") as temporary:
        report = Path(temporary) / "validation.json"
        backend = folding._validate_raw(manifest_path.parent / "raw", source, config,
                                        data["identity"]["environment"], report)
        validation = read_json(report)
    if (validation != read_json(manifest_path.parent / "validation.json")
            or backend != data["backend"] or data["classification"] != backend["classification"]):
        raise PocketError("Structure mapping or classification disagrees with the verified backend.")
    files["result.json"] = manifest_path.read_bytes()
    return StructureInput(data, validation, files["raw/structure.pdb"].decode("ascii"), files)


def prepare_receptor(pdb: str) -> str:
    """Zero the pLDDT-bearing B-factor field so fpocket cannot treat confidence as thermal motion."""
    return "\n".join(line[:60] + "  0.00" + line[66:] if line.startswith("ATOM  ") else line
                     for line in pdb.splitlines()) + "\n"


def run_process(command: list[str], directory: Path, prefix: str, timeout: float) -> int:
    """Run without a shell in an isolated working directory; kill/reap the group on interruption."""
    with (directory / f"{prefix}.stdout.log").open("wb") as stdout, (directory / f"{prefix}.stderr.log").open("wb") as stderr:
        process = subprocess.Popen(command, cwd=directory, stdout=stdout, stderr=stderr,
                                   env={**os.environ, "LC_ALL": "C"}, start_new_session=os.name == "posix")
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
                raise PocketTimeout(f"{prefix} exceeded {timeout:g}s; process group terminated.") from exc
            raise
    if code != 0:
        raise PocketError(f"{prefix} exited with code {code}; inspect {prefix}.stderr.log.")
    return code


def execute_fpocket(receptor: str, output: Path, *, executable: str = "fpocket",
                    config: PocketConfig = PocketConfig(), timeout: float = 120,
                    release_label: str | None = None) -> dict[str, Any]:
    """Execute the actual binary and record version, hash, command and failure evidence.

    The controlled relative filename avoids fpocket's internal unquoted mkdir
    commands and its fixed-size filename buffers. The no-argument banner is used
    because ``-v`` means Monte Carlo iterations, not version. Release labels are
    user-supplied provenance, never treated as a verified binary version.
    """
    arguments = config.arguments()
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise PocketError("Timeout must be finite and positive.")
    output.mkdir(parents=True, exist_ok=False)
    (output / "receptor.pdb").write_text(receptor, encoding="ascii")
    state: dict[str, Any] = {"name": "fpocket", "started_at": utc_now(), "status": "running",
                             "configuration": asdict(config), "declared_release": release_label,
                             "declared_release_verified": False, "reported_version": None,
                             "executable_requested": executable, "receptor": receipt(receptor.encode("ascii")),
                             "timeout_seconds": timeout, "coordinates_sent_to_external_service": False,
                             "random_seed_controlled": False}
    start = time.monotonic()
    try:
        resolved = shutil.which(executable)
        if resolved is None:
            raise PocketError(f"fpocket executable not found: {executable}. Install fpocket 4.x; see docs/abl1-pockets.md.")
        binary = Path(resolved).resolve()
        state.update({"executable": str(binary), "executable_sha256": sha256(binary.read_bytes()),
                      "probe_command": [str(binary)], "command": [str(binary), "-f", "receptor.pdb", *arguments],
                      "working_directory": "."})
        write_json(output / "backend.json", state)
        run_process(state["probe_command"], output, "probe", min(timeout, 30))
        banner = re.sub(r"\x1b\[[0-9;]*m", "", read_text(output / "probe.stdout.log") + read_text(output / "probe.stderr.log"))
        version = re.search(r"\bfpocket\s+(\d+\.\d+(?:\.\d+)?)\b", banner, re.IGNORECASE)
        if version is None or not version[1].startswith("4."):
            raise PocketError("Unrecognized/unsupported fpocket version banner; this adapter supports 4.x output.")
        state["reported_version"] = version[1]
        write_json(output / "backend.json", state)
        state["returncode"] = run_process(state["command"], output, "fpocket", timeout)
        stdout, stderr = read_text(output / "fpocket.stdout.log"), read_text(output / "fpocket.stderr.log")
        if ("POCKET HUNTING ENDS" not in stdout
                or re.search(r"\b(error|failed|failure|fatal|invalid|cannot|could not|unable|qhull|segmentation)\b", stdout + stderr, re.IGNORECASE)):
            raise PocketError("fpocket reported incomplete execution or an internal error despite exit zero; inspect logs.")
        state["no_output_no_pockets"] = (not (output / "receptor_out").exists()
                                           and re.search(r"(?im)^no pockets found\s*$", stdout) is not None)
        if not (output / "receptor_out").is_dir() and not state["no_output_no_pockets"]:
            raise PocketError("fpocket produced no output and no unambiguous no-pocket result.")
        state["status"] = "succeeded"
    except BaseException as exc:
        state.update({"status": "timed_out" if isinstance(exc, PocketTimeout) else
                      "cancelled" if isinstance(exc, KeyboardInterrupt) else "failed", "error": str(exc)})
        raise
    finally:
        state.update({"completed_at": utc_now(), "runtime_seconds": time.monotonic() - start})
        write_json(output / "backend.json", state)
    return state


def add_mutation_context(pockets: list[dict[str, Any]], inputs: StructureInput) -> None:
    """Annotate mutation contacts and CA-to-sphere-center distances without selecting a site."""
    target = next(row for row in inputs.validation["residue_mapping"] if row["source_position"] == 315)
    residue = target["structure_residue"]
    atoms = pdb_atoms(inputs.pdb)
    ca = atoms[(residue["chain"], residue["number"], residue["insertion_code"], "CA")]["coordinates"]
    for pocket in pockets:
        pocket["mutation_context"] = {"label": "T315I", "source_position": 315,
                                      "structure_residue": residue, "observed_amino_acid": target["observed_amino_acid"],
                                      "contacted": any(row["source_position"] == 315 for row in pocket["residues"]),
                                      "ca_coordinates": ca, "coordinate_unit": "angstrom",
                                      "nearest_alpha_center_distance": min(math.dist(ca, sphere["center"])
                                                                          for sphere in pocket["geometry"]["alpha_spheres"])}


def run_pockets(structure_result: Path, output: Path, *, executable: str = "fpocket",
                config: PocketConfig = PocketConfig(), timeout: float = 120,
                release_label: str | None = None, allow_illustrative: bool = False) -> PocketResult:
    """Detect cavities independently for either verified variant and retain terminal receipts."""
    config.arguments()
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise PocketError("Timeout must be finite and positive.")
    inputs = load_structure_input(structure_result)
    if inputs.manifest["classification"] == "illustrative" and not allow_illustrative:
        raise PocketError("Illustrative structures have no physical meaning; use --allow-illustrative only for pipeline tests.")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    state: dict[str, Any] = {"schema_version": 1, "stage": "pocket_detection", "status": "running",
                             "started_at": utc_now(), "variant": inputs.manifest["variant"],
                             "classification": inputs.manifest["classification"], "pockets_artifact": None,
                             "pocket_count": 0, "selection": None, "docking_ready": False,
                             "structure_sha256": sha256(inputs.pdb.encode("ascii")),
                             "input_structure_result": "inputs/structure-run/result.json",
                             "input_structure_result_sha256": sha256(inputs.files["result.json"]),
                             "bfactor_policy": "zeroed_for_fpocket; original_pLDDT_preserved_in_structure_bundle_and_mapping",
                             "configuration": asdict(config), "error": None,
                             "implementation": {name: sha256(Path(__file__).with_name(name).read_bytes())
                                                for name in ("pockets.py", "pocket_io.py")}}
    start = time.monotonic()

    def progress(step: str) -> None:
        """Publish a stage boundary and visible progress for long external-tool calls."""
        state["step"] = step
        write_json(output / "status.json", {**state, "updated_at": utc_now()})
        print(f"[{state['variant']}] {step}", file=sys.stderr, flush=True)

    try:
        progress("archiving_structure")
        for name, content in inputs.files.items():
            path = output / "inputs/structure-run" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        receptor = prepare_receptor(inputs.pdb)
        state["receptor_sha256"] = sha256(receptor.encode("ascii"))
        progress("running_fpocket")
        backend = execute_fpocket(receptor, output / "raw", executable=executable, config=config,
                                  timeout=timeout, release_label=release_label)
        state["backend"] = backend
        progress("parsing_pockets")
        pockets = [] if backend["no_output_no_pockets"] else parse_pockets(
            output / "raw/receptor_out", receptor, inputs.validation["residue_mapping"])
        add_mutation_context(pockets, inputs)
        write_json(output / "pockets.json", {"schema_version": 1, "coordinate_unit": "angstrom", "pockets": pockets})
        state.update({"status": "succeeded" if pockets else "no_pockets", "pocket_count": len(pockets),
                      "pockets_artifact": "pockets.json", "receptor_artifact": "raw/receptor.pdb"})
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
        state.update({"status": "timed_out" if isinstance(exc, PocketTimeout) else "failed",
                      "error": str(exc), "failed_step": state.get("step")})
    except KeyboardInterrupt:
        state.update({"status": "cancelled", "error": "Interrupted by user"})
        raise
    finally:
        state.update({"completed_at": utc_now(), "runtime_seconds": time.monotonic() - start})
        state["artifacts"] = {str(path.relative_to(output)): receipt(path.read_bytes())
                              for path in output.rglob("*") if path.is_file() and not path.is_symlink()
                              and path not in (output / "result.json", output / "status.json")}
        write_json(output / "result.json", state)
        progress(state["status"])
    return PocketResult(state["status"], output / "result.json",
                        output / "pockets.json" if state["pockets_artifact"] else None, state["pocket_count"])


def select_pocket(result_path: Path, output: Path, *, pocket_id: str, rationale: str,
                  padding: float = 4.0, center: list[float] | None = None,
                  size: list[float] | None = None) -> Path:
    """Export an explicit pocket choice and a self-contained, structure-bound docking-box proposal."""
    if not rationale.strip():
        raise PocketError("Record a rationale for the explicit pocket choice.")
    data = read_json(result_path)
    if data.get("schema_version") != 1 or data.get("stage") != "pocket_detection" or data.get("status") != "succeeded":
        raise PocketError("Selection requires a successful nonempty pocket result.")
    files = verified_files(result_path.parent, data["artifacts"])
    backend = read_json(result_path.parent / "raw/backend.json")
    if (data["backend"] != backend or backend["status"] != "succeeded"
            or data["configuration"] != backend["configuration"]
            or data["pockets_artifact"] != "pockets.json" or data["receptor_artifact"] != "raw/receptor.pdb"):
        raise PocketError("Pocket result disagrees with its native-tool receipt or artifact contract.")
    inputs = load_structure_input(result_path.parent / "inputs/structure-run/result.json")
    receptor = prepare_receptor(inputs.pdb)
    if (files["raw/receptor.pdb"].decode("ascii") != receptor
            or data["receptor_sha256"] != sha256(receptor.encode("ascii"))
            or data["structure_sha256"] != sha256(inputs.pdb.encode("ascii"))
            or data["input_structure_result_sha256"] != sha256(inputs.files["result.json"])
            or data["classification"] != inputs.manifest["classification"] or data["variant"] != inputs.manifest["variant"]):
        raise PocketError("Pocket result disagrees with its archived structure.")
    pockets = parse_pockets(result_path.parent / "raw/receptor_out", receptor, inputs.validation["residue_mapping"])
    add_mutation_context(pockets, inputs)
    if (len(pockets) != data["pocket_count"] or read_json(result_path.parent / "pockets.json")
            != {"schema_version": 1, "coordinate_unit": "angstrom", "pockets": pockets}):
        raise PocketError("Exported pocket records disagree with the raw fpocket artifacts.")
    pocket = next((row for row in pockets if row["id"] == pocket_id), None)
    if pocket is None:
        raise PocketError(f"Unknown pocket {pocket_id!r}; inspect pockets.json and choose an exact ID.")
    proposal = propose_box(pocket, padding)
    box = proposal.copy()
    if center is not None or size is not None:
        if center is None or size is None or len(center) != 3 or len(size) != 3:
            raise PocketError("Box override requires three center coordinates and three sizes.")
        if (any(type(v) not in (int, float) or not math.isfinite(v) for v in [*center, *size])
                or any(v <= 0 for v in size)):
            raise PocketError("Box coordinates must be finite and sizes positive, in angstroms.")
        box = {**proposal, "center": center, "size": size, "method": "explicit_override", "padding_per_face": None}
    output.mkdir(parents=True, exist_ok=False)
    selected_pocket = {**pocket, "artifacts": {"contact_atoms": "contact-atoms.pdb", "alpha_spheres": "alpha-spheres.pqr"}}
    exports = {"source-result.json": result_path.read_bytes(), "receptor.pdb": receptor.encode("ascii"),
               "pocket.json": (json.dumps(selected_pocket, indent=2, allow_nan=False) + "\n").encode("ascii"),
               "contact-atoms.pdb": files["raw/receptor_out/" + pocket["artifacts"]["contact_atoms"]],
               "alpha-spheres.pqr": files["raw/receptor_out/" + pocket["artifacts"]["alpha_spheres"]]}
    for name, content in exports.items():
        (output / name).write_bytes(content)
    selection = {"schema_version": 1, "stage": "pocket_selection", "status": "proposal", "selected_at": utc_now(),
                 "pocket_id": pocket_id, "selection_method": "explicit", "rationale": rationale.strip(),
                 "variant": data["variant"], "classification": data["classification"],
                 "source_result_sha256": sha256(exports["source-result.json"]),
                 "structure_sha256": data["structure_sha256"], "receptor_sha256": data["receptor_sha256"],
                 "receptor_artifact": "receptor.pdb", "pocket_artifact": "pocket.json",
                 "backend": data["backend"], "box": box, "automatic_box_proposal": proposal,
                 "docking_ready": False, "receptor_preparation_performed": False, "binding_site_validated": False,
                 "artifacts": {name: receipt(content) for name, content in exports.items()}}
    write_json(output / "selection.json", selection)
    return output / "selection.json"


def main(argv: list[str] | None = None) -> int:
    """Expose separate detection and explicit selection commands; never choose rank one implicitly."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    detect = commands.add_parser("detect", help="Run fpocket independently on one #5 structure result")
    detect.add_argument("--structure-result", type=Path, required=True)
    detect.add_argument("--output", type=Path, required=True)
    detect.add_argument("--executable", default="fpocket")
    detect.add_argument("--release-label", help="Optional user-declared install provenance; banner and binary hash are also recorded")
    detect.add_argument("--timeout", type=float, default=120)
    detect.add_argument("--min-alpha-radius", type=float, default=3.4)
    detect.add_argument("--max-alpha-radius", type=float, default=6.2)
    detect.add_argument("--clustering-distance", type=float, default=2.4)
    detect.add_argument("--min-spheres", type=int, default=15)
    detect.add_argument("--monte-carlo-iterations", type=int, default=300)
    detect.add_argument("--allow-illustrative", action="store_true")
    select = commands.add_parser("select", help="Record a reviewed pocket ID and proposed docking box")
    select.add_argument("--result", type=Path, required=True)
    select.add_argument("--output", type=Path, required=True)
    select.add_argument("--pocket", required=True)
    select.add_argument("--rationale", required=True)
    select.add_argument("--padding", type=float, default=4)
    select.add_argument("--center", type=float, nargs=3)
    select.add_argument("--size", type=float, nargs=3)
    args = parser.parse_args(argv)
    try:
        if args.command == "select":
            path = select_pocket(args.result, args.output, pocket_id=args.pocket, rationale=args.rationale,
                                 padding=args.padding, center=args.center, size=args.size)
            print(json.dumps({"status": "proposal", "selection": str(path)}))
            return 0
        config = PocketConfig(args.min_alpha_radius, args.max_alpha_radius, args.clustering_distance,
                              args.min_spheres, args.monte_carlo_iterations)
        result = run_pockets(args.structure_result, args.output, executable=args.executable, config=config,
                             timeout=args.timeout, release_label=args.release_label, allow_illustrative=args.allow_illustrative)
        print(json.dumps({"status": result.status, "manifest": str(result.manifest_path), "pocket_count": result.count}))
        if result.status not in ("succeeded", "no_pockets"):
            print(f"Pocket detection failed: {read_json(result.manifest_path)['error']}", file=sys.stderr)
            return 2
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"Pocket input/selection failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
