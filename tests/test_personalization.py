"""Exercise real PEFT storage, scaling, and ComfyUI casting without a full TTS model."""
import importlib
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

import torch

from test_contracts import PACKAGE, folders, nodes

adapters = importlib.import_module(f"{PACKAGE}.modules.adapters")


class AssetTests(unittest.TestCase):
    def test_listing_resolution_and_file_fingerprints(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(folders, "models_dir", tmp, create=True), \
             patch.object(adapters, "folder_paths", folders):
            self.assertEqual(adapters.list_assets("speakers"), ["none"])
            speaker = Path(tmp) / "irodori_tts/speakers/nested/voice.speaker.safetensors"
            speaker.parent.mkdir(parents=True)
            speaker.touch()
            self.assertEqual(adapters.list_assets("speakers"), ["none", "nested/voice.speaker.safetensors"])
            self.assertEqual(adapters.resolve_asset("speakers", "nested/voice.speaker.safetensors"), speaker)
            before = nodes.IrodoriTTSGenerate.fingerprint_inputs(mode="text_speaker", speaker_embedding="nested/voice.speaker.safetensors")
            speaker.write_bytes(b"updated")
            self.assertNotEqual(before, nodes.IrodoriTTSGenerate.fingerprint_inputs(mode="text_speaker", speaker_embedding="nested/voice.speaker.safetensors"))
            for name in ("../outside", str(Path(tmp) / "outside"), "missing"):
                with self.assertRaises(ValueError):
                    adapters.resolve_asset("speakers", name)
            lora = Path(tmp) / "irodori_tts/loras/my_adapter"
            lora.mkdir(parents=True)
            (lora / "adapter_config.json").write_text('{}')
            self.assertEqual(adapters.list_assets("loras"), ["none"])
            (lora / "adapter_model.safetensors").touch()
            self.assertEqual(adapters.list_assets("loras"), ["none", "my_adapter"])

    def test_invalid_strength(self):
        for value in (-1, 3, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                adapters.validate_lora_strength(value)


class TinyModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.proj = torch.nn.Linear(32, 32, bias=False)

    def forward(self, x):
        return self.proj(x)


class PeftTests(unittest.TestCase):
    def test_scale_and_dynamic_conversion_preserve_unmerged_quantized_storage(self):
        try:
            from peft import LoraConfig, get_peft_model
        except ImportError:
            self.skipTest("Install requirements-lora.txt for PEFT integration tests")
        from test_dynamic_vram import dynamic
        with tempfile.TemporaryDirectory() as tmp:
            trained = get_peft_model(TinyModel(), LoraConfig(r=2, lora_alpha=4, target_modules=["proj"]))
            torch.nn.init.constant_(trained.base_model.model.proj.lora_A["default"].weight, 0.1)
            torch.nn.init.constant_(trained.base_model.model.proj.lora_B["default"].weight, 0.1)
            trained.save_pretrained(tmp)
            for quantized in (False, True):
                base = TinyModel().to(dtype=torch.bfloat16)
                if quantized:
                    try:
                        from torchao.quantization import quantize_, Int8WeightOnlyConfig
                    except ImportError:
                        continue
                    quantize_(base, Int8WeightOnlyConfig(version=2))
                x = torch.ones(1, 32, dtype=torch.bfloat16)
                with torch.no_grad():
                    original = base(x)
                runtime = types.SimpleNamespace(model=base, model_device=torch.device("cpu"),
                                                key=types.SimpleNamespace(comfy_dynamic_vram=True))
                adapters.apply_lora(runtime, tmp, 0.5)
                with torch.no_grad():
                    adapted = runtime.model(x)
                self.assertGreater((adapted - original).abs().max().item(), 0.01)
                layer = runtime.model.base_model.model.proj
                self.assertEqual(layer.scaling["default"], 1.0)  # alpha/r * strength
                self.assertFalse(layer.merged)
                counts = dynamic.adapt_model(runtime.model)
                if quantized:
                    self.assertEqual(counts["quantized"], 1)
                with torch.no_grad():
                    torch.testing.assert_close(runtime.model(x), adapted)
                    layer.set_scale("default", 0)
                    torch.testing.assert_close(runtime.model(x), original)

    def test_preloaded_adapter_is_not_disabled_by_sampling(self):
        module = importlib.import_module(f"{PACKAGE}.modules.personalized_runtime")
        runtime = object.__new__(module.PersonalizedRuntime)
        with runtime._prepare_lora_for_request(None):
            pass
        with self.assertRaises(ValueError):
            runtime._prepare_lora_for_request("unexpected")
