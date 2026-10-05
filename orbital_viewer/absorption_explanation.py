"""Build EDU-01's teaching report from a verified synthetic MCP evidence bundle.

This is an explanation of recorded tool outputs, not a transition-assignment
engine. Real molecular assignments require the upstream evidence in the lesson.
"""
import argparse
import hashlib
from html import escape
import json
import math
from pathlib import Path
import sys

import numpy as np

from orbital_viewer.benchmark import fingerprint, relative_name, validate_plan
from orbital_viewer.data import HC, read_transitions
from orbital_viewer.mcp_models import CubeInfo, Export, Spectrum, TransitionInfo

MODELS = {"inspect_cube": CubeInfo, "inspect_transitions": TransitionInfo,
          "broaden_spectrum": Spectrum, "export_orbital": Export, "export_spectrum": Export}


def read_json(path):
    def invalid_constant(value):
        raise ValueError("Nonfinite JSON number: " + value)
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid_constant)


def checked_file(root, name, expected):
    path = (root / relative_name(name)).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("Evidence file must remain inside the run directory")
    actual = fingerprint(path)
    if any(actual[key] != expected[key] for key in actual):
        raise ValueError("Evidence fingerprint mismatch: " + name)
    return path


def transition_rows(data):
    """Convert verified table rows to photon wavelengths without assigning states."""
    info = TransitionInfo.model_validate(data)
    if info.transition_count != len(info.transitions) or not info.transitions:
        raise ValueError("Transition count mismatch or empty table")
    rows = []
    for index, row in enumerate(info.transitions, 1):
        if row.energy_ev <= 0 or row.oscillator_strength < 0:
            raise ValueError("Excitation energy must be positive and strength nonnegative")
        wavelength = HC / row.energy_ev
        if not math.isclose(wavelength, row.wavelength_nm, rel_tol=1e-10):
            raise ValueError("Wavelength disagrees with hc/E")
        rows.append({"input_row": index, "energy_ev": row.energy_ev,
                     "oscillator_strength": row.oscillator_strength,
                     "derived_wavelength_nm": wavelength,
                     "molecular_state": None, "orbital_assignment": None})
    return rows


def verify_bundle(root):
    """Reject failed, incomplete, relabelled, or internally inconsistent evidence."""
    root = root.resolve(strict=True)
    record = read_json(root / "run.json")
    plan = validate_plan(read_json(root / "plan.json"))
    for item in (record, plan):
        if (item.get("schema_version") != "1" or item.get("benchmark_id") != "EDU-01"
                or item.get("evidence_scope") != "synthetic_fixture"):
            raise ValueError("Only EDU-01 synthetic evidence is supported")
    if fingerprint(root / "plan.json")["sha256"] != record["plan_sha256"]:
        raise ValueError("Plan fingerprint mismatch")
    if record.get("tool_execution_status") != "passed":
        raise ValueError("A successful actual MCP run is required")
    if record["engineering_decision"].get("release_allowed") is not False:
        raise ValueError("Synthetic evidence must retain the release block")
    if any(record["engineering_decision"].get(key, "missing") is not None
           for key in plan["unknown_quantities"]):
        raise ValueError("Missing molecular quantities must stay unknown")

    inputs = record["input_artifacts"]
    if [x["filename"] for x in inputs] != [x["filename"] for x in plan["inputs"]]:
        raise ValueError("Input list differs from plan")
    for actual, declared in zip(inputs, plan["inputs"]):
        if actual["path"] != "inputs/" + declared["filename"]:
            raise ValueError("Input snapshot path differs from plan")
        path = checked_file(root, actual["path"], actual)
        content = path.read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        if not declared.get("source_blob_sha1") or blob != declared["source_blob_sha1"]:
            raise ValueError("Input is not the declared pinned synthetic fixture")

    calls = record["calls"]
    if len(calls) != len(plan["calls"]) or {c["name"] for c in calls} != set(MODELS):
        raise ValueError("Incomplete planned tool coverage")
    outputs = []
    for index, (call, planned) in enumerate(zip(calls, plan["calls"]), 1):
        if (call["sequence"] != index or call["name"] != planned["name"]
                or call["arguments"] != planned["arguments"] or call["status"] != "succeeded"):
            raise ValueError("Call sequence, arguments or status differ from plan")
        response = call["response"]
        data = response.get("structuredContent")
        if response.get("isError") is not False or not isinstance(data, dict):
            raise ValueError("MCP response reports an error or lacks structured content")
        MODELS[call["name"]].model_validate(data)
        if not data["caveats"]:
            raise ValueError("Scientific caveats are required")
        texts = [x["text"] for x in response["content"] if x["type"] == "text"]
        if len(texts) != 1 or json.loads(texts[0]) != data:
            raise ValueError("Text and structured MCP responses disagree")
        if call["name"].startswith("export_"):
            outputs.append((index, data))
    artifacts = record["generated_artifacts"]
    if len(artifacts) != len(outputs):
        raise ValueError("Export count mismatch")
    for artifact, (sequence, data) in zip(artifacts, outputs):
        if (artifact["call_sequence"] != sequence or artifact["path"] != "exports/" + data["filename"]
                or artifact["size_bytes"] != data["size_bytes"]
                or artifact["media_type"] != data["media_type"]
                or artifact.get("evidence_scope") != "synthetic_fixture"):
            raise ValueError("Export metadata differs from its MCP response")
        checked_file(root, artifact["path"], artifact)
    return record, plan


