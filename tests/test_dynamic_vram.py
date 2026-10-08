import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

import torch
from torch import nn
import comfy.ops as ops

spec = importlib.util.spec_from_file_location("irodori_dynamic_adapter_tests", Path(__file__).resolve().parents[1] / "src" / "modules" / "dynamic_vram.py")
dynamic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dynamic)


class DynamicAdapterTests(unittest.TestCase):
    def test_standard_layers_preserve_output_and_shared_modules(self):
        embedding = nn.Embedding(32, 16)
        projection = nn.Linear(16, 16)
        model = nn.Sequential(embedding, nn.LayerNorm(16), projection, nn.RMSNorm(16), projection).eval()
        tokens = torch.tensor([[1, 2, 3]])
        with torch.no_grad():
            expected = model(tokens)
        counts = dynamic.adapt_model(model)
        self.assertEqual(counts, {"ordinary": 4, "quantized": 0})
        self.assertIs(model[2], model[4])
        self.assertIsInstance(model[0], ops.manual_cast.Embedding)
        self.assertIsNone(model[0].bias)
        with torch.no_grad():
            torch.testing.assert_close(model(tokens), expected)

    def test_custom_norm_math_is_not_replaced(self):
        class ShiftedNorm(nn.LayerNorm):
            def forward(self, x):
                return super().forward(x) + 1
        model = nn.Sequential(ShiftedNorm(8))
        dynamic.adapt_model(model)
        self.assertIs(type(model[0]), ShiftedNorm)
        torch.testing.assert_close(model(torch.ones(1, 8)), torch.ones(1, 8))

    def test_supported_custom_norms_preserve_float_math(self):
        from transformers.models.t5gemma2.modeling_t5gemma2 import T5Gemma2RMSNorm
        root = Path(__file__).resolve().parents[1] / "src" / "modules"
        package_spec = importlib.util.spec_from_file_location(
            "irodori_norm_tests", root / "__init__.py", submodule_search_locations=[str(root)])
        package = importlib.util.module_from_spec(package_spec)
        sys.modules[package_spec.name] = package
        # Only load the vendor module; the package entry point is unnecessary.
        from irodori_norm_tests.vendor.irodori_tts.model import RMSNorm
        for original in (RMSNorm((2, 8)), T5Gemma2RMSNorm(8)):
            for dtype in (torch.float32, torch.bfloat16):
                original = original.to(dtype=dtype)
                original.weight.data.uniform_(-.5, .5)
                inputs = torch.randn(3, 2, 8).to(dtype)
                with torch.no_grad():
                    expected = original(inputs)
                model = nn.Sequential(original)
                counts = dynamic.adapt_model(model)
                self.assertEqual(counts["ordinary"], 1)
                self.assertIsInstance(model[0], dynamic.IrodoriRMSNorm)
                with torch.no_grad():
                    torch.testing.assert_close(model(inputs), expected, rtol=0, atol=0)

    @unittest.skipUnless(importlib.util.find_spec("torchao"), "torchao required")
    def test_packed_int8_keeps_integer_storage_and_forward_result(self):
        from torchao.quantization import quantize_, Int8WeightOnlyConfig
        model = nn.Sequential(nn.Linear(128, 64, bias=True)).to(dtype=torch.bfloat16).eval()
        quantize_(model, Int8WeightOnlyConfig(version=2))
        weight = model[0].weight
        bytes_before = weight.qdata.nbytes + weight.scale.nbytes + model[0].bias.nbytes
        inputs = torch.randn(2, 128, dtype=torch.bfloat16)
        with torch.inference_mode():
            expected = model(inputs)
        counts = dynamic.adapt_model(model)
        self.assertEqual(counts["quantized"], 1)
        self.assertEqual(sum(p.nbytes for p in model.parameters()), bytes_before)
        self.assertEqual(model[0].pieces["qdata"].weight.dtype, torch.int8)
        self.assertEqual(model[0].weight.dtype, torch.bfloat16)
        with torch.inference_mode():
            torch.testing.assert_close(model(inputs), expected)

    @unittest.skipUnless(importlib.util.find_spec("torchao"), "torchao required")
    def test_many_replaced_layers_keep_distinct_modules(self):
        from torchao.quantization import quantize_, Int8WeightOnlyConfig
        from transformers.models.t5gemma2.modeling_t5gemma2 import T5Gemma2RMSNorm
        model = nn.Sequential(*[
            nn.Sequential(nn.Linear(128, 128), T5Gemma2RMSNorm(128)) for _ in range(24)
        ]).to(dtype=torch.bfloat16).eval()
        quantize_(model, Int8WeightOnlyConfig(version=2))
        inputs = torch.randn(2, 128, dtype=torch.bfloat16)
        with torch.inference_mode():
            expected = model(inputs)
        counts = dynamic.adapt_model(model)
        self.assertEqual(counts, {"ordinary": 24, "quantized": 24})
        for block in model:
            self.assertIsInstance(block[0].pieces, nn.ModuleDict)
            self.assertIsInstance(block[1], dynamic.T5GemmaRMSNorm)
        with torch.inference_mode():
            torch.testing.assert_close(model(inputs), expected)

    def test_close_removes_only_its_own_registered_model(self):
        manager = dynamic.DynamicModel.__new__(dynamic.DynamicModel)
        manager.patcher = MagicMock()
        owned = MagicMock(model=manager.patcher)
        other = MagicMock()
        loaded = [other, owned]
        with patch.object(dynamic.mm, "current_loaded_models", loaded):
            manager.close()
        self.assertEqual(loaded, [other])
        owned.model_unload.assert_called_once()
        other.model_unload.assert_not_called()


if __name__ == "__main__":
    unittest.main()
