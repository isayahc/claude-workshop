"""Record real Orbital Studio MCP calls against explicitly synthetic fixtures.

This recorder is not a chemistry solver or a machine-release mechanism. It keeps
raw results and file hashes; successful protocol execution never approves a cure.
"""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import math
from pathlib import Path, PurePosixPath
import platform
import subprocess
import sys

TOOLS = frozenset({"inspect_cube", "inspect_transitions", "broaden_spectrum",
                   "export_orbital", "export_spectrum"})
WARNING = "SYNTHETIC FIXTURES ONLY - NOT PHOTOINITIATOR OR CURE-PROCESS DATA"
MAX_INPUT_BYTES = 40 * 1024 * 1024


def relative_name(value):
    """Accept portable, relative file names, never traversal or drive paths."""
    if (not isinstance(value, str) or not value or len(value) > 1024
            or any(c in value for c in ("\\", ":", "\0"))
            or PurePosixPath(value).is_absolute()
            or any(p in ("", ".", "..") for p in value.split("/"))):
        raise ValueError("Expected a portable relative file name")
    return value


def validate_plan(plan):
    if not isinstance(plan, dict) or plan.get("schema_version") != "1":
        raise ValueError("Expected benchmark plan schema_version 1")
    if plan.get("evidence_scope") != "synthetic_fixture":
        raise ValueError("This recorder only accepts explicitly synthetic fixtures")
    if not isinstance(plan.get("benchmark_id"), str) or not plan["benchmark_id"].strip():
        raise ValueError("benchmark_id is required")
    inputs = plan.get("inputs")
    if not isinstance(inputs, list) or not inputs or len(inputs) > 50:
        raise ValueError("Expected 1-50 declared inputs")
    names = [relative_name(item["filename"]) for item in inputs]
    if len(names) != len(set(names)):
        raise ValueError("Input names must be unique")
    if any(not isinstance(item.get("provenance"), str) or not item["provenance"].strip()
           for item in inputs):
        raise ValueError("Every input needs explicit provenance")
    calls = plan.get("calls")
    if not isinstance(calls, list) or not 1 <= len(calls) <= 50:
        raise ValueError("Expected 1-50 tool calls")
    for call in calls:
        if call.get("name") not in TOOLS:
            raise ValueError("Only Orbital Studio inspection/export tools are allowed")
        args = call.get("arguments")
        if not isinstance(args, dict) or args.get("filename") not in names:
            raise ValueError("Each call must reference a declared input")
    return plan


def fingerprint(path):
    content = path.read_bytes()
    return {"sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content)}


def snapshot_inputs(plan, data_dir, destination):
    root = data_dir.resolve(strict=True)
    records = []
    for item in plan["inputs"]:
        name = relative_name(item["filename"])
        source = (root / name).resolve(strict=True)
        if not source.is_relative_to(root) or not source.is_file():
            raise ValueError("Input must be a regular file inside the data directory")
        with source.open("rb") as stream:
            content = stream.read(MAX_INPUT_BYTES + 1)
        if len(content) > MAX_INPUT_BYTES:
            raise ValueError("Input exceeds 40 MiB")
        blob_sha = hashlib.sha1(b"blob " + str(len(content)).encode("ascii") + b"\0" + content).hexdigest()
        if item.get("source_blob_sha1") and item["source_blob_sha1"] != blob_sha:
            raise ValueError("Input no longer matches its declared repository fixture: " + name)
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        records.append({**item, "path": "inputs/" + name,
                        "classification": "Observed", "observed_blob_sha1": blob_sha, **fingerprint(target)})
    return records


def spectrum_summary(spectrum):
    """Derive only numerical diagnostics from a returned, synthetic spectrum."""
    area = float(spectrum["integrated_oscillator_strength"])
    total = float(spectrum["total_oscillator_strength"])
    if not all(math.isfinite(x) and x >= 0 for x in (area, total)):
        raise ValueError("Invalid observed spectral areas")
    return {
        "evidence_scope": "synthetic_fixture",
        "observed": {"classification": "Observed", "sample_count": len(spectrum["energy_ev"]),
                     "integrated_oscillator_strength": area, "total_oscillator_strength": total,
                     "intensity_unit": "oscillator_strength/eV"},
        "derived": {"classification": "Derived", "absolute_area_error": abs(area - total),
                    "relative_area_error": abs(area - total) / total if total else None,
                    "formula": "abs(integrated_area - total_strength) / total_strength",
                    "zero_strength_note": "Relative error undefined when total strength is zero"},
        "caveats": spectrum["caveats"],
    }


def empty_record(plan):
    return {
        "schema_version": "1", "benchmark_id": plan["benchmark_id"],
        "evidence_scope": "synthetic_fixture", "warning": WARNING,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "tool_execution_status": "not_started", "input_artifacts": [], "calls": [],
        "generated_artifacts": [], "spectral_diagnostics": [],
        "engineering_decision": {
            "status": "blocked_missing_material_and_process_data", "release_allowed": False,
            "selected_wavelength_nm": None, "required_optical_power_w": None,
            "irradiance_w_cm2": None, "required_dose_j_cm2": None,
            "exposure_seconds": None, "maximum_part_temperature_c": None,
            "throughput_parts_per_hour": None,
            "reason": "Synthetic tool success is not evidence of material suitability or cure performance.",
        },
    }


async def exercise(plan, output, record):
    # Lazy imports let contract tests run without the optional MCP dependencies.
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=sys.executable, args=[
        "-m", "orbital_viewer.mcp_server", "--data-dir", str(output / "inputs"),
        "--output-dir", str(output / "exports")])
    async with asyncio.timeout(120):
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=30)) as session:
                record["server"] = (await session.initialize()).model_dump(mode="json")
                discovery = await session.list_tools()
                record["tool_discovery"] = discovery.model_dump(mode="json")
                available = {tool.name for tool in discovery.tools}
                for index, call in enumerate(plan["calls"], 1):
                    entry = {"sequence": index, **call, "status": "started"}
                    record["calls"].append(entry)
                    if call["name"] not in available:
                        raise RuntimeError("Required tool not discovered: " + call["name"])
                    result = await session.call_tool(call["name"], call["arguments"])
                    entry["response"] = result.model_dump(mode="json")
                    if result.isError or not isinstance(result.structuredContent, dict):
                        entry["status"] = "failed"
                        raise RuntimeError("MCP call failed: " + call["name"])
                    data = result.structuredContent
                    if data.get("schema_version") != "1" or not data.get("caveats"):
                        raise RuntimeError("Missing versioned scientific caveats")
                    if call["name"] == "broaden_spectrum":
                        record["spectral_diagnostics"].append({"call_sequence": index, **spectrum_summary(data)})
                    if call["name"].startswith("export_"):
                        path = (output / "exports" / relative_name(data["filename"])).resolve(strict=True)
                        if not path.is_relative_to(output / "exports") or not path.is_file():
                            raise RuntimeError("Export escaped the configured output directory")
                        meta = fingerprint(path)
                        if path.as_uri() != data["uri"] or meta["size_bytes"] != data["size_bytes"]:
                            raise RuntimeError("Export metadata does not match the actual file")
                        record["generated_artifacts"].append({"call_sequence": index,
                            "path": path.relative_to(output).as_posix(), "classification": "Observed",
                            "evidence_scope": "synthetic_fixture", "media_type": data["media_type"], **meta})
                    entry["status"] = "succeeded"
                    print(f"MCP {index}: {call['name']} succeeded (synthetic fixture)", flush=True)


