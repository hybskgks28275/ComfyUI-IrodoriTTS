"""Local inference assets and cache identities for speaker embeddings and LoRA."""

import math
from pathlib import Path

import folder_paths

NONE = "none"


def asset_directory(kind):
    return Path(getattr(folder_paths, "models_dir", "models")) / "irodori_tts" / kind


def list_assets(kind):
    root = asset_directory(kind)
    if not root.is_dir():
        return [NONE]
    pattern = "*.speaker.safetensors" if kind == "speakers" else "adapter_config.json"
    paths = (p if kind == "speakers" else p.parent for p in root.rglob(pattern))
    names = []
    for path in paths:
        if kind == "loras" and not (path / "adapter_model.safetensors").is_file():
            continue
        if path.resolve().is_relative_to(root.resolve()):
            names.append(path.relative_to(root).as_posix())
    return [NONE] + sorted(names)


def resolve_asset(kind, name):
    if name in (None, "", NONE):
        return None
    root = asset_directory(kind).resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or name not in list_assets(kind):
        raise ValueError(f"Invalid or missing {kind} asset: {name}")
    return path


def asset_fingerprint(path):
    if path is None:
        return None
    files = [path] if path.is_file() else [path / "adapter_config.json", path / "adapter_model.safetensors"]
    return tuple((str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in files)


def validate_lora_strength(strength):
    if not math.isfinite(strength) or not 0 <= strength <= 2:
        raise ValueError("lora_strength must be a finite number between 0 and 2.")


def require_lora_support():
    try:
        from .vendor.irodori_tts.lora import _require_peft
        _require_peft()
    except (ImportError, RuntimeError) as exc:
        raise RuntimeError("LoRA requires PEFT. Install requirements-lora.txt in ComfyUI's Python environment.") from exc


def apply_lora(runtime, path, strength):
    """Attach PEFT before ComfyUI transforms modules and records their storage."""
    from .vendor.irodori_tts.lora import load_lora_adapter
    from peft.tuners.tuners_utils import BaseTunerLayer
    from peft import LoraConfig
    from peft.tuners.lora.layer import Linear
    import torch

    device = "cpu" if runtime.key.comfy_dynamic_vram else str(runtime.model_device)
    if runtime.key.comfy_dynamic_vram:
        runtime.model._execution_device = runtime.model_device
    config = LoraConfig.from_pretrained(str(path), local_files_only=True)
    if any(type(getattr(m, "weight", None)).__module__.startswith("torchao.")
           for m in runtime.model.modules()):
        # PEFT's torchao dispatcher expects Transformers' tensor-subclass hook.
        # These are standalone Irodori Linear layers: retain their packed base
        # weights and add the adapter via the ordinary (unmerged) LoRA forward.
        config._register_custom_module({torch.nn.Linear: Linear})
    runtime.model = load_lora_adapter(runtime.model, path, is_trainable=False, torch_device=device, config=config)
    for module in runtime.model.modules():
        if isinstance(module, BaseTunerLayer):
            for adapter in module.active_adapters:
                module.set_scale(adapter, strength)
    runtime.model.eval()
    runtime.model.requires_grad_(False)
