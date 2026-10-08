"""Preflight for the official CUDA/BF16 torchao checkpoints."""

import torch

from .vendor.irodori_tts.quantization import _require_torchao_safetensors


def resolve_quantized_precision(model_name: str, device: str, precision: str) -> str:
    _, _, variant = model_name.partition("/")
    if not variant:
        return precision
    if device != "cuda" or not torch.cuda.is_bf16_supported():
        raise ValueError("Quantized models require an NVIDIA CUDA GPU with BF16 support. Select a non-quantized model.")
    capability = torch.cuda.get_device_capability()
    if variant == "int4-weight-only" and capability < (8, 0):
        raise ValueError("INT4 requires an Ampere or newer GPU (compute capability 8.0 or higher).")
    if variant.startswith("float8-") and capability < (8, 9):
        raise ValueError("FP8 requires an Ada or newer GPU (compute capability 8.9 or higher). Select INT8 or INT4.")
    try:
        _require_torchao_safetensors()
    except (ImportError, RuntimeError) as exc:
        raise RuntimeError(
            "Cannot load torchao for quantized models. In the ComfyUI Python environment, run "
            "pip install -r requirements-quantized.txt."
        ) from exc
    # Quantized tensor subclasses must retain their BF16 compute dtype.
    return "bf16"
