"""Reproduce MAT-01 evidence and actual MCP smoke tests, never qualify a window."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import shutil
import sys
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from orbital_viewer.benchmark import fingerprint, relative_name, run as record_mcp


def read_json(path: Path) -> Any:
    """Read JSON while rejecting non-standard nonfinite values."""
    def invalid(value: str) -> None:
        raise ValueError("Nonfinite JSON value: " + value)
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid)


def write_json(path: Path, value: Any) -> None:
    """Write portable evidence without NaN/Infinity literals."""
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def optical_gate(points: list[list[float]] | None, minimum: float | None,
                 required_nm: tuple[float, float] = (280, 400), *,
                 coverage_validated: bool = False) -> str:
    """Gate supplied acceptance values without interpolation or averaging.

    This is a benchmark check, not an implemented material-data platform. A
    reviewer must establish measurement adequacy and uncertainty treatment.
    Supplier single-point minimum specifications are NOT measured samples and
    must not be passed as exact transmission measurements. No real candidate
    has a measured input array in this benchmark.
    """
    lo, hi = required_nm
    if not all(math.isfinite(v) and v > 0 for v in (lo, hi)) or lo >= hi:
        raise ValueError("Required band must be positive and increasing")
    if minimum is not None and (type(minimum) not in (int, float)
                               or not math.isfinite(minimum) or not 0 <= minimum <= 1):
        raise ValueError("Minimum must be a finite transmission fraction")
    previous = -math.inf
    for wavelength, transmission in points or []:
        if (type(wavelength) not in (int, float) or type(transmission) not in (int, float)
                or not math.isfinite(wavelength) or wavelength <= previous or wavelength <= 0
                or not math.isfinite(transmission) or not 0 <= transmission <= 1):
            raise ValueError("Samples need increasing wavelengths and finite fractions")
        previous = wavelength
    if minimum is None or not points:
        return "unknown"
    selected = [(w, t) for w, t in points if lo <= w <= hi]
    if any(t < minimum for _, t in selected):
        return "fail"
    if (not selected or not coverage_validated
            or selected[0][0] > lo or selected[-1][0] < hi):
        return "unknown"
    return "pass"


def mapping_checks(mapping: dict[str, Any]) -> dict[str, Any]:
    """Check exported JSON Schema and proposal relationships; never import."""
    schema = read_json(BASE / "hardware-ir.schema.json")
    provenance = read_json(BASE / "schema-provenance.json")
    if fingerprint(BASE / "hardware-ir.schema.json")["sha256"] != provenance["schema_sha256"]:
        raise ValueError("Pinned Forma JSON Schema changed")
    jsonschema.Draft202012Validator(schema).validate(mapping)
    parts = {p["part_definition_id"]: p for p in mapping["part_definitions"]}
    instances = {c["ref_des"]: c for c in mapping["components"]}
    if len(parts) != len(mapping["part_definitions"]) or len(instances) != len(mapping["components"]):
        raise ValueError("Duplicate part or instance ID")
    if any(c["part_definition_id"] not in parts or "quantity" in c for c in instances.values()):
        raise ValueError("Invalid physical instance reference")
    seen: list[str] = []
    for row in mapping["bom"]:
        part = parts.get(row["part_definition_id"])
        refs = row["instance_refs"]
        if part is None or row["quantity"] != len(refs) or len(refs) != len(set(refs)):
            raise ValueError("Invalid BOM part or quantity")
        if any(ref not in instances or instances[ref]["part_definition_id"] != row["part_definition_id"] for ref in refs):
            raise ValueError("Unresolved BOM instance")
        for key in ("part_number", "manufacturer", "name", "category", "unit_price", "sourcing_url"):
            if row.get(key) != part.get(key):
                raise ValueError("BOM differs from shared part: " + key)
        if not math.isfinite(row["extended_price"]) or not math.isclose(row["extended_price"], row["quantity"] * row["unit_price"]):
            raise ValueError("BOM extended price mismatch")
        seen.extend(refs)
    if Counter(seen) != Counter({ref: 1 for ref in instances}):
        raise ValueError("Every instance must occur exactly once in BOM")
    if (mapping.get("is_valid") is not False or not mapping["validation"]["critical"]
            or mapping["assembly_metadata"].get("production_release") is not False):
        raise ValueError("MAT-01 proposal must preserve qualification/release blocks")
    return {"json_schema": "passed", "relationships": "passed", "schema_revision": provenance["source_revision"],
            "pydantic_model_validation": "recorded separately in forma-model-check.json; not rerun by this command",
            "caid_import_performed": False, "production_qualification": False}


def audit_inputs() -> dict[str, Any]:
    """Validate research references and prevent synthetic evidence promotion."""
    data = {name: read_json(BASE / (name + ".json")) for name in
            ("sources", "evidence", "candidates", "requirements", "decision", "friction", "handoffs", "material-entry.proposed")}
    sources = {s["source_id"] for s in data["sources"]}
    evidence = {e["evidence_id"]: e for e in data["evidence"]}
    if len(sources) != len(data["sources"]) or len(evidence) != len(data["evidence"]):
        raise ValueError("Duplicate source/evidence ID")
    for item in evidence.values():
        if item["classification"] not in {"Observed", "Derived", "External knowledge", "Assumed"}:
            raise ValueError("Unknown claim classification")
        if not set(item["source_ids"]) <= sources or not all(item[k] for k in ("origin", "units", "conditions", "limitations")):
            raise ValueError("Incomplete claim provenance")
    for candidate in data["candidates"]:
        if not candidate["grade"] or not candidate["configuration"]:
            raise ValueError("Candidate needs grade and configuration")
        for ref in candidate["evidence_ids"]:
            if ref not in evidence or not evidence[ref]["decision_use"]:
                raise ValueError("Candidate references absent or smoke-only evidence")
    if evidence["O501"]["decision_use"] or evidence["O502"]["decision_use"]:
        raise ValueError("Smoke evidence cannot drive material selection")
    if data["decision"]["production_release"] is not False or data["decision"]["preference_scoring"]["applied"]:
        raise ValueError("Unresolved MAT-01 gates cannot release or rank materials")
    model_check = read_json(BASE / "forma-model-check.json")
    if model_check["proposal_input_sha256"] != fingerprint(BASE / "material-entry.proposed.json")["sha256"]:
        raise ValueError("Proposal changed since actual Pydantic validation; rerun verify_forma.py")
    if model_check["serialized_proposal_sha256"] != fingerprint(BASE / "hardware-ir.proposed.json")["sha256"]:
        raise ValueError("Serialized Forma proposal changed")
    data["serialized_proposal"] = read_json(BASE / "hardware-ir.proposed.json")
    if data["serialized_proposal"] != data["material-entry.proposed"]["proposed_mapping"]:
        raise ValueError("Serialized proposal differs from assessed input")
    data["mapping_checks"] = mapping_checks(data["serialized_proposal"])
    return data


def derived_values(data: dict[str, Any]) -> dict[str, Any]:
    """Recompute only geometry/mass diagnostics from identified input evidence."""
    e = {row["evidence_id"]: row["values"] for row in data["evidence"]}
    fs_mass = math.pi * (e["E101"]["diameter_mm"] / 2) ** 2 * e["E101"]["thickness_mm"] * e["E103"]["density_g_cm3"] / 1000
    pmma_mass = math.pi * (e["A01"]["diameter"] / 2) ** 2 * e["E201"]["sheet_thickness_mm"] * e["E203"]["density_g_cm3"] / 1000
    return {"classification": "Derived", "FS_ideal_nominal_disc_mass_g": fs_mass,
            "PMMA_ideal_proposed_disc_mass_g": pmma_mass, "mass_equation": "pi*(diameter_mm/2)^2*thickness_mm*density_g_cm3/1000",
            "mass_input_evidence_ids": ["E101", "E103", "E201", "E203", "A01"],
            "mass_limitations": "Ideal cylinders; no bevels, tolerances, coating or mount. PMMA diameter is assumed.",
            "PC_nominal_thickness_mm": e["E301"]["thickness_in"] * 25.4,
            "PC_equation": "E301.thickness_in * 25.4 mm/inch", "PC_input_evidence_ids": ["E301"],
            "full_band_or_sensor_weighted_transmission": None,
            "transmission_reason": "No matched measured wavelength arrays, threshold, detector response or illumination spectrum. No interpolation, extrapolation or thickness scaling."}


def verify_smoke(output: Path, plan: dict[str, Any], record: dict[str, Any]) -> None:
    """Check exact MCP sequence, response equivalence, inventory and file hashes."""
    if record["evidence_scope"] != "synthetic_fixture" or record["engineering_decision"]["release_allowed"] is not False:
        raise ValueError("Invalid smoke scope or release claim")
    if fingerprint(output / "plan.json")["sha256"] != record["plan_sha256"] or read_json(output / "plan.json") != plan:
        raise ValueError("Recorded plan mismatch")
    calls = record["calls"]
    if len(calls) != len(plan["calls"]):
        raise ValueError("Incomplete MCP call sequence")
    inventory = {item["name"] for item in record["tool_discovery"]["tools"]}
    if not {item["name"] for item in plan["calls"]} <= inventory:
        raise ValueError("Missing discovered tool")
    for actual, expected in zip(calls, plan["calls"]):
        if any(actual[k] != expected[k] for k in ("name", "arguments")) or actual["status"] != "succeeded":
            raise ValueError("Recorded MCP call differs from plan")
        response = actual["response"]
        if response["isError"] or not response["structuredContent"].get("caveats"):
            raise ValueError("Invalid MCP response")
        texts = [item["text"] for item in response["content"] if item["type"] == "text"]
        if len(texts) != 1 or json.loads(texts[0]) != response["structuredContent"]:
            raise ValueError("MCP text/structured response mismatch")
    for artifact in record["input_artifacts"] + record["generated_artifacts"]:
        path = (output / relative_name(artifact["path"])).resolve(strict=True)
        if not path.is_relative_to(output.resolve()) or fingerprint(path)["sha256"] != artifact["sha256"]:
            raise ValueError("Recorded input/export hash mismatch")


def reproduce(output: Path) -> int:
    """Record a new complete evidence bundle and propagate MCP failures."""
    data = audit_inputs()
    result = record_mcp(BASE / "plan.json", ROOT / "examples/mcp", output)
    record = read_json(output / "run.json")
    plan = read_json(BASE / "plan.json")
    if result == 0:
        verify_smoke(output, plan, record)
    minimum = next(r["value"] for r in data["requirements"] if r["requirement_id"] == "R02")
    gates = [{"candidate_id": c["candidate_id"],
              "optical_gate": optical_gate(c["optical"]["full_band_transmission_fraction"], minimum),
              "mechanical_gate": "unknown", "environmental_gate": "unknown", "production_release": False}
             for c in data["candidates"]]
    statuses = {"material_decision": "Conditional", "orbital_execution": "Complete" if result == 0 else "Blocked",
                "candidate_specific_orbital_analysis": "Blocked", "caid_schema_validation": "Complete",
                "caid_export_integration": "Blocked", "design_qualification": "Blocked"}
    assessment = {"benchmark_id": "MAT-01", "statuses": statuses, "decision": data["decision"],
                  "qualification_gates": gates, "derived": derived_values(data), "mapping_checks": data["mapping_checks"],
                  "orbital_scope": "Actual MCP synthetic smoke tests only; no demonstrated material-selection value",
                  "caid_scope": "Pinned local schema checked; no target-project application import",
                  "candidate_specific_orbital_runs": 0, "production_release": False}
    write_json(output / "assessment.json", assessment)
    shutil.copyfile(BASE / "hardware-ir.proposed.json", output / "hardware-ir.proposed.json")
    shutil.copyfile(BASE / "README.md", output / "benchmark-report.md")
    inputs = []
    for source in sorted(BASE.glob("*")):
        if source.suffix not in {".json", ".py", ".md"}:
            continue
        target = output / "assessment-inputs" / source.name
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(source, target)
        inputs.append({"path": target.relative_to(output).as_posix(), **fingerprint(target)})
    outputs = [{"path": name, **fingerprint(output / name)} for name in
               ("run.json", "assessment.json", "hardware-ir.proposed.json", "benchmark-report.md")]
    counts = Counter(call["status"] for call in record["calls"])
    manifest = {"benchmark_id": "MAT-01", "run_id": output.name,
                "created_at_utc": datetime.now(timezone.utc).isoformat(), "source_revision": record["source_revision"],
                "execution_route": "orbital_viewer.benchmark: real stdio MCP; research assessment offline",
                "statuses": statuses, "actual_mcp_successes": counts["succeeded"], "actual_mcp_failures": counts["failed"],
                "export_count": len(record["generated_artifacts"]), "candidate_specific_orbital_runs": 0,
                "manual_handoffs": data["handoffs"], "input_artifacts": inputs, "output_artifacts": outputs,
                "raw_mcp_record": "run.json", "elapsed_task_time": None, "task_cost": None,
                "production_release": False, "caid_import_performed": False}
    write_json(output / "manifest.json", manifest)
    print(json.dumps({"statuses": statuses, "mcp_successes": counts["succeeded"], "exports": len(record["generated_artifacts"])}))
    return result


def main() -> None:
    """Use a fresh directory, retaining failures without claiming success."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New run directory")
    args = parser.parse_args()
    sys.exit(reproduce(args.output.resolve()))


if __name__ == "__main__":
    main()