def build_explanation(root, lesson_path):
    root = root.resolve(strict=True)
    record, plan = verify_bundle(root)
    lesson = read_json(lesson_path)
    if (lesson.get("schema_version") != "1" or lesson.get("benchmark_id") != "EDU-01"
            or lesson.get("evidence_scope") != "synthetic_fixture"):
        raise ValueError("Expected the EDU-01 synthetic teaching lesson")
    source_ids = {s["id"] for s in lesson["sources"]}
    for concept in lesson["concepts"]:
        if (concept["classification"] != "External knowledge" or not concept["source_ids"]
                or not set(concept["source_ids"]).issubset(source_ids)):
            raise ValueError("Every scientific concept needs a known source")
    calls = record["calls"]
    observations = []
    for call in calls:
        if call["name"] != "inspect_transitions":
            continue
        data = call["response"]["structuredContent"]
        rows = transition_rows(data)
        # Match observations to the actual archived input, including ORCA parsing.
        original = read_transitions((root / "inputs" / call["arguments"]["filename"]).read_text(),
                                    call["arguments"]["filename"])
        returned = np.array([[r["energy_ev"], r["oscillator_strength"]] for r in rows])
        if original.shape != returned.shape or not np.allclose(original, returned, rtol=1e-12, atol=0):
            raise ValueError("Transition response differs from its input snapshot")
        maximum = max(r["oscillator_strength"] for r in rows)
        observations.append({"classification": "Observed", "filename": call["arguments"]["filename"],
            "evidence_pointer": f"run.json#/calls/{call['sequence'] - 1}/response/structuredContent",
            "rows": rows, "derived": {"classification": "Derived", "wavelength_formula": "hc / excitation_energy",
                "hc_ev_nm": HC, "strongest_input_rows": [r["input_row"] for r in rows
                    if r["oscillator_strength"] == maximum] if maximum > 0 else [],
                "total_oscillator_strength": math.fsum(r["oscillator_strength"] for r in rows)},
            "caveats": data["caveats"]})

    spectrum_call = next(c for c in calls if c["name"] == "broaden_spectrum")
    spectrum = Spectrum.model_validate(spectrum_call["response"]["structuredContent"])
    energy, wavelength, intensity = (np.asarray(v) for v in
        (spectrum.energy_ev, spectrum.wavelength_nm, spectrum.intensity_f_per_ev))
    if (len(energy) < 2 or len(energy) != len(wavelength) or len(energy) != len(intensity)
            or np.any(energy <= 0) or np.any(np.diff(energy) <= 0) or np.any(intensity < 0)
            or not np.allclose(wavelength, HC / energy, rtol=1e-10, atol=0)):
        raise ValueError("Inconsistent spectrum axes, lengths or intensities")
    primary = next(o for o in observations if o["filename"] == spectrum_call["arguments"]["filename"])
    total = primary["derived"]["total_oscillator_strength"]
    area = float(np.trapezoid(intensity, energy))
    if (spectrum.transition_count != len(primary["rows"])
            or not math.isclose(total, spectrum.total_oscillator_strength, rel_tol=1e-10, abs_tol=1e-14)
            or not math.isclose(area, spectrum.integrated_oscillator_strength, rel_tol=1e-10, abs_tol=1e-14)
            or spectrum.fwhm_ev != spectrum_call["arguments"]["fwhm_ev"]):
        raise ValueError("Spectrum summary differs from its samples or source table")

    # Check every CSV row, including both axes, against the actual MCP broadening.
    for artifact in record["generated_artifacts"]:
        if artifact["media_type"] == "text/csv":
            exported = np.loadtxt(root / artifact["path"], delimiter=",", skiprows=1)
            expected = np.column_stack((energy, wavelength, intensity))
            if exported.shape != expected.shape or not np.allclose(exported, expected, rtol=1e-12, atol=0):
                raise ValueError("Exported spectrum differs from the recorded spectrum")

    cube_call = next(c for c in calls if c["name"] == "inspect_cube")
    return {"schema_version": "1", "benchmark_id": "EDU-01", "evidence_scope": "synthetic_fixture",
        "warning": "Synthetic teaching fixtures; no molecule or molecular transition has been assigned.",
        "provenance": {"run": fingerprint(root / "run.json"), "plan": fingerprint(root / "plan.json"),
            "lesson": fingerprint(lesson_path), "report_implementation": fingerprint(Path(__file__)),
            "recorded_source_revision": record["source_revision"], "actual_mcp_calls": len(calls)},
        "observations": observations,
        "cube": {"classification": "Observed", "field_identity": "synthetic_scalar",
            "evidence_pointer": f"run.json#/calls/{cube_call['sequence'] - 1}/response/structuredContent",
            "summary": cube_call["response"]["structuredContent"], "orbital_index": None,
            "occupation": None, "homo_lumo_role": None, "nto_state_and_pair": None},
        "spectrum": {"classification": "Derived", "sample_count": len(energy),
            "recomputed_energy_integral": area, "input_strength_total": total,
            "absolute_area_error": abs(area - total), "relative_area_error": abs(area - total) / total if total else None,
            "integration_coordinate": "energy_ev", "intensity_unit": spectrum.intensity_unit,
            "fwhm_ev": spectrum.fwhm_ev, "linewidth_classification": "Assumed",
            "caveats": spectrum.caveats},
        "assignment": {"status": "blocked_missing_molecular_assignment_evidence", "molecule": None,
            "assigned_transition": None, "nto_weights": None, "assignment_allowed": False,
            "reason": "The archived CUBE and transition tables are unrelated synthetic fixtures. "
                      "Energies and strengths contain no orbital-pair or state provenance."},
        "engineering_decision": {"status": "educational_demo_only", "release_allowed": False,
            "caid_import_performed": False, "quantum_results_generated": False,
            "action": "Keep these outputs as teaching evidence. Obtain a matched calculation bundle "
                      "before assigning a molecular transition or using absorption in a hardware decision.",
            "confidence": "High for checked software arithmetic; molecular assignment is undetermined."},
        "concepts": lesson["concepts"], "missing_data": lesson["missing_data"],
        "manual_handoffs": lesson["manual_handoffs"], "friction": lesson["friction"],
        "sources": lesson["sources"], "display_assumptions": plan["assumptions"],
        "artifacts": [{**a, "tool": calls[a["call_sequence"] - 1]["name"],
            "arguments": calls[a["call_sequence"] - 1]["arguments"]} for a in record["generated_artifacts"]]}


