import asyncio
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
import weakref
from contextlib import ExitStack
from unittest.mock import patch

import soundfile as sf
import torch

# Run with ComfyUI on PYTHONPATH; use the real V3 schema implementation.
from comfy_api.latest import ComfyExtension, io

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "irodori_contract_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "src")]
sys.modules[PACKAGE] = package


def load_module(name):
    spec = importlib.util.spec_from_file_location(f"{PACKAGE}.{name}", ROOT / "src" / Path(*name.split(".")).with_suffix(".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


models = load_module("modules.models")
quantized_runtime = load_module("modules.quantized_runtime")
comfy = types.ModuleType("comfy")
comfy.__path__ = []
comfy.utils = types.ModuleType("comfy.utils")
management = types.ModuleType("comfy.model_management")
folders = types.ModuleType("folder_paths")
with patch.dict(sys.modules, {"comfy": comfy, "comfy.utils": comfy.utils,
                             "comfy.model_management": management, "folder_paths": folders}):
    nodes = load_module("nodes.generate")
    reference_audio = sys.modules[f"{PACKAGE}.nodes.reference_audio"]


class ReferenceFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.input_patch = patch.object(folders, "get_input_directory", return_value=str(self.root), create=True)
        self.input_patch.start()
        self.addCleanup(self.input_patch.stop)
        self.references = self.root / "irodori_references"
        self.references.mkdir()
        (self.references / "first.wav").write_bytes(b"first")
        (self.references / "second.wav").write_bytes(b"second")

    def test_order_and_duplicate_files_are_preserved(self):
        paths = reference_audio.resolve_reference_files("second.wav\n\nfirst.wav\nsecond.wav\n")
        self.assertEqual([path.name for path in paths], ["second.wav", "first.wav", "second.wav"])

    def test_empty_missing_and_outside_paths_are_rejected(self):
        for files in ("", "missing.wav", "../outside.wav"):
            with self.subTest(files=files):
                self.assertIsInstance(reference_audio.IrodoriTTSLoadReferenceAudios.validate_inputs(files), str)
        self.assertIs(reference_audio.IrodoriTTSLoadReferenceAudios.validate_inputs("first.wav\nsecond.wav"), True)

    def test_replacing_a_file_invalidates_the_loader_cache(self):
        loader = reference_audio.IrodoriTTSLoadReferenceAudios
        initial = loader.fingerprint_inputs("first.wav\nsecond.wav")
        self.assertNotEqual(initial, loader.fingerprint_inputs("second.wav\nfirst.wav"))
        (self.references / "second.wav").write_bytes(b"changed")
        self.assertNotEqual(initial, loader.fingerprint_inputs("first.wav\nsecond.wav"))

    def test_multiselect_and_single_selection(self):
        for names in (["first.wav"], ["second.wav", "first.wav"]):
            self.assertEqual([p.name for p in reference_audio.resolve_reference_files(names)], names)
        self.assertEqual(reference_audio.resolve_reference_files("irodori_references/first.wav"),
                         reference_audio.resolve_reference_files(["first.wav"]))
        nested = self.references / "irodori_references"
        nested.mkdir()
        (nested / "first.wav").touch()
        self.assertEqual(reference_audio.resolve_reference_files(["irodori_references/first.wav"]),
                         [nested / "first.wav"])

    def test_listing_filters_files_and_includes_subfolders(self):
        (self.root / "outside.wav").touch()
        (self.references / "notes.txt").touch()
        (self.references / "sub").mkdir()
        (self.references / "sub/a.MP3").touch()
        self.assertEqual(reference_audio.list_reference_files(), ["first.wav", "second.wav", "sub/a.MP3"])
        (self.references / "third.flac").touch()
        self.assertIn("third.flac", reference_audio.IrodoriTTSLoadReferenceAudios.define_schema().inputs[0].options)
        for value in ([], ["../outside.wav"], ["notes.txt"], [23], 23):
            self.assertIsInstance(reference_audio.IrodoriTTSLoadReferenceAudios.validate_inputs(value), str)

    def test_empty_directory_can_be_listed(self):
        with patch.object(reference_audio, "reference_directory", return_value=self.root / "missing"):
            self.assertEqual(reference_audio.list_reference_files(), [])

    def test_v3_entrypoint_and_registered_schema(self):
        extension_module = load_module("__init__")
        self.assertFalse(hasattr(extension_module, "NODE_CLASS_MAPPINGS"))
        extension = asyncio.run(extension_module.comfy_entrypoint())
        self.assertIsInstance(extension, ComfyExtension)
        classes = asyncio.run(extension.get_node_list())
        schemas = {node.GET_SCHEMA().node_id: node.GET_SCHEMA() for node in classes}
        self.assertEqual(set(schemas), {"IrodoriTTSGenerate", "IrodoriTTSLoadReferenceAudios", "IrodoriTTSSaveAudio"})
        self.assertTrue(all(issubclass(node, io.ComfyNode) for node in classes))
        loader = schemas["IrodoriTTSLoadReferenceAudios"]
        self.assertIsInstance(loader.inputs[0], io.MultiCombo.Input)
        self.assertFalse(loader.outputs[0].is_output_list)
        generator = schemas["IrodoriTTSGenerate"]
        self.assertEqual(generator.outputs[0].io_type, "AUDIO")
        self.assertFalse(next(item for item in generator.inputs if item.id == "unload_after_generate").default)


class ModelFilesTests(unittest.TestCase):
    def test_each_quantized_variant_downloads_only_selected_weights_and_shared_tokenizer(self):
        for model_name, (repo, revision) in models.MODEL_SPECS.items():
            if "/" not in model_name:
                continue
            with self.subTest(model=model_name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                folder, variant = model_name.split("/")
                with patch.object(models, "snapshot_download") as snapshot, patch.object(models, "hf_hub_download"):
                    checkpoint, _ = models.resolve_models(root, True, model_name)
                self.assertEqual(checkpoint, root / folder / variant / "model.safetensors")
                snapshot.assert_called_once_with(repo, revision=revision,
                    allow_patterns=[f"{variant}/model.safetensors", "tokenizer/*"], local_dir=str(root / folder))

    def test_quantized_offline_checks_selected_variant_and_shared_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            name = "Irodori-TTS-v4-Large-Quantized/int8-weight-only"
            for relative in (f"{name}/model.safetensors",
                             "Irodori-TTS-v4-Large-Quantized/tokenizer/tokenizer.json",
                             "Irodori-TTS-v4-Large-Quantized/tokenizer/tokenizer_config.json",
                             "Semantic-DACVAE-Japanese-32dim/weights.pth"):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            with patch.object(models, "snapshot_download") as snapshot, patch.object(models, "hf_hub_download") as download:
                models.resolve_models(root, False, name)
                with self.assertRaisesRegex(FileNotFoundError, "int4-weight-only"):
                    models.resolve_models(root, False, name.replace("int8-weight-only", "int4-weight-only"))
                snapshot.assert_not_called()
                download.assert_not_called()

    def test_large_download_uses_its_pinned_repo_and_shared_codec(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codec = root / "Semantic-DACVAE-Japanese-32dim/weights.pth"
            codec.parent.mkdir()
            codec.touch()
            with patch.object(models, "snapshot_download") as snapshot, patch.object(models, "hf_hub_download") as download:
                checkpoint, resolved_codec = models.resolve_models(root, True, "Irodori-TTS-v4-Large")
                self.assertEqual(checkpoint, root / "Irodori-TTS-v4-Large/model.safetensors")
                self.assertEqual(resolved_codec, codec)
                snapshot.assert_called_once_with(
                    "Aratako/Irodori-TTS-v4-Large", revision=models.MODEL_SPECS["Irodori-TTS-v4-Large"][1],
                    allow_patterns=["model.safetensors", "tokenizer/*"],
                    local_dir=str(root / "Irodori-TTS-v4-Large"))
                download.assert_not_called()

    def test_missing_large_offline_does_not_fall_back_to_small(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(models, "snapshot_download") as download:
            with self.assertRaisesRegex(FileNotFoundError, "Irodori-TTS-v4-Large"):
                models.resolve_models(Path(tmp), False, "Irodori-TTS-v4-Large")
            download.assert_not_called()

    def test_unknown_model_is_rejected_before_download(self):
        with patch.object(models, "snapshot_download") as download:
            with self.assertRaises(ValueError):
                models.resolve_models(ROOT, True, "../other")
            download.assert_not_called()

    def test_missing_offline_does_not_download(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(models, "snapshot_download") as download:
            with self.assertRaises(FileNotFoundError):
                models.resolve_models(Path(tmp), False)
            download.assert_not_called()

    def test_complete_local_files_never_contact_hub(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("Irodori-TTS-v4.1-Small/model.safetensors",
                         "Irodori-TTS-v4.1-Small/tokenizer/tokenizer.json",
                         "Irodori-TTS-v4.1-Small/tokenizer/tokenizer_config.json",
                         "Semantic-DACVAE-Japanese-32dim/weights.pth"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            with patch.object(models, "snapshot_download") as snapshot, patch.object(models, "hf_hub_download") as download:
                checkpoint, codec = models.resolve_models(root, True)
                self.assertTrue(checkpoint.is_file() and codec.is_file())
                snapshot.assert_not_called()
                download.assert_not_called()


class RuntimeTensorTests(unittest.TestCase):
    @unittest.skipUnless(torch.cuda.is_available() and importlib.util.find_spec("torchao"), "CUDA and torchao required")
    def test_quantized_packed_weights_move_to_cuda_and_stay_quantized(self):
        from torchao.quantization import quantize_, Int8WeightOnlyConfig
        runtime = importlib.import_module(f"{PACKAGE}.modules.vendor.irodori_tts.inference_runtime")
        module = torch.nn.Sequential(torch.nn.Linear(128, 32, bias=False)).to(dtype=torch.bfloat16)
        quantize_(module, Int8WeightOnlyConfig(version=2))
        runtime._move_inference_module(module, device=torch.device("cuda"), dtype=torch.bfloat16)
        self.assertEqual(module[0].weight.qdata.device.type, "cuda")
        self.assertEqual(module[0].weight.qdata.dtype, torch.int8)
        self.assertEqual(module[0].weight.scale.device.type, "cuda")
        with torch.inference_mode():
            output = module(torch.ones(1, 128, device="cuda", dtype=torch.bfloat16))
        self.assertTrue(torch.isfinite(output).all())

    def test_bf16_move_preserves_complex_buffers_without_full_model_staging(self):
        runtime = importlib.import_module(f"{PACKAGE}.modules.vendor.irodori_tts.inference_runtime")
        module = torch.nn.Linear(2, 2)
        module.weight.grad = torch.ones_like(module.weight)
        module.register_buffer("rotary", torch.tensor([1 + 2j], dtype=torch.complex64))
        module.register_buffer("floating", torch.ones(2))
        module.register_buffer("indices", torch.arange(2))
        with patch.object(module, "to", side_effect=AssertionError("Do not stage the full model on GPU")):
            runtime._move_inference_module(module, device=torch.device("cpu"), dtype=torch.bfloat16)
        self.assertEqual(module.weight.dtype, torch.bfloat16)
        self.assertEqual(module.weight.grad.dtype, torch.bfloat16)
        self.assertEqual(module.floating.dtype, torch.bfloat16)
        self.assertEqual(module.indices.dtype, torch.int64)
        torch.testing.assert_close(module.rotary, torch.tensor([1 + 2j], dtype=torch.complex64))


class QuantizedRuntimeTests(unittest.TestCase):
    def test_precision_and_gpu_matrix_before_dependencies(self):
        with patch.object(quantized_runtime, "_require_torchao_safetensors") as require, \
             patch.object(torch.cuda, "is_bf16_supported", return_value=True):
            for variant in models.QUANTIZATION_VARIANTS:
                name = "Irodori-TTS-v4-Large-Quantized/" + variant
                for capability in ((8, 0), (8, 6), (8, 9), (9, 0)):
                    with self.subTest(variant=variant, capability=capability), \
                         patch.object(torch.cuda, "get_device_capability", return_value=capability):
                        require.reset_mock()
                        if variant.startswith("float8") and capability < (8, 9):
                            with self.assertRaisesRegex(ValueError, "FP8"):
                                quantized_runtime.resolve_quantized_precision(name, "cuda", "fp32")
                            require.assert_not_called()
                        else:
                            self.assertEqual(quantized_runtime.resolve_quantized_precision(name, "cuda", "fp32"), "bf16")
                            require.assert_called_once()

    def test_cpu_and_unsupported_bf16_fail_before_dependencies(self):
        name = "Irodori-TTS-v4.1-Small-Quantized/int8-weight-only"
        with patch.object(quantized_runtime, "_require_torchao_safetensors") as require, \
             patch.object(torch.cuda, "is_bf16_supported", return_value=False):
            for device in ("cpu", "cuda"):
                with self.assertRaisesRegex(ValueError, "BF16"):
                    quantized_runtime.resolve_quantized_precision(name, device, "fp32")
            require.assert_not_called()

    def test_unquantized_never_requires_torchao(self):
        with patch.object(quantized_runtime, "_require_torchao_safetensors") as require:
            self.assertEqual(quantized_runtime.resolve_quantized_precision(models.DEFAULT_MODEL, "cpu", "fp32"), "fp32")
            require.assert_not_called()

    def test_missing_torchao_explains_installation(self):
        with patch.object(quantized_runtime, "_require_torchao_safetensors", side_effect=RuntimeError("missing")), \
             patch.object(torch.cuda, "is_bf16_supported", return_value=True), \
             patch.object(torch.cuda, "get_device_capability", return_value=(8, 6)):
            with self.assertRaisesRegex(RuntimeError, "requirements-quantized.txt"):
                quantized_runtime.resolve_quantized_precision("Irodori-TTS-v4-Large-Quantized/int8-weight-only", "cuda", "fp32")


class ReferenceTests(unittest.TestCase):
    def test_stereo_downmix_preserves_rate_and_float_values(self):
        audio = {"waveform": torch.tensor([[[0.2, 0.4], [0.4, 0.8]]]), "sample_rate": 24000}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ref.wav"
            nodes.prepare_reference(audio, path)
            waveform, rate = sf.read(path)
            self.assertEqual(rate, 24000)
            torch.testing.assert_close(torch.tensor(waveform).float(), torch.tensor([0.3, 0.6]))

    def test_invalid_audio(self):
        for waveform in (torch.zeros(2, 1, 20), torch.zeros(1, 1, 0),
                         torch.full((1, 1, 10), float("nan")), torch.zeros(10)):
            with self.subTest(shape=waveform.shape), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(ValueError):
                    nodes.prepare_reference({"waveform": waveform, "sample_rate": 48000}, Path(tmp) / "ref.wav")


class ModeTests(unittest.TestCase):
    def setUp(self):
        self.inputs = dict(mode="text", text="こんにちは。", seed=0, steps=40,
                           cfg_text=3., cfg_reference=5., cfg_caption=3., seconds=0.,
                           duration_scale=1., device="cpu", precision="fp32",
                           codec_device="cpu", allow_download=False)

    def test_required_reference_checked_before_model_loading(self):
        for mode in ("text_reference", "text_caption_reference"):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "reference_audio"):
                nodes.IrodoriTTSGenerate.execute(**(self.inputs | {"mode": mode}))

    def test_model_selector_is_appended_and_old_workflows_default_to_small(self):
        selector = nodes.IrodoriTTSGenerate.define_schema().inputs[-2]
        self.assertEqual(selector.id, "model_name")
        self.assertTrue(selector.optional)
        self.assertEqual(selector.default, "Irodori-TTS-v4.1-Small")
        self.assertEqual(selector.options[:2], ["Irodori-TTS-v4.1-Small", "Irodori-TTS-v4-Large"])
        self.assertEqual(len(selector.options), 12)
        dynamic = nodes.IrodoriTTSGenerate.define_schema().inputs[-1]
        self.assertEqual(dynamic.id, "dynamic_vram")
        self.assertTrue(dynamic.default)

    def test_invalid_model_is_rejected_before_loading(self):
        with self.assertRaisesRegex(ValueError, "model_name"):
            nodes.IrodoriTTSGenerate.execute(**self.inputs, model_name="unknown")

    def test_required_caption(self):
        for mode in ("text_caption", "text_caption_reference"):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "caption"):
                nodes.IrodoriTTSGenerate.execute(**(self.inputs | {"mode": mode}), reference_audio={})

    def test_one_reference_socket_accepts_both_loader_types(self):
        optional = {item.id: item for item in nodes.IrodoriTTSGenerate.define_schema().inputs if item.optional}
        self.assertNotIn("reference_audios", optional)
        self.assertEqual(optional["reference_audio"].get_io_type(), "AUDIO,IRODORI_REFERENCE_AUDIOS")

    def test_blank_text(self):
        with self.assertRaises(ValueError):
            nodes.IrodoriTTSGenerate.execute(**(self.inputs | {"text": "  "}))

    def test_invalid_mode(self):
        with self.assertRaises(ValueError):
            nodes.IrodoriTTSGenerate.execute(**(self.inputs | {"mode": "unexpected"}))

    def test_bf16_cpu_rejected_before_loading(self):
        with self.assertRaisesRegex(ValueError, "bf16"):
            nodes.IrodoriTTSGenerate.execute(**(self.inputs | {"precision": "bf16"}))


class RuntimeCacheTests(unittest.TestCase):
    def test_manual_release_clears_runtime_and_next_generation_reloads(self):
        self.generate()
        self.assertEqual(nodes.release_cached_runtime(), "released")
        self.assertIsNone(self.references[0]())
        self.assertIsNone(nodes._RUNTIME_KEY)
        self.assertEqual(nodes.release_cached_runtime(), "empty")
        self.generate()
        self.assertEqual(len(self.references), 2)

    def test_manual_release_does_not_interrupt_active_generation(self):
        self.generate()
        with nodes._RUNTIME_LOCK:
            self.assertEqual(nodes.release_cached_runtime(), "busy")
            self.assertIsNotNone(self.references[0]())
        self.assertEqual(nodes.release_cached_runtime(), "released")

    def test_release_endpoint_reports_busy_and_success(self):
        import json
        routes = load_module("modules.routes")
        for status, code in (("busy", 409), ("released", 200), ("empty", 200)):
            with self.subTest(status=status), patch.object(routes, "release_cached_runtime", return_value=status):
                response = asyncio.run(routes.release_runtime(None))
                self.assertEqual(response.status, code)
                self.assertEqual(json.loads(response.text), {"status": status})

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.references = []
        self.requests = []
        self.reference_waves = []
        self.load_inference_modes = []
        owner = self
        self.inputs = dict(mode="text", text="こんにちは。", seed=0, steps=40,
                           cfg_text=3., cfg_reference=5., cfg_caption=3., seconds=0.,
                           duration_scale=1., device="cpu", precision="fp32",
                           codec_device="cpu", allow_download=False)

        class FakeRuntime:
            fail = False

            def synthesize(self, request, **kwargs):
                owner.requests.append(request)
                owner.reference_waves.append([sf.read(path) for path in request.ref_wavs or []])
                if self.fail:
                    raise RuntimeError("interrupted")
                return types.SimpleNamespace(audio=torch.ones(1, 100), sample_rate=48000)

        def build(key):
            self.load_inference_modes.append(torch.is_inference_mode_enabled())
            # A replacement must not temporarily coexist with the old model.
            self.assertTrue(all(ref() is None for ref in self.references))
            runtime = FakeRuntime()
            runtime.model = object()
            self.references.append(weakref.ref(runtime))
            return runtime

        runtime_module = types.ModuleType(f"{PACKAGE}.modules.vendor.irodori_tts.inference_runtime")
        runtime_module.InferenceRuntime = types.SimpleNamespace(from_key=build)
        runtime_module.RuntimeKey = types.SimpleNamespace
        runtime_module.SamplingRequest = types.SimpleNamespace
        self.stack.enter_context(patch.dict(sys.modules, {runtime_module.__name__: runtime_module}))
        for name in ("throw_exception_if_processing_interrupted", "unload_all_models", "soft_empty_cache"):
            self.stack.enter_context(patch.object(management, name, create=True))
        self.stack.enter_context(patch.object(comfy.utils, "ProgressBar", create=True))
        self.stack.enter_context(patch.object(folders, "models_dir", str(ROOT), create=True))
        self.stack.enter_context(patch.object(nodes, "resolve_models", side_effect=
            lambda root, allow_download, model_name: (ROOT / model_name / "model.safetensors", ROOT / "weights.pth")))
        self.stack.enter_context(patch.object(torch.cuda, "is_available", return_value=True))
        self.stack.enter_context(patch.object(torch.cuda, "is_bf16_supported", return_value=True))
        nodes._clear_runtime_cache()
        self.addCleanup(nodes._clear_runtime_cache)

    def generate(self, **changes):
        return nodes.IrodoriTTSGenerate.execute(**(self.inputs | changes))

    def test_execute_returns_v3_audio_output(self):
        output = self.generate()
        self.assertIsInstance(output, io.NodeOutput)
        self.assertEqual(output.result[0]["sample_rate"], 48000)

    def test_default_reuses_across_calls_and_changed_prompts(self):
        self.generate()
        self.generate(seed=2, text="こんばんは。", steps=20)
        self.assertEqual(len(self.references), 1)
        self.assertIsNotNone(self.references[0]())

    def test_load_disables_outer_inference_mode_and_restores_it(self):
        with torch.inference_mode():
            self.generate()
            self.assertTrue(torch.is_inference_mode_enabled())
        self.assertEqual(self.load_inference_modes, [False])

    def test_dynamic_backend_switch_and_targeted_unload(self):
        events = []
        class FakeManager:
            def __init__(self, model, device):
                events.append("create")
            def load(self):
                events.append("load")
            def close(self):
                events.append("close")
        module = types.ModuleType(f"{PACKAGE}.modules.dynamic_vram")
        module.DynamicModel = FakeManager
        with patch.dict(sys.modules, {module.__name__: module}), \
             patch.object(comfy, "memory_management", types.SimpleNamespace(aimdo_enabled=True), create=True):
            self.generate(device="cuda")
            self.assertTrue(nodes._RUNTIME_KEY.comfy_dynamic_vram)
            management.unload_all_models.assert_not_called()
            self.generate(device="cuda", seed=10)
            self.assertEqual(len(self.references), 1)
            self.generate(device="cuda", dynamic_vram=False)
            self.assertFalse(nodes._RUNTIME_KEY.comfy_dynamic_vram)
            self.assertEqual(events, ["create", "load", "load", "close"])
            self.generate(device="cuda", unload_after_generate=True)
            self.assertEqual(events[-3:], ["create", "load", "close"])
            self.assertIsNone(nodes._RUNTIME_MANAGER)

    def test_model_switch_replaces_runtime_and_same_model_reuses_it(self):
        self.generate()
        self.assertIn("Irodori-TTS-v4.1-Small", nodes._RUNTIME_KEY.checkpoint)
        self.generate(model_name="Irodori-TTS-v4-Large")
        self.assertEqual(len(self.references), 2)
        self.assertIsNone(self.references[0]())
        self.assertIn("Irodori-TTS-v4-Large", nodes._RUNTIME_KEY.checkpoint)
        self.generate(model_name="Irodori-TTS-v4-Large", seed=23)
        self.assertEqual(len(self.references), 2)
        self.generate()
        self.assertEqual(len(self.references), 3)

    def test_quantized_variant_switch_and_effective_precision_cache(self):
        with patch.object(quantized_runtime, "_require_torchao_safetensors"), \
             patch.object(torch.cuda, "get_device_capability", return_value=(8, 6)):
            name = "Irodori-TTS-v4-Large-Quantized/"
            self.generate(device="cuda", model_name=name + "int8-weight-only")
            self.assertEqual(nodes._RUNTIME_KEY.model_precision, "bf16")
            self.generate(device="cuda", model_name=name + "int8-weight-only", precision="bf16")
            self.assertEqual(len(self.references), 1)
            self.generate(device="cuda", model_name=name + "int4-weight-only")
            self.assertEqual(len(self.references), 2)
            self.assertIsNone(self.references[0]())

    def test_unload_reuses_then_releases_and_next_call_reloads(self):
        self.generate()
        self.generate(unload_after_generate=True)
        self.assertEqual(len(self.references), 1)
        self.assertIsNone(self.references[0]())
        self.assertIsNone(nodes._RUNTIME_KEY)
        self.generate()
        self.assertEqual(len(self.references), 2)

    def test_device_precision_and_codec_changes_replace_the_runtime(self):
        self.generate()
        self.generate(device="cuda")
        self.generate(device="cuda", precision="bf16")
        self.generate(device="cuda", precision="bf16", codec_device="cuda")
        self.assertEqual(len(self.references), 4)
        self.assertTrue(all(ref() is None for ref in self.references[:-1]))

    def test_inference_failure_discards_cached_runtime(self):
        self.generate()
        nodes._RUNTIME.fail = True
        with self.assertRaisesRegex(RuntimeError, "interrupted"):
            self.generate()
        self.assertIsNone(nodes._RUNTIME)
        self.assertIsNone(nodes._RUNTIME_KEY)
        self.generate()
        self.assertEqual(len(self.references), 2)

    def test_multiple_references_keep_order_rates_and_cleanup(self):
        clips = [{"waveform": torch.full((1, 2, 30 + index), value), "sample_rate": rate}
                 for index, (value, rate) in enumerate(((0.1, 16000), (0.2, 24000), (0.3, 48000)))]
        self.generate(mode="text_caption_reference", caption="穏やかに", reference_audio=clips)
        self.assertEqual([rate for _, rate in self.reference_waves[0]], [16000, 24000, 48000])
        self.assertEqual([len(wav) for wav, _ in self.reference_waves[0]], [30, 31, 32])
        for index, (wave, _) in enumerate(self.reference_waves[0]):
            self.assertAlmostEqual(float(wave[0]), (index + 1) / 10, places=6)
        self.assertFalse(self.requests[0].no_ref)
        self.assertTrue(all(not Path(path).exists() for path in self.requests[0].ref_wavs))
        self.generate(mode="text_reference", reference_audio=clips[:2])
        self.assertEqual(len(self.references), 1)
        self.assertEqual(len(self.requests[-1].ref_wavs), 2)

    def test_text_mode_ignores_all_reference_inputs(self):
        self.generate(reference_audio=[{}])
        self.assertIsNone(self.requests[0].ref_wavs)
        self.assertTrue(self.requests[0].no_ref)

    def test_multiple_reference_temporary_files_are_removed_on_failure(self):
        self.generate()
        nodes._RUNTIME.fail = True
        clip = {"waveform": torch.ones(1, 1, 10), "sample_rate": 24000}
        with self.assertRaisesRegex(RuntimeError, "interrupted"):
            self.generate(mode="text_reference", reference_audio=[clip, clip])
        self.assertTrue(all(not Path(path).exists() for path in self.requests[-1].ref_wavs))
        self.assertIsNone(nodes._RUNTIME)

    def test_caption_without_reference_uses_caption_conditioning(self):
        self.generate(mode="text_caption", caption="穏やかな声", reference_audio=[{}])
        self.assertTrue(self.requests[0].no_ref)
        self.assertIsNone(self.requests[0].ref_wavs)
        self.assertEqual(self.requests[0].caption, "穏やかな声")

    def test_single_audio_and_single_item_list_use_same_socket(self):
        clip = {"waveform": torch.ones(1, 1, 20), "sample_rate": 24000}
        self.generate(mode="text_reference", reference_audio=clip, caption="unused")
        self.generate(mode="text_reference", reference_audio=[clip])
        self.assertEqual([len(r.ref_wavs) for r in self.requests], [1, 1])
        self.assertIsNone(self.requests[0].caption)


if __name__ == "__main__":
    unittest.main()
