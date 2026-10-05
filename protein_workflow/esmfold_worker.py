"""Isolated local ESMFold execution; heavy packages are imported only on request."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import time
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from protein_workflow.sequences import sha256, utc_now
from protein_workflow.structures import illustrative_pdb

MODEL_ID = "facebook/esmfold_v1"
MODEL_REVISION = "75a3841ee059df2bf4d56688166c8fb459ddd97a"
TRANSFORMERS_VERSION = "4.57.6"


def environment(backend: str, device: str) -> dict[str, Any]:
    """Describe the actual worker runtime without loading or downloading weights."""
    result: dict[str, Any] = {"backend": backend, "python": platform.python_version(),
                              "platform": platform.platform(), "device": device}
    if backend == "fixture":
        return {**result, "fixture_version": 1}
    import torch
    import transformers
    if transformers.__version__ != TRANSFORMERS_VERSION:
        raise RuntimeError(f"This adapter requires transformers=={TRANSFORMERS_VERSION}; install the fold extra.")
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable. Install a compatible PyTorch/CUDA runtime or explicitly use --device cpu.")
    return {**result, "torch": torch.__version__, "transformers": transformers.__version__,
            "numpy": importlib.metadata.version("numpy"), "scipy": importlib.metadata.version("scipy"),
            "huggingface_hub": importlib.metadata.version("huggingface-hub"),
            "accelerate": importlib.metadata.version("accelerate"), "cuda": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(0) if device == "cuda" else None}


def predict(request: dict[str, Any], output: Path) -> None:
    """Execute the selected backend and preserve its unrounded confidence values."""
    config = request["configuration"]
    sequence = request["sequence"]
    runtime = environment(config["backend"], config["device"])
    started = time.monotonic()
    if config["backend"] == "fixture":
        pdb = illustrative_pdb(sequence)
        raw_confidence: list[float] | None = None
        model: dict[str, Any] = {"id": "illustrative-backbone", "revision": "1"}
        classification = "illustrative"
    else:
        import torch
        from transformers import EsmForProteinFolding
        from transformers.models.esm.openfold_utils import residue_constants
        torch.manual_seed(config["seed"])
        if config["device"] == "cuda":
            torch.cuda.manual_seed_all(config["seed"])
            torch.backends.cuda.matmul.allow_tf32 = False
            torch.backends.cudnn.allow_tf32 = False
        print("Loading pinned ESMFold v1 weights", flush=True)
        fold = EsmForProteinFolding.from_pretrained(
            MODEL_ID, revision=MODEL_REVISION, local_files_only=request["local_files_only"],
            torch_dtype=torch.float32, low_cpu_mem_usage=True, use_safetensors=False, weights_only=True)
        fold.eval().to(config["device"])
        if config["device"] == "cuda":
            fold.esm.half()  # Keep the folding trunk in float32.
        fold.trunk.set_chunk_size(config["chunk_size"])
        # ESMFold.forward expects AF2 residue order, not the ESM language-model vocabulary.
        tokens = torch.tensor([[residue_constants.restype_order[aa] for aa in sequence]],
                              dtype=torch.long, device=config["device"])
        print(f"Predicting {len(sequence)} residues with {config['num_recycles'] + 1} trunk passes", flush=True)
        with torch.inference_mode():
            result = fold(tokens, num_recycles=config["num_recycles"])
        confidence = result["plddt"]
        if not torch.isfinite(confidence).all() or (confidence < 0).any() or (confidence > 1).any():
            raise RuntimeError("Unexpected confidence scale from pinned backend; expected finite 0..1 values.")
        raw_confidence = confidence[0, :, residue_constants.atom_order["CA"]].float().cpu().tolist()
        # Transformers 4.57.6 categorical_lddt returns 0..1; PDB B-factors here explicitly use 0..100.
        result["plddt"] = confidence * 100.0
        pdb = "REMARK 900 ESMFOLD PREDICTION; B-FACTORS ARE PLDDT 0-100\n" + fold.output_to_pdb(result)[0]
        model = {"id": MODEL_ID, "revision": MODEL_REVISION,
                 "resolved_config_revision": fold.config._commit_hash,
                 "precision": "esm-fp16/trunk-fp32" if config["device"] == "cuda" else "float32"}
        if model["resolved_config_revision"] != MODEL_REVISION:
            raise RuntimeError("Loaded checkpoint config does not match the pinned revision.")
        classification = "computed_prediction"
    output.mkdir(parents=True, exist_ok=False)
    (output / "structure.pdb").write_text(pdb, encoding="ascii")
    (output / "confidence.json").write_text(json.dumps({
        "kind": "predicted_lddt" if raw_confidence is not None else "unavailable_fixture",
        "raw_scale": [0, 1] if raw_confidence is not None else None,
        "raw_ca_values": raw_confidence, "pdb_scale": [0, 100] if raw_confidence is not None else None,
        "pdb_conversion": "raw * 100, rounded to two decimals" if raw_confidence is not None else None,
    }, indent=2) + "\n", encoding="utf-8")
    (output / "backend.json").write_text(json.dumps({
        "schema_version": 1, "classification": classification, "model": model, "environment": runtime,
        "sequence_sha256": sha256(sequence.encode("ascii")), "configuration": config,
        "completed_at": utc_now(), "runtime_seconds": time.monotonic() - started,
        "sequence_sent_to_external_service": False,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Completed {classification}", flush=True)


def main(argv: list[str] | None = None) -> int:
    """Run a lightweight environment probe or one isolated inference request."""
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--backend", choices=["esmfold", "fixture"], default="esmfold")
    parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    parser.add_argument("--request", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.probe:
        print(json.dumps(environment(args.backend, args.device)))
    else:
        if args.request is None or args.output is None:
            parser.error("--request and --output are required for prediction")
        predict(json.loads(args.request.read_text(encoding="utf-8")), args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
