import gc
import logging
import tempfile
import threading
from pathlib import Path

import soundfile as sf
import torch

import comfy.model_management as mm
import comfy.utils
import folder_paths
from comfy_api.latest import io

from ..modules.models import DEFAULT_MODEL, MODEL_SPECS, resolve_models
from ..modules.adapters import (
    NONE, list_assets, resolve_asset, asset_fingerprint,
    validate_lora_strength, require_lora_support, apply_lora,
)
from .reference_audio import ReferenceAudios

MODES = ["text", "text_caption", "text_reference", "text_caption_reference", "text_speaker", "text_caption_speaker"]
LOGGER = logging.getLogger(__name__)
_RUNTIME_LOCK = threading.Lock()
_RUNTIME = None
_RUNTIME_KEY = None
_RUNTIME_LORA_KEY = None
_RUNTIME_MANAGER = None


def _clear_runtime_cache():
    global _RUNTIME, _RUNTIME_KEY, _RUNTIME_MANAGER, _RUNTIME_LORA_KEY
    if _RUNTIME_MANAGER is not None:
        _RUNTIME_MANAGER.close()
        _RUNTIME_MANAGER = None
    _RUNTIME = None
    _RUNTIME_KEY = None
    _RUNTIME_LORA_KEY = None
    gc.collect()
    mm.soft_empty_cache()


def release_cached_runtime():
    """Release the shared runtime without racing an active generation."""
    if not _RUNTIME_LOCK.acquire(blocking=False):
        return "busy"
    try:
        if _RUNTIME is None and _RUNTIME_MANAGER is None:
            return "empty"
        _clear_runtime_cache()
        LOGGER.info("[Irodori TTS] Released cached model and codec")
        return "released"
    finally:
        _RUNTIME_LOCK.release()


def prepare_reference(audio: dict, path: Path) -> None:
    waveform = audio["waveform"]
    sample_rate = audio["sample_rate"]
    if not isinstance(waveform, torch.Tensor) or waveform.ndim != 3:
        raise ValueError("reference_audio must be ComfyUI AUDIO with shape [batch, channels, samples].")
    if waveform.shape[0] != 1:
        raise ValueError("Connect reference clips individually; batched audio is not supported.")
    if waveform.shape[1] < 1 or waveform.shape[2] < 1:
        raise ValueError("Reference audio is empty.")
    if not isinstance(sample_rate, int) or sample_rate <= 0:
        raise ValueError("Reference audio sample_rate must be a positive integer.")
    waveform = waveform.detach().to(device="cpu", dtype=torch.float32)
    if not torch.isfinite(waveform).all():
        raise ValueError("Reference audio contains NaN or Inf.")
    # The official runtime handles sample-rate conversion and loudness normalization.
    mono = waveform[0].mean(dim=0).numpy()
    sf.write(str(path), mono, sample_rate, subtype="FLOAT")


