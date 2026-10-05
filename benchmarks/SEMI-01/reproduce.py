"""Build SEMI-01's evidence bundle using the actual local MCP server."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from orbital_viewer.benchmark import fingerprint, relative_name, run as record_mcp
from orbital_viewer.semiconductor_screen import assess, run as screen

SCHEMA = ROOT / "benchmarks/MAT-01/hardware-ir.schema.json"
SCHEMA_PROVENANCE = ROOT / "benchmarks/MAT-01/schema-provenance.json"
SCHEMA_HASH = "571773e3def3e9fcae64b33e0c8a27524d3a4f661c385a2895124cefc916bd25"
INPUT_NAMES = ("design.json", "sources.json", "requirements.json", "workflow.json", "hardware-ir.proposed.json")


def read(path):
    def invalid(value):
        raise ValueError("Nonfinite JSON: " + value)
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid)


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def validate_proposal(proposal, design, requirements):
    if fingerprint(SCHEMA)["sha256"] != SCHEMA_HASH:
        raise ValueError("Pinned Forma schema changed")
    jsonschema.Draft202012Validator(read(SCHEMA)).validate(proposal)
    metadata = proposal["assembly_metadata"]
    sidecar = metadata["semi01"]
    if (proposal["hardware_ir_version"] != "0.2" or proposal["is_valid"] is not False
            or metadata["production_release"] is not False or not proposal["validation"]["critical"]):
        raise ValueError("Requirements proposal must retain its qualification/release blocks")
    if any(proposal[key] for key in ("part_definitions", "components", "bom")):
        raise ValueError("No parts or BOM have been selected for SEMI-01")
    if (sidecar["requirements"] != requirements["requirements"]
            or sidecar["voltage_requirement"] != design["voltage_requirement"]
            or sidecar["operating_point"] != design["operating_point"]):
        raise ValueError("Hardware IR lost the engineering inputs")
    if any(sidecar[key] is not None for key in
           ("selected_technology", "selected_part_number", "approved_bus_voltage_v", "module_cost")):
        raise ValueError("Unresolved selections and costs must remain null")
    if ("estimated_cost" in proposal["overview"] or "estimated_current_draw_ma" in proposal
            or "requirements" in proposal):
        raise ValueError("Do not turn schema defaults into unobserved cost, current or operating voltage")
    if json.loads(json.dumps(proposal, allow_nan=False)) != proposal:
        raise ValueError("JSON serialization did not preserve the proposal")
    return {"json_schema_validation": "passed", "evidence_and_nulls_preserved": True,
            "schema_source_revision": read(SCHEMA_PROVENANCE)["source_revision"],
            "schema_sha256": SCHEMA_HASH, "pydantic_model_validation_performed": False,
            "current_live_schema_verified": False, "caid_import_performed": False,
            "production_release": False,
            "scope": "Pinned JSON Schema and explicit benchmark invariants; not model defaults, application integration or physical qualification"}


def audit_inputs():
    data = {name: read(BASE / name) for name in INPUT_NAMES}
    design = data["design.json"]
    assess(design)
    sources = data["sources.json"]["sources"]
    source_ids = {item["id"] for item in sources}
    if len(source_ids) != len(sources) or any(not item[k] for item in sources for k in ("url", "locator", "access", "limitation")):
        raise ValueError("Source provenance is incomplete")
    for candidate in design["candidates"]:
        if (not set(candidate["source_ids"]) <= source_ids
                or not set(candidate["voltage_class"]["source_ids"]) <= source_ids
                or candidate["classification"] != "External knowledge"):
            raise ValueError("Unresolved commercial source")
        if candidate["scientific_artifacts"] or candidate["matched_operating_point_losses_w"] is not None:
            raise ValueError("This benchmark has no candidate calculations or matched loss evidence")
    if (not set(design["proposal"]["source_ids"]) <= source_ids
            or design["proposal"]["classification"] != "Assumed"
            or any(design["proposal"][key] is not None for key in ("selected_technology", "selected_part_number"))):
        raise ValueError("Provisional recommendation must remain an assumption")
    requirements = data["requirements.json"]
    ids = {r["id"] for r in requirements["requirements"]}
    if len(ids) != len(requirements["requirements"]) or any(r["status"] != "unresolved" for r in requirements["requirements"]):
        raise ValueError("Requirements must be unique and unresolved")
    workflow = data["workflow.json"]
    if workflow["execution_status"] != "proposed_not_executed" or workflow["cots_selection_requires_new_dft"] is not False:
        raise ValueError("Do not claim upstream computation or require DFT for COTS selection")
    covered = {r for handoff in workflow["manual_handoffs"] for r in handoff["requirement_ids"]}
    if covered != ids:
        raise ValueError("Every requirement needs an identified manual handoff")
    jobs = {job["id"]: job for job in workflow["jobs"]}
    if len(jobs) != len(workflow["jobs"]):
        raise ValueError("Duplicate upstream job")
    visited = set()
    def visit(key, active):
        if key not in jobs or key in active:
            raise ValueError("Unresolved or cyclic upstream dependency")
        if key in visited:
            return
        for parent in jobs[key]["depends_on"]:
            visit(parent, active | {key})
        visited.add(key)
    for job in jobs.values():
        if job["status"] not in {"not_run", "blocked_missing_inputs"}:
            raise ValueError("Upstream jobs have not run")
        visit(job["id"], set())
    data["mapping_check"] = validate_proposal(data["hardware-ir.proposed.json"], design, requirements)
    return data


def verify_smoke(output):
    record = read(output / "run.json")
    plan = read(output / "plan.json")
    if (record["tool_execution_status"] != "passed" or record["evidence_scope"] != "synthetic_fixture"
            or record["engineering_decision"]["release_allowed"] is not False):
        raise ValueError("MCP run failed or promoted synthetic evidence")
    if fingerprint(output / "plan.json")["sha256"] != record["plan_sha256"] or plan != read(BASE / "plan.json"):
        raise ValueError("MCP plan mismatch")
    if len(record["calls"]) != 2 or len(record["generated_artifacts"]) != 1 or record["spectral_diagnostics"]:
        raise ValueError("SEMI-01 uses only two CUBE software checks and one export")
    inventory = {t["name"]: t for t in record["tool_discovery"]["tools"]}
    for actual, expected in zip(record["calls"], plan["calls"]):
        if any(actual[k] != expected[k] for k in ("name", "arguments")) or actual["status"] != "succeeded":
            raise ValueError("MCP call differs from the plan")
        response = actual["response"]
        if response["isError"] or not response["structuredContent"].get("caveats"):
            raise ValueError("MCP response error or missing caveats")
        schema = inventory[actual["name"]]
        jsonschema.validate(actual["arguments"], schema["inputSchema"])
        jsonschema.validate(response["structuredContent"], schema["outputSchema"])
        texts = [item["text"] for item in response["content"] if item["type"] == "text"]
        if len(texts) != 1 or json.loads(texts[0]) != response["structuredContent"]:
            raise ValueError("MCP text and structured responses differ")
    for item in record["input_artifacts"] + record["generated_artifacts"]:
        path = (output / relative_name(item["path"])).resolve(strict=True)
        if not path.is_relative_to(output.resolve()) or fingerprint(path) != {k: item[k] for k in ("sha256", "size_bytes")}:
            raise ValueError("Input/export integrity failure")
    if any(record["engineering_decision"][key] is not None for key in plan["unknown_quantities"]):
        raise ValueError("Fixture-derived material/device quantities must remain unknown")


def reproduce(output):
    data = audit_inputs()
    if record_mcp(BASE / "plan.json", ROOT / "examples/mcp", output):
        raise RuntimeError("Actual stdio MCP execution failed; inspect run.json")
    verify_smoke(output)
    for name in INPUT_NAMES:
        shutil.copyfile(BASE / name, output / name)
    shutil.copyfile(BASE / "README.md", output / "benchmark-report.md")
    shutil.copyfile(SCHEMA, output / "hardware-ir.schema.json")
    shutil.copyfile(SCHEMA_PROVENANCE, output / "schema-provenance.json")
    screen(output / "design.json", output / "assessment.json")
    write(output / "mapping-check.json", data["mapping_check"])
    source_paths = sorted(p for p in BASE.iterdir() if p.is_file()) + [
        Path(__file__), ROOT / "orbital_viewer/semiconductor_screen.py",
        ROOT / "tests/test_semiconductor_benchmark.py", ROOT / ".github/workflows/test.yml", SCHEMA, SCHEMA_PROVENANCE]
    source_paths = sorted(set(source_paths))
    write(output / "evidence-manifest.json", {
        "benchmark_id": "SEMI-01", "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_revision": read(output / "run.json")["source_revision"],
        "source_files": [{"path": p.relative_to(ROOT).as_posix(), **fingerprint(p)} for p in source_paths],
        "bundle_files": [{"path": p.relative_to(output).as_posix(), **fingerprint(p)}
                         for p in sorted(output.rglob("*")) if p.is_file()],
        "release_allowed": False, "scientific_calculations_performed": False,
        "browser_render_verified": False})
    return read(output / "assessment.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Fresh output directory")
    args = parser.parse_args()
    result = reproduce(args.output.resolve())
    print(json.dumps(result["engineering_decision"], indent=2))


if __name__ == "__main__":
    main()
