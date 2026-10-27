"""Structural GPU smoke with synthetic adapters, not a learned-voice quality test.

Uses already-downloaded Small weights; fixtures/output stay under --output-dir.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--comfy-root", required=True)
parser.add_argument("--output-dir", type=Path, required=True)
parser.add_argument("--quantized", action="store_true")
args = parser.parse_args()
sys.path.insert(0, args.comfy_root)
sys.argv = [sys.argv[0], "--enable-dynamic-vram", "--disable-all-custom-nodes"]
import comfy.options
comfy.options.enable_args_parsing()
import cuda_malloc
import main
import torch
import comfy.model_management as mm
import folder_paths
import soundfile as sf
from peft import LoraConfig
from safetensors import safe_open
from safetensors.torch import save_file

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("irodori_personal_smoke", root / "__init__.py", submodule_search_locations=[str(root)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
from irodori_personal_smoke.src.nodes import generate
from irodori_personal_smoke.src.modules import adapters

args.output_dir.mkdir(parents=True, exist_ok=True)
assets = args.output_dir / "fixtures"
adapters.asset_directory = lambda kind: assets / kind
base = Path(folder_paths.models_dir) / "irodori_tts/Irodori-TTS-v4.1-Small/model.safetensors"
with safe_open(base, framework="pt") as f:
    config = json.loads(f.metadata()["config_json"])
    shape = f.get_slice("out_proj.weight").get_shape()
speaker = assets / "speakers/test.speaker.safetensors"
speaker.parent.mkdir(parents=True, exist_ok=True)
torch.manual_seed(42)
save_file({"speaker_embedding": torch.randn(16, config["speaker_dim"]) * .02}, str(speaker))
lora = assets / "loras/test"
lora.mkdir(parents=True, exist_ok=True)
LoraConfig(r=2, lora_alpha=2, target_modules="^out_proj$").save_pretrained(lora)
save_file({"base_model.model.out_proj.lora_A.weight": torch.randn(2, shape[1]) * .001,
           "base_model.model.out_proj.lora_B.weight": torch.randn(shape[0], 2) * .001},
          str(lora / "adapter_model.safetensors"))
model = "Irodori-TTS-v4.1-Small"
if args.quantized:
    model = "Irodori-TTS-v4.1-Small-Quantized/int8-weight-only"
inputs = dict(mode="text_speaker", text="こんにちは。", seed=42, steps=4, cfg_text=3.,
              cfg_reference=5., cfg_caption=3., seconds=1., duration_scale=1., device="cuda",
              precision="bf16", codec_device="cpu", allow_download=False, model_name=model,
              speaker_embedding="test.speaker.safetensors")
results = []


def run(name, **changes):
    with torch.inference_mode():
        audio = generate.IrodoriTTSGenerate.execute(**(inputs | changes)).result[0]
    assert audio["sample_rate"] == 48000
    assert torch.isfinite(audio["waveform"]).all()
    assert audio["waveform"].abs().max() > .001
    sf.write(str(args.output_dir / f"{name}.wav"), audio["waveform"][0].T.numpy(), 48000)
    results.append(name)
    print("PASS", name, flush=True)
    return audio


try:
    run("speaker_mask")
    original = generate._RUNTIME
    run("speaker_caption_noise", mode="text_caption_speaker", caption="穏やかな声。", speaker_uncond_mode="noise")
    assert generate._RUNTIME is original
    del original
    first = run("speaker_lora", lora_adapter="test")
    original = generate._RUNTIME
    manager = generate._RUNTIME_MANAGER
    assert manager is not None
    assert manager.patcher.partially_unload(torch.device("cpu"), 1e32) > 0
    second = run("speaker_lora_reused", lora_adapter="test")
    assert generate._RUNTIME is original
    torch.testing.assert_close(first["waveform"], second["waveform"], rtol=1e-3, atol=1e-4)
    del original, manager
    run("lora_strength", lora_adapter="test", lora_strength=.5)
    run("lora_without_speaker", mode="text", lora_adapter="test", lora_strength=.5)
    run("reference_lora", mode="text_reference", lora_adapter="test", lora_strength=.5, reference_audio=first)
    run("caption_reference_lora", mode="text_caption_reference", caption="穏やかな声。",
        lora_adapter="test", lora_strength=.5, reference_audio=first)
    run("base_without_speaker", mode="text", unload_after_generate=True)
    assert generate._RUNTIME is None and generate._RUNTIME_MANAGER is None
    (args.output_dir / "results.json").write_text(json.dumps({"model": model, "passed": results}, indent=2))
finally:
    generate.release_cached_runtime()