class IrodoriTTSGenerate(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="IrodoriTTSGenerate",
            display_name="Irodori TTS Generate",
            category="audio/Irodori TTS",
            description="Generate Japanese speech with compatible Irodori-TTS models from models.json. Reference audio transcripts are not required.",
            inputs=[
                io.Combo.Input("mode", options=MODES, default="text"),
                io.String.Input("text", multiline=True, default="こんにちは。音声合成のテストです。"),
                io.Int.Input("seed", default=0, min=0, max=0xffffffffffffffff,
                             control_after_generate=True),
                io.Int.Input("steps", default=40, min=1, max=200),
                io.Float.Input("cfg_text", default=3.0, min=0.0, max=20.0, step=0.1),
                io.Float.Input("cfg_reference", default=5.0, min=0.0, max=20.0, step=0.1),
                io.Float.Input("cfg_caption", default=3.0, min=0.0, max=20.0, step=0.1),
                io.Float.Input("seconds", default=0.0, min=0.0, max=30.0, step=0.1,
                               tooltip="Use 0 to predict the duration automatically, or specify a fixed duration in seconds."),
                io.Float.Input("duration_scale", default=1.0, min=0.1, max=3.0, step=0.05),
                io.Combo.Input("device", options=["auto", "cuda", "cpu"], default="auto"),
                io.Combo.Input("precision", options=["fp32", "bf16"], default="fp32",
                               tooltip="Precision for non-quantized models. Quantized models always use BF16."),
                io.Combo.Input("codec_device", options=["cpu", "cuda"], default="cpu"),
                io.Boolean.Input("allow_download", default=True,
                                 tooltip="Download missing model files on the first run."),
                io.String.Input("caption", optional=True, multiline=True, default="",
                                tooltip="Describe vocal expression and speaking style for text_caption and text_caption_reference modes."),
                io.MultiType.Input("reference_audio", [io.Audio, ReferenceAudios], optional=True,
                                   tooltip="Connect one or more clips from Load Reference Audios, or one clip from the standard Load Audio node."),
                io.Boolean.Input("unload_after_generate", optional=True, default=False,
                                 tooltip="Keep the model for reuse when disabled. Release it after generation when enabled."),
                # Append new widgets so existing workflows retain positional values.
                io.Combo.Input("model_name", options=list(MODEL_SPECS), optional=True, default=DEFAULT_MODEL,
                               tooltip="Choose a model from models.json. Restart ComfyUI after editing the list. Quantized models use CUDA and BF16. Changing the model reloads it."),
                io.Boolean.Input("dynamic_vram", optional=True, default=True,
                                 tooltip="Offload TTS model weights as needed when ComfyUI Dynamic VRAM is enabled. Otherwise, or on CPU, use standard loading. Codec device is configured separately."),
                io.Combo.Input("speaker_embedding", options=list_assets("speakers"), optional=True, default=NONE,
                               tooltip="Speaker Inversion file under models/irodori_tts/speakers. Used only in text_speaker and text_caption_speaker modes."),
                io.Combo.Input("speaker_uncond_mode", options=["mask", "noise"], optional=True, default="mask",
                               tooltip="Unconditional speaker guidance method for Speaker Inversion."),
                io.Combo.Input("lora_adapter", options=list_assets("loras"), optional=True, default=NONE,
                               tooltip="PEFT adapter folder under models/irodori_tts/loras. Select none to use the base model."),
                io.Float.Input("lora_strength", optional=True, default=1.0, min=0.0, max=2.0, step=0.05,
                               tooltip="LoRA scale multiplier. 1 uses the trained adapter scale. Changing the adapter or strength reloads the model."),
            ],
            outputs=[io.Audio.Output("audio")],
        )

    @classmethod
    def execute(cls, mode, text, seed, steps, cfg_text, cfg_reference, cfg_caption,
                seconds, duration_scale, device, precision, codec_device, allow_download,
                caption="", reference_audio=None, unload_after_generate=False,
                model_name=DEFAULT_MODEL, dynamic_vram=True, speaker_embedding=NONE,
                speaker_uncond_mode="mask", lora_adapter=NONE, lora_strength=1.0) -> io.NodeOutput:
        global _RUNTIME, _RUNTIME_KEY, _RUNTIME_MANAGER, _RUNTIME_LORA_KEY
        if model_name not in MODEL_SPECS:
            raise ValueError(f"Unsupported model_name: {model_name}")
        if mode not in MODES:
            raise ValueError(f"Unsupported mode: {mode}")
        if not text.strip():
            raise ValueError("Enter text to synthesize.")
        use_reference = mode in {"text_reference", "text_caption_reference"}
        use_speaker = mode in {"text_speaker", "text_caption_speaker"}
        use_caption = mode in {"text_caption", "text_caption_reference", "text_caption_speaker"}
        if speaker_uncond_mode not in {"mask", "noise"}:
            raise ValueError("speaker_uncond_mode must be mask or noise.")
        speaker_path = resolve_asset("speakers", speaker_embedding) if use_speaker else None
        if use_speaker and speaker_path is None:
            raise ValueError("This mode requires a speaker_embedding.")
        if use_speaker and reference_audio is not None:
            raise ValueError("Speaker Inversion cannot be combined with reference_audio. Disconnect reference_audio.")
        validate_lora_strength(lora_strength)
        lora_path = resolve_asset("loras", lora_adapter)
        if lora_strength == 0:
            lora_path = None
        if lora_path:
            require_lora_support()
        lora_stamp = asset_fingerprint(lora_path)
        references = []
        if use_reference:
            if isinstance(reference_audio, dict):
                references = [reference_audio]
            elif isinstance(reference_audio, (list, tuple)):
                references = list(reference_audio)
            elif reference_audio is not None:
                raise ValueError("Connect Load Reference Audios or Load Audio to reference_audio.")
        if use_reference and not references:
            raise ValueError("This mode requires reference_audio. Connect a reference audio loader.")
        if use_caption and not caption.strip():
            raise ValueError("This mode requires a caption.")
        if device not in {"auto", "cuda", "cpu"} or codec_device not in {"cuda", "cpu"}:
            raise ValueError("Invalid device / codec_device.")
        device = ("cuda" if torch.cuda.is_available() else "cpu") if device == "auto" else device
        if (device == "cuda" or codec_device == "cuda") and not torch.cuda.is_available():
            raise ValueError("CUDA is unavailable. Set device and codec_device to cpu.")
        if precision not in {"fp32", "bf16"}:
            raise ValueError("precision must be fp32 or bf16.")
        if "/" in model_name:
            from ..modules.quantized_runtime import resolve_quantized_precision
            precision = resolve_quantized_precision(model_name, device, precision)
        if precision == "bf16" and (device != "cuda" or not torch.cuda.is_bf16_supported()):
            raise ValueError("bf16 requires a compatible CUDA GPU. Set precision to fp32.")

        # Lazy import keeps node discovery independent of optional codec dependencies.
        from ..modules.vendor.irodori_tts.inference_runtime import InferenceRuntime, RuntimeKey, SamplingRequest
        use_dynamic = bool(dynamic_vram and device == "cuda" and
                           getattr(getattr(comfy, "memory_management", None), "aimdo_enabled", False))

        mm.throw_exception_if_processing_interrupted()
        progress = comfy.utils.ProgressBar(steps + 3)
        # Share one runtime across node instances and serialize its use/replacement.
        with _RUNTIME_LOCK:
            succeeded = False
            try:
                with tempfile.TemporaryDirectory(prefix="irodori-") as tmp:
                    reference_paths = []
                    for index, audio in enumerate(references):
                        mm.throw_exception_if_processing_interrupted()
                        reference_path = Path(tmp) / f"reference_{index:04d}.wav"
                        prepare_reference(audio, reference_path)
                        reference_paths.append(str(reference_path))
                    checkpoint, codec = resolve_models(Path(folder_paths.models_dir) / "irodori_tts", allow_download, model_name)
                    mm.throw_exception_if_processing_interrupted()
                    key = RuntimeKey(
                        checkpoint=str(checkpoint), model_device=device, model_precision=precision,
                        codec_repo=str(codec), codec_device=codec_device, codec_precision="fp32",
                        comfy_dynamic_vram=use_dynamic)
                    if not use_dynamic:
                        mm.unload_all_models()
                    lora_key = (lora_stamp, lora_strength if lora_path else None)
                    if _RUNTIME is None or _RUNTIME_KEY != key or _RUNTIME_LORA_KEY != lora_key:
                        # Free the previous model before allocating its replacement.
                        _clear_runtime_cache()
                        LOGGER.info("[Irodori TTS] Loading %s (%s / %s)", model_name, device, precision)
                        # ComfyUI wraps execution in inference_mode. torchao's
                        # tensor reconstruction/transfer requires normal tensors;
                        # synthesis enters its own inference_mode afterwards.
                        with torch.inference_mode(False), torch.no_grad():
                            runtime_class = InferenceRuntime
                            if lora_path:
                                from ..modules.personalized_runtime import PersonalizedRuntime
                                runtime_class = PersonalizedRuntime
                            _RUNTIME = runtime_class.from_key(key)
                            if lora_path:
                                apply_lora(_RUNTIME, lora_path, lora_strength)
                            if use_dynamic:
                                from ..modules.dynamic_vram import DynamicModel
                                _RUNTIME_MANAGER = DynamicModel(_RUNTIME.model, device)
                        _RUNTIME_KEY = key
                        _RUNTIME_LORA_KEY = lora_key
                    else:
                        LOGGER.info("[Irodori TTS] Reusing loaded %s (%s / %s)", model_name, device, precision)
                    progress.update_absolute(1)
                    if _RUNTIME_MANAGER is not None:
                        with torch.inference_mode(False), torch.no_grad():
                            _RUNTIME_MANAGER.load()

                    def step_callback(step, total):
                        mm.throw_exception_if_processing_interrupted()
                        progress.update_absolute(step + 1)

                    def log(message):
                        mm.throw_exception_if_processing_interrupted()
                        LOGGER.info("[Irodori TTS] %s", message)

                    result = _RUNTIME.synthesize(SamplingRequest(
                        text=text, caption=caption if use_caption else None,
                        ref_wavs=reference_paths or None,
                        ref_embed=str(speaker_path) if speaker_path else None,
                        speaker_uncond_mode=speaker_uncond_mode,
                        no_ref=not (use_reference or use_speaker), seed=seed, num_steps=steps,
                        cfg_scale_text=cfg_text, cfg_scale_speaker=cfg_reference,
                        cfg_scale_caption=cfg_caption, seconds=seconds or None,
                        duration_scale=duration_scale,
                    ), log_fn=log, step_callback=step_callback)
                    waveform = result.audio.detach().to(device="cpu", dtype=torch.float32).unsqueeze(0).contiguous()
                    if waveform.numel() == 0 or not torch.isfinite(waveform).all():
                        raise RuntimeError("Generated audio is empty or contains non-finite values. Retry with fp32 or a different seed.")
                    progress.update_absolute(steps + 3)
                    succeeded = True
                    return io.NodeOutput({"waveform": waveform, "sample_rate": result.sample_rate})
            finally:
                if unload_after_generate or not succeeded:
                    # Clear the entire runtime, including codec and watermark models.
                    _clear_runtime_cache()

    @classmethod
    def fingerprint_inputs(cls, mode="text", speaker_embedding=NONE, lora_adapter=NONE, **kwargs):
        speaker = resolve_asset("speakers", speaker_embedding) if mode in {"text_speaker", "text_caption_speaker"} else None
        return (asset_fingerprint(speaker), asset_fingerprint(resolve_asset("loras", lora_adapter)))
