"""Run the real node with ComfyUI's Python: --comfy-root PATH --output-dir PATH."""
import argparse
import asyncio
import importlib.util
import json
import logging
from pathlib import Path
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument("--comfy-root", type=Path, required=True)
parser.add_argument("--output-dir", type=Path, required=True)
parser.add_argument("--precision", default="fp32", choices=["fp32", "bf16"])
parser.add_argument("--steps", default=40, type=int)
parser.add_argument("--model-name", default="Irodori-TTS-v4.1-Small")
parser.add_argument("--unload-after-generate", action="store_true")
args = parser.parse_args()
sys.argv = sys.argv[:1]
sys.path.insert(0, str(args.comfy_root))
logging.basicConfig(level=logging.INFO)

import soundfile as sf
import torch
import folder_paths

Path(folder_paths.get_temp_directory()).mkdir(parents=True, exist_ok=True)
package_dir = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("irodori_custom_node", package_dir / "__init__.py",
                                            submodule_search_locations=[str(package_dir)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
extension = asyncio.run(package.comfy_entrypoint())
node = next(node for node in asyncio.run(extension.get_node_list())
            if node.define_schema().node_id == "IrodoriTTSGenerate")
args.output_dir.mkdir(parents=True, exist_ok=True)
results = []
reference = None
for mode in ("text", "text_caption", "text_reference", "text_caption_reference"):
    started = time.perf_counter()
    torch.cuda.reset_peak_memory_stats()
    result = node.execute(
        mode=mode, text="こんにちは。今日はいい天気ですね。", seed=1234, steps=args.steps,
        cfg_text=3.0, cfg_reference=5.0, cfg_caption=3.0, seconds=0.0,
        duration_scale=1.0, device="cuda", precision=args.precision, codec_device="cpu",
        allow_download=False, caption="落ち着いた自然な話し方。穏やかな口調で話す。",
        reference_audio=reference,
        unload_after_generate=args.unload_after_generate,
        model_name=args.model_name,
    )
    audio, = result.result
    assert audio["waveform"].ndim == 3 and audio["waveform"].shape[:2] == (1, 1)
    assert audio["sample_rate"] == 48000
    assert torch.isfinite(audio["waveform"]).all()
    assert audio["waveform"].abs().max() > 0.001
    sf.write(str(args.output_dir / f"{mode}.wav"), audio["waveform"][0].T.numpy(), audio["sample_rate"])
    results.append({"mode": mode, "elapsed_seconds": round(time.perf_counter() - started, 2),
                    "audio_seconds": audio["waveform"].shape[-1] / audio["sample_rate"],
                    "peak_cuda_gib": round(torch.cuda.max_memory_allocated() / 1024**3, 3),
                    "cuda_after_gib": round(torch.cuda.memory_allocated() / 1024**3, 3),
                    "precision_requested": args.precision,
                    "precision": "bf16" if "/" in args.model_name else args.precision, "steps": args.steps,
                    "model_name": args.model_name,
                    "unload_after_generate": args.unload_after_generate})
    if reference is None:
        # Exercise stereo -> mono and a non-48k reference, using synthetic speech only.
        import torchaudio
        reference = {"waveform": torchaudio.functional.resample(audio["waveform"], 48000, 24000).repeat(1, 2, 1),
                     "sample_rate": 24000}
    print(json.dumps(results[-1]), flush=True)
(args.output_dir / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