def render_html(report):
    """Keep provenance and the assignment boundary beside every exported view."""
    e = lambda value: escape(str(value), quote=True)
    sections = []
    for observation in report["observations"]:
        rows = "".join(f"<tr><td>{r['input_row']}</td><td>{r['energy_ev']:.6g}</td>"
                       f"<td>{r['derived_wavelength_nm']:.4f}</td><td>{r['oscillator_strength']:.6g}</td>"
                       "<td>Unassigned</td></tr>" for r in observation["rows"])
        strongest = [r for r in observation["rows"]
                     if r["input_row"] in observation["derived"]["strongest_input_rows"]]
        strength_note = ("Largest input oscillator strength: " + "; ".join(
            f"row {r['input_row']} at {r['energy_ev']:.6g} eV "
            f"({r['derived_wavelength_nm']:.4f} nm), f = {r['oscillator_strength']:.6g}"
            for r in strongest) + ". This identifies a synthetic stick, not a molecular mechanism."
            if strongest else "All input oscillator strengths are zero; this table supplies no positive-strength stick.")
        sections.append(f"<h3>{e(observation['filename'])}</h3><p>Observed energies and strengths; "
                        f"wavelengths derived with hc/E. Input row numbers are not molecular state IDs. "
                        f"Evidence: <code>{e(observation['evidence_pointer'])}</code>.</p>"
                        "<div class='table'><table><thead><tr><th>Input row</th><th>Energy (eV)</th>"
                        "<th>Wavelength (nm)</th><th>Strength (f)</th><th>Assignment</th></tr></thead>"
                        f"<tbody>{rows}</tbody></table></div><p>{e(strength_note)}</p>")
    concepts = "".join(f"<article><h3>{e(c['name'])}</h3><p>{e(c['explanation'])}</p>"
                       f"<small>External knowledge · {e(', '.join(c['source_ids']))}</small></article>"
                       for c in report["concepts"])
    exports = []
    for artifact in report["artifacts"]:
        path = e(artifact["path"])
        title = "Synthetic signed scalar field" if artifact["tool"] == "export_orbital" else (
            "Synthetic spectrum · " + artifact["arguments"].get("x_unit", "CSV"))
        view = (f"<iframe title='{e(title)}' src='{path}' loading='lazy' sandbox='allow-scripts'></iframe>"
                if artifact["media_type"] == "text/html" else "")
        exports.append(f"<article><h3>{e(title)}</h3><p>Synthetic fixture. "
                       "Colors on the signed field are not positive/negative charge. "
                       "Spectrum envelopes retain f/eV on both axes.</p>"
                       f"<a href='{path}'>Open original export</a>{view}</article>")
    missing = "".join(f"<li><strong>{e(x['required_for'])}</strong>: {e(x['artifact'])}</li>" for x in report["missing_data"])
    handoffs = "".join(f"<li>{e(x)}</li>" for x in report["manual_handoffs"])
    friction = "".join(f"<li><strong>{e(x['gap'])}</strong>: {e(x['capability'])}</li>" for x in report["friction"])
    sources = "".join(f"<li>{e(x['id'])}: <a href='{e(x['url'])}'>{e(x['title'])}</a> "
                      f"— {e(x['scope'])}</li>" for x in report["sources"])
    spectrum = report["spectrum"]
    return f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EDU-01 · From orbitals to absorption</title>
