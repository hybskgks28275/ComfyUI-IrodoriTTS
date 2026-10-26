"""A fixed adapter per cached runtime avoids changing ComfyUI-managed storage."""

from contextlib import nullcontext

from .vendor.irodori_tts.inference_runtime import InferenceRuntime


class PersonalizedRuntime(InferenceRuntime):
    def _prepare_lora_for_request(self, adapter_path, **kwargs):
        # Generate attaches a single adapter before creating the VRAM manager.
        # The upstream no-adapter request would otherwise disable that adapter.
        if adapter_path is not None:
            raise ValueError("Use the Generate node's lora_adapter input.")
        return nullcontext()
