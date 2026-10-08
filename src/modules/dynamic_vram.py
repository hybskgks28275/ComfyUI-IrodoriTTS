"""Native ComfyUI Dynamic VRAM integration, including packed torchao weights."""

from contextlib import ExitStack
import logging

import torch
from torch import nn
import torch.nn.functional as F

import comfy.model_management as mm
import comfy.model_patcher
import comfy.ops as ops

LOGGER = logging.getLogger(__name__)


class PackedTensor(nn.Module, ops.CastWeightBiasOp):
    """A plain packed tensor that ComfyUI can page without dequantizing it."""

    comfy_cast_weights = True

    def __init__(self, tensor):
        super().__init__()
        self.weight = nn.Parameter(tensor.detach().contiguous(), requires_grad=False)
        self.register_parameter("bias", None)

    def acquire(self, stack, device):
        weight, _ = stack.enter_context(ops.CastBiasWeightContext(
            self, device=device, dtype=self.weight.dtype, offloadable=True))
        return weight


class QuantizedLinear(nn.Module):
    """Page the storage pieces, reconstruct the original torchao tensor, run Linear."""

    def __init__(self, linear):
        super().__init__()
        weight = linear.weight
        names, self.metadata = weight.__tensor_flatten__()
        self.tensor_type = type(weight)
        self.outer_size = weight.size()
        self.outer_stride = weight.stride()
        self.in_features = linear.in_features
        self.out_features = linear.out_features
        self.pieces = nn.ModuleDict()
        for name in names:
            tensor = getattr(weight, name)
            if type(tensor) not in (torch.Tensor, nn.Parameter):
                raise TypeError(f"Unsupported nested quantized storage: {type(tensor)}")
            self.pieces[name] = PackedTensor(tensor)
        self.bias_piece = PackedTensor(linear.bias) if linear.bias is not None else None

    @property
    def weight(self):
        # Metadata queries in upstream models do not need CUDA materialization.
        return self.tensor_type.__tensor_unflatten__(
            {name: piece.weight for name, piece in self.pieces.items()},
            self.metadata, self.outer_size, self.outer_stride)

    def forward(self, input):
        with ExitStack() as stack:
            tensors = {name: piece.acquire(stack, input.device) for name, piece in self.pieces.items()}
            weight = self.tensor_type.__tensor_unflatten__(
                tensors, self.metadata, self.outer_size, self.outer_stride)
            bias = self.bias_piece.acquire(stack, input.device) if self.bias_piece is not None else None
            return F.linear(input, weight, bias)


class IrodoriRMSNorm(nn.Module, ops.CastWeightBiasOp):
    """Irodori's last-axis normalization, including multi-axis affine weights."""

    comfy_cast_weights = True

    def __init__(self, original):
        super().__init__()
        self.weight = original.weight
        self.eps = original.eps
        self.register_parameter("bias", None)

    def forward(self, input):
        with ops.CastBiasWeightContext(self, device=input.device,
                                       dtype=self.weight.dtype, offloadable=True) as (weight, _):
            x = input.float()
            x = x * torch.rsqrt((x * x).mean(dim=-1, keepdim=True) + self.eps)
            return (x * weight).to(input.dtype)


class T5GemmaRMSNorm(IrodoriRMSNorm):
    def forward(self, input):
        with ops.CastBiasWeightContext(self, device=input.device,
                                       dtype=self.weight.dtype, offloadable=True) as (weight, _):
            x = input.float()
            x = x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + self.eps)
            return (x * (1.0 + weight.float())).type_as(input)


def adapt_model(model):
    """Adapt supported operations while preserving each custom norm's math."""
    replacements = {
        nn.Linear: ops.manual_cast.Linear,
        nn.Embedding: ops.manual_cast.Embedding,
        nn.LayerNorm: ops.manual_cast.LayerNorm,
        nn.RMSNorm: ops.manual_cast.RMSNorm,
    }
    counts = {"ordinary": 0, "quantized": 0}
    visited = {}

    def convert(module):
        if module in visited:
            return visited[module]
        original = module
        if type(module) is nn.Linear and type(module.weight).__module__.startswith("torchao."):
            module = QuantizedLinear(module)
            counts["quantized"] += 1
        elif type(module).__name__ == "RMSNorm" and type(module).__module__.endswith(".irodori_tts.model"):
            module = IrodoriRMSNorm(module)
            counts["ordinary"] += 1
        elif type(module).__name__ == "T5Gemma2RMSNorm" and type(module).__module__ == "transformers.models.t5gemma2.modeling_t5gemma2":
            module = T5GemmaRMSNorm(module)
            counts["ordinary"] += 1
        elif type(module) in replacements:
            module.__class__ = replacements[type(module)]
            if not hasattr(module, "bias"):
                module.register_parameter("bias", None)
            counts["ordinary"] += 1
        # Retain originals while traversing: replaced modules' ids can be reused.
        visited[original] = module
        for name, child in list(module._modules.items()):
            if child is not None:
                module._modules[name] = convert(child)
        return module

    convert(model)
    return counts


class DynamicModel:
    def __init__(self, model, device):
        self.counts = adapt_model(model)
        device = torch.device(device)
        if device.index is None:
            device = torch.device("cuda", torch.cuda.current_device())
        model._execution_device = device
        # Upstream exposes a read-only .device property. Keep ComfyUI's mutable
        # bookkeeping on a container while the runtime uses the original model.
        container = nn.Module()
        container.add_module("tts", model)
        self.patcher = comfy.model_patcher.CoreModelPatcher(
            container, load_device=device, offload_device=torch.device("cpu"))
        if not self.patcher.is_dynamic():
            raise RuntimeError("ComfyUI Dynamic VRAM is not enabled.")
        LOGGER.info("[Irodori TTS] Dynamic VRAM: %s ordinary / %s quantized layers",
                    self.counts["ordinary"], self.counts["quantized"])

    def load(self):
        # ComfyUI chooses which managed weights to retain or evict.
        mm.load_models_gpu([self.patcher])

    def close(self):
        # Unload this model only; leave other workflows' managed models alone.
        found = False
        for loaded in list(mm.current_loaded_models):
            if loaded.model is self.patcher:
                loaded.model_unload()
                mm.current_loaded_models.remove(loaded)
                found = True
        if not found:
            self.patcher.detach()