<style>body{{margin:0;background:#f4f6f8;color:#17242d;font:17px/1.6 system-ui,sans-serif}}
main{{max-width:1100px;margin:auto;padding:32px 24px}}h1{{font-size:clamp(30px,5vw,52px);line-height:1.15}}
h2{{margin-top:48px}}h3{{margin-bottom:8px}}article{{padding:20px;background:white;border:1px solid #d8e1e8;border-radius:10px;margin:18px 0}}
.notice{{padding:20px;border-left:5px solid #b75d13;background:#fff2dc}}.table{{overflow:auto}}table{{width:100%;border-collapse:collapse}}
th,td{{text-align:left;padding:10px;border-bottom:1px solid #cdd6dc}}a{{color:#075985}}code{{overflow-wrap:anywhere}}
iframe{{display:block;width:100%;height:550px;border:0;margin-top:16px}}small{{color:#4d5e6b}}
</style><main><p>ORBITAL STUDIO / EDU-01</p><h1>From orbitals to absorption</h1>
<p class="notice"><strong>Assignment blocked.</strong> {e(report['warning'])}</p>
<p>Absorption connects a difference between electronic-state energies with the strength of the light-induced transition.
The tables locate and weight the synthetic sticks. Orbital pictures alone cannot identify the transition that produced a stick.</p>
<h2>What the recorded tools tell us</h2>{''.join(sections)}
<p>The Gaussian envelope uses an assumed FWHM of {spectrum['fwhm_ev']:g} eV and {spectrum['sample_count']} samples.
Its recomputed energy-space integral is {spectrum['recomputed_energy_integral']:.12g}; the input strengths sum to
{spectrum['input_strength_total']:.12g}. This checks numerical consistency, not a measured molecular spectrum.</p>
<h2>Nine distinctions that matter</h2>{concepts}
<h2>Explore the actual exports</h2>{''.join(exports)}
<h2>What is needed to assign a transition</h2><p>{e(report['assignment']['reason'])}</p><ul>{missing}</ul>
<h2>Manual handoffs</h2><ol>{handoffs}</ol><h2>Reusable capability gaps</h2><ul>{friction}</ul>
<h2>Engineering decision</h2><p>{e(report['engineering_decision']['action'])}</p>
<p>No CAID import or quantum calculation was performed. Molecular assignment and production release remain blocked.</p>
<h2>Evidence and references</h2><p><a href="explanation.json">Structured explanation</a> · <a href="run.json">Raw MCP record</a> ·
<a href="plan.json">Execution plan</a> · <a href="lesson.json">Lesson and source ledger</a></p><ul>{sources}</ul>
</main></html>"""


def write_explanation(root, lesson_path):
    root = root.resolve(strict=True)
    targets = [root / name for name in ("explanation.json", "index.html", "lesson.json")]
    if any(p.exists() or p.is_symlink() for p in targets):
        raise FileExistsError("Explanation outputs already exist; use a fresh benchmark run")
    report = build_explanation(root, lesson_path)
    contents = [(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"),
                render_html(report).encode("utf-8"), lesson_path.read_bytes()]
    for target, content in zip(targets, contents):
        with target.open("xb") as stream:
            stream.write(content)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--lesson", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = write_explanation(args.run_dir, args.lesson)
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
        parser.exit(2, f"Explanation evidence error: {exc}\n")
    print(json.dumps({"assignment": report["assignment"], "engineering_decision": report["engineering_decision"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
