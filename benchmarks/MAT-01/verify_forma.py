"""Validate MAT-01 with an authorized, unmodified checkout of pinned Forma.

This optional offline check imports the real Pydantic model and its validators.
It never connects to a Forma service or treats schema success as qualification.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import sys
from typing import Any

BASE = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    """Hash exact bytes rather than a reconstructed source representation."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def retained(expected: Any, actual: Any) -> None:
    """Reject dropped/changed proposal fields, including nulls and release flags."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or not expected.keys() <= actual.keys():
            raise ValueError("Forma serialization dropped proposal fields")
        for key, value in expected.items():
            retained(value, actual[key])
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            raise ValueError("Forma serialization changed a proposal list")
        for before, after in zip(expected, actual):
            retained(before, after)
    elif expected != actual or type(expected) is not type(actual):
        # Pydantic may serialize integer dimensions/prices as float values.
        if (type(expected) not in (int, float) or type(actual) not in (int, float)
                or expected != actual):
            raise ValueError("Forma serialization changed a proposal value")


def verify(source: Path, output: Path) -> dict[str, Any]:
    """Check pinned sources, real validation, retained evidence and round trip."""
    source = source.resolve(strict=True)
    provenance = json.loads((BASE / "schema-provenance.json").read_text())
    for item in provenance["source_files"]:
        if digest(source / item["path"]) != item["sha256"]:
            raise ValueError("Forma source differs from pinned schema: " + item["path"])
    sys.path.insert(0, str(source))
    models = importlib.import_module("forma_core.workspaces.projects.models")
    if Path(models.__file__).resolve() != source / "forma_core/workspaces/projects/models.py":
        raise ValueError("Unexpected Forma model import")
    import pydantic

    model = models.HardwareIntermediateRepresentation
    proposal = json.loads((BASE / "material-entry.proposed.json").read_text())["proposed_mapping"]
    validated = model.model_validate(deepcopy(proposal))
    serialized = validated.model_dump(mode="json", exclude_unset=True)
    retained(proposal, serialized)
    round_trip = model.model_validate_json(json.dumps(serialized)).model_dump(mode="json", exclude_unset=True)
    if round_trip != serialized:
        raise ValueError("Pinned Forma serialization is not stable")
    if serialized["is_valid"] is not False or not serialized["validation"]["critical"]:
        raise ValueError("Proposal lost its design-qualification block")
    if serialized["assembly_metadata"]["production_release"] is not False:
        raise ValueError("Proposal lost its release block")
    rejected = []
    for case in ("bom_quantity", "bom_price", "unresolved_instance"):
        bad = deepcopy(proposal)
        if case == "bom_quantity":
            bad["bom"][0]["quantity"] = 2
        elif case == "bom_price":
            bad["bom"][0]["extended_price"] = 1
        else:
            bad["bom"][0]["instance_refs"] = ["W2"]
        try:
            model.model_validate(bad)
        except pydantic.ValidationError:
            rejected.append(case)
        else:
            raise ValueError("Actual Forma model accepted invalid case: " + case)
    output.mkdir(parents=True, exist_ok=False)
    schema = model.model_json_schema(mode="validation")
    for name, value in (("hardware-ir.schema.json", schema), ("hardware-ir.proposed.json", serialized)):
        (output / name).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    modules = []
    for name, module in sorted(sys.modules.items()):
        if not name.startswith("forma_core") or not getattr(module, "__file__", None):
            continue
        path = Path(module.__file__).resolve()
        if not path.is_relative_to(source):
            raise ValueError("Mixed Forma source trees")
        modules.append({"path": path.relative_to(source).as_posix(), "sha256": digest(path)})
    result = {
        "source_revision": provenance["source_revision"], "pydantic_version": pydantic.__version__,
        "unmodified_model_validation": "passed", "evidence_and_nulls_preserved": True,
        "local_serialization_round_trip": "passed", "negative_cases_rejected": rejected,
        "loaded_source_modules": modules, "schema_sha256": digest(output / "hardware-ir.schema.json"),
        "proposal_input_sha256": digest(BASE / "material-entry.proposed.json"),
        "serialized_proposal_sha256": digest(output / "hardware-ir.proposed.json"),
        "caid_import_performed": False, "production_release": False,
    }
    (output / "schema-check.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    """Run the optional model check without a hosted service or credentials."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New evidence directory")
    args = parser.parse_args()
    result = verify(args.source, args.output)
    print(json.dumps({key: result[key] for key in ("source_revision", "unmodified_model_validation", "local_serialization_round_trip", "caid_import_performed")}))


if __name__ == "__main__":
    main()