def run(plan_path, data_dir, output):
    plan_bytes = plan_path.read_bytes()
    plan = validate_plan(json.loads(plan_bytes))
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)  # Never mix a new run with stale evidence.
    record = empty_record(plan)
    record["plan_sha256"] = hashlib.sha256(plan_bytes).hexdigest()
    record["python_version"] = platform.python_version()
    package_dir = Path(__file__).resolve().parent
    record["implementation_artifacts"] = [
        {"path": "orbital_viewer/" + source.name, **fingerprint(source)}
        for source in sorted(package_dir.glob("*.py"))]
    record["package_versions"] = {}
    for package in ("orbital-studio", "mcp", "numpy", "plotly", "scikit-image", "cclib"):
        try:
            record["package_versions"][package] = version(package)
        except PackageNotFoundError:
            record["package_versions"][package] = None
    try:
        record["source_revision"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parent,
            stderr=subprocess.DEVNULL, text=True, timeout=5).strip()
    except (OSError, subprocess.SubprocessError):
        record["source_revision"] = None
    (output / "plan.json").write_bytes(plan_bytes)
    (output / "README.txt").write_text(WARNING + "\nSee run.json for inputs, actual MCP responses, caveats, hashes, and the blocked engineering decision.\nRaw server exports are unchanged; they are not measured absorption or real molecular orbitals.\n", encoding="utf-8")
    try:
        record["input_artifacts"] = snapshot_inputs(plan, data_dir, output / "inputs")
        record["tool_execution_status"] = "running"
        asyncio.run(exercise(plan, output, record))
        for item in record["input_artifacts"]:
            if fingerprint(output / item["path"])["sha256"] != item["sha256"]:
                raise RuntimeError("An input snapshot changed during execution")
        record["tool_execution_status"] = "passed"
    except Exception as exc:
        record["tool_execution_status"] = "failed"
        record["error"] = {"type": type(exc).__name__, "message": str(exc)}
        for entry in record["calls"]:
            if entry["status"] == "started":
                entry["status"] = "failed"
    finally:
        record["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        (output / "run.json").write_text(json.dumps(record, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: record[key] for key in ("tool_execution_status", "spectral_diagnostics", "engineering_decision")}, indent=2))
    return 0 if record["tool_execution_status"] == "passed" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="New directory; must not already exist")
    args = parser.parse_args()
    try:
        return run(args.plan, args.data_dir, args.output)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"Benchmark input/output error: {exc}\n")


if __name__ == "__main__":
    sys.exit(main())
