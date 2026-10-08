"""Native Dynamic VRAM: CPU staging, quantized storage, eviction and regeneration.

Run separately from unittest: --comfy-root PATH --model-name NAME --output-dir PATH
"""
import argparse
import gc
import importlib.util
import json
from pathlib import Path
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument("--comfy-root", required=True)
parser.add_argument("--model-name", required=True)
parser.add_argument("--precision", default="bf16")
parser.add_argument("--steps", type=int, default=4)
parser.add_argument("--full-unload", action="store_true",
                    help="Evict through ComfyUI's model registry instead of partial paging")
parser.add_argument("--output-dir", type=Path, required=True)
args = parser.parse_args()
sys.argv = [sys.argv[0], "--enable-dynamic-vram", "--disable-all-custom-nodes"]
sys.path.insert(0, args.comfy_root)
# Use the same allocator and initialization order as ComfyUI's entry point.
import comfy.options
comfy.options.enable_args_parsing()
import cuda_malloc
import main
import torch
import comfy.memory_management
import comfy.model_management as mm
assert comfy.memory_management.aimdo_enabled

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("irodori_dynamic_smoke", root / "__init__.py",
                                            submodule_search_locations=[str(root)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
from irodori_dynamic_smoke.src.nodes import generate as nodes
from irodori_dynamic_smoke.src.modules.dynamic_vram import DynamicModel

initial_loaded = set(id(item) for item in mm.current_loaded_models)
inputs = dict(mode="text", text="こんにちは。", seed=1234, steps=args.steps,
              cfg_text=3., cfg_reference=5., cfg_caption=3., seconds=2., duration_scale=1.,
              device="cuda", precision=args.precision, codec_device="cpu", allow_download=False,
              model_name=args.model_name)
staging = {}
original_init = DynamicModel.__init__

def checked_init(self, model, device):
    assert not staging, "The runtime was reconstructed instead of reused"
    assert all(p.device.type == "cpu" for p in model.parameters()), "Weights were sent to GPU before staging"
    staging["cpu_staging"] = True
    original_init(self, model, device)

DynamicModel.__init__ = checked_init
started = time.monotonic()
with torch.inference_mode():
    first = nodes.IrodoriTTSGenerate.execute(**inputs).result[0]
manager = nodes._RUNTIME_MANAGER
assert manager is not None and manager.patcher.is_dynamic()
assert any(item.model is manager.patcher for item in mm.current_loaded_models)
before = manager.patcher.loaded_size()
assert before > 0
if args.full_unload:
    mm.unload_all_models()
    freed = before - manager.patcher.loaded_size()
else:
    freed = manager.patcher.partially_unload(torch.device("cpu"), 1e32)
after = manager.patcher.loaded_size()
assert freed > 0 and after < before, (before, after, freed)
with torch.inference_mode():
    second = nodes.IrodoriTTSGenerate.execute(**inputs, unload_after_generate=True).result[0]
assert nodes._RUNTIME is None and nodes._RUNTIME_MANAGER is None
assert all(id(item) in initial_loaded for item in mm.current_loaded_models)
for audio in (first, second):
    assert audio["sample_rate"] == 48000 and torch.isfinite(audio["waveform"]).all()
    assert audio["waveform"].abs().max() > .001
torch.testing.assert_close(first["waveform"], second["waveform"], rtol=1e-3, atol=1e-4)
result = dict(model=args.model_name, **staging, adapted=manager.counts,
              eviction="full" if args.full_unload else "partial",
              loaded_before_eviction=before, freed=freed, loaded_after_eviction=after,
              regenerated_after_eviction=True, elapsed_seconds=round(time.monotonic()-started, 2))
args.output_dir.mkdir(parents=True, exist_ok=True)
(args.output_dir / "results.json").write_text(json.dumps(result, indent=2), encoding="utf8")
print(json.dumps(result), flush=True)
del manager
gc.collect()
