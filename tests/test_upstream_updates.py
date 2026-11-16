"""Contracts for the October upstream tokenizer, attention, cache and batching updates."""
import importlib
import os
from collections import OrderedDict
from dataclasses import replace
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

import torch
from tokenizers import Tokenizer
from tokenizers.models import Unigram
from transformers import PreTrainedTokenizerFast

from test_contracts import PACKAGE

vendor = f"{PACKAGE}.modules.vendor.irodori_tts"
runtime = importlib.import_module(f"{vendor}.inference_runtime")
attention = importlib.import_module(f"{vendor}.attention")
tokenizer = importlib.import_module(f"{vendor}.tokenizer")
split = importlib.import_module(f"{vendor}.token_split")


class TokenSplitTests(unittest.TestCase):
    def test_rare_and_forced_split_preserves_source_vocab_bos_mask_and_truncation(self):
        vocab = [("[UNK]", 0.), ("[BOS]", 0.), ("[PAD]", 0.),
                 ("浦和レッズ", -14.), ("浦", -10.), ("和", -10.), ("レ", -10.), ("ッ", -10.), ("ズ", -10.),
                 ("送料無料", -1.), ("送料", -10.), ("無料", -10.)]
        backend = Tokenizer(Unigram(vocab, unk_id=0))
        fast = PreTrainedTokenizerFast(tokenizer_object=backend, unk_token="[UNK]", bos_token="[BOS]", pad_token="[PAD]")
        wrapper = tokenizer.PretrainedTextTokenizer(fast)
        self.assertEqual(fast.encode("浦和レッズ", add_special_tokens=False), [3])
        wrapper.enable_rare_token_split()
        self.assertEqual(wrapper.encode("浦和レッズ").tolist(), [1, 4, 5, 6, 7, 8])
        self.assertEqual(wrapper.encode("送料無料").tolist(), [1, 10, 11])
        self.assertEqual(fast.encode("浦和レッズ", add_special_tokens=False), [3])
        ids, mask = wrapper.batch_encode(["浦和レッズ", ""], max_length=4)
        self.assertEqual(ids.tolist(), [[1, 4, 5, 6], [1, 2, 2, 2]])
        self.assertEqual(mask.tolist(), [[True] * 4, [True, False, False, False]])
        ids, mask = wrapper.batch_encode(["送料無料"], max_length=1)
        self.assertEqual(ids.tolist(), [[1]])
        self.assertTrue(mask.all())

    def test_hiragana_and_validated_keep_words_are_not_disabled(self):
        self.assertFalse(split._disabled("こんにちは", -20))
        self.assertFalse(split._disabled("心筋梗塞", -20))
        self.assertTrue(split._disabled("浦和レッズ", -14))


class AttentionTests(unittest.TestCase):
    def test_cudnn_opt_out_retains_fallbacks(self):
        with patch.dict(os.environ, {"IRODORI_SDPA_CUDNN": "0"}):
            self.assertNotIn(attention.SDPBackend.CUDNN_ATTENTION, attention._sdpa_priority())
            self.assertIn(attention.SDPBackend.MATH, attention._sdpa_priority())
        with patch.dict(os.environ, {"IRODORI_SDPA_CUDNN": "1"}):
            self.assertEqual(attention._sdpa_priority()[0], attention.SDPBackend.CUDNN_ATTENTION)

    def test_cpu_masked_attention_matches_sdpa(self):
        q = torch.randn(2, 5, 2, 8)
        mask = torch.tensor([[[[True, True, False, False, False]]], [[[True] * 5]]])
        expected = torch.nn.functional.scaled_dot_product_attention(q.transpose(1, 2), q.transpose(1, 2), q.transpose(1, 2), attn_mask=mask)
        torch.testing.assert_close(attention.masked_sdpa(q, q, q, mask), expected.transpose(1, 2))


    def test_comfy_kitchen_opt_in_keeps_cpu_mask_and_disables_fa3(self):
        q = torch.randn(2, 5, 2, 8)
        mask = torch.tensor([[True, True, False, False, False], [True] * 5])
        expected = attention.masked_sdpa(q, q, q, mask[:, None, None, :])
        with (
            attention.use_attention_backend("comfy_kitchen"),
            patch.object(attention, "_kitchen_attention") as kitchen,
            patch.object(attention, "_fa3_varlen_func", object()),
            patch.object(attention, "_fa3_device_ok") as probe,
        ):
            plan = attention.build_context_attention_plan(
                [mask], query_len=q.size(1), attention_dtype=q.dtype,
            )
            self.assertFalse(plan.use_fa3)
            torch.testing.assert_close(attention.context_attention(q, q, q, plan), expected)
            torch.testing.assert_close(attention.prefix_key_mask_attention(q, q, q, mask), expected)
            kitchen.assert_not_called()
            probe.assert_not_called()


class LengthCheckTests(unittest.TestCase):
    def test_resynthesis_reuses_seed_and_forwards_callbacks(self):
        length_check = importlib.import_module(f"{vendor}.length_check")
        recorders = []
        requests = []
        progress = []

        class Recorder:
            def __init__(self, model, on_call):
                self.on_call = on_call
                self.pointer = torch.zeros(100)
                self.calls = 0
                self.text_len = 4
                self.closed = False
                recorders.append(self)

            def close(self):
                self.closed = True

        class Runtime:
            model_cfg = types.SimpleNamespace(num_layers=12, num_heads=20, model_dim=1280, latent_patch_size=1)
            codec = types.SimpleNamespace(sample_rate=48000, model=types.SimpleNamespace(hop_length=1920))
            model = object()

            def synthesize(self, request, log_fn, step_callback):
                requests.append(request)
                current = recorders[-1]
                for i in range(request.num_steps):
                    step_callback(i, request.num_steps)
                    current.calls += 1
                    current.on_call(current)
                return "decoded"

        request = runtime.SamplingRequest(text="test", seed=12, num_steps=2)
        with (
            patch.object(length_check, "PointerRecorder", Recorder),
            patch.object(length_check, "estimated_frames", return_value=60),
            patch.object(length_check, "reading_end", side_effect=[None, 57]),
        ):
            result, info = length_check.synthesize(
                Runtime(), request, step_callback=lambda i, total: progress.append((i, total)),
            )
        self.assertEqual(result, "decoded")
        self.assertEqual(info["length_check"], "resynthesized")
        self.assertEqual(info["retries"], 1)
        self.assertEqual([req.seconds for req in requests], [None, 2.4, 3.0])
        self.assertEqual([req.seed for req in requests], [12, 12, 12])
        self.assertEqual([req.collect_duration_tokens for req in requests], [True, False, False])
        self.assertEqual(progress, [(0, 2), (1, 2)] * 3)
        self.assertTrue(all(recorder.closed for recorder in recorders))


class ReferenceCacheTests(unittest.TestCase):
    def test_content_keys_include_order_normalization_and_length_but_not_temporary_path(self):
        req = runtime.SamplingRequest(text="test", reference_cache_key=("clip_a", "clip_b"))
        key = runtime._reference_latent_key(req, ["nonexistent.wav"], 120.)
        self.assertEqual(key, runtime._reference_latent_key(req, ["another.wav"], 120.))
        self.assertNotEqual(key, runtime._reference_latent_key(replace(req, reference_cache_key=("clip_b", "clip_a")), [], 120.))
        self.assertNotEqual(key, runtime._reference_latent_key(replace(req, ref_normalize_db=None), [], 120.))
        self.assertNotEqual(key, runtime._reference_latent_key(req, [], 60.))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ref.wav"
            path.touch()
            raw = replace(req, reference_cache_key=None)
            before = runtime._reference_latent_key(raw, [str(path)], 120.)
            path.write_bytes(b"changed")
            self.assertNotEqual(before, runtime._reference_latent_key(raw, [str(path)], 120.))

    def test_cache_reuses_then_invalidates_and_evicts_lru(self):
        rt = object.__new__(runtime.InferenceRuntime)
        rt.model = torch.nn.Linear(1, 1)
        rt.model_cfg = types.SimpleNamespace(use_speaker_condition_resolved=True, speaker_patch_size=1, latent_patch_size=1, latent_dim=32)
        rt.model_device = torch.device("cpu")
        rt.codec = types.SimpleNamespace(sample_rate=48000, model=types.SimpleNamespace(hop_length=1920))
        rt.default_max_ref_seconds = 120.
        rt._reference_latents = OrderedDict()
        req = runtime.SamplingRequest(text="test", ref_wavs=["ref.wav"], reference_cache_key=("clip",))
        with patch.object(rt, "_encode_reference_wavs", return_value=(torch.ones(1, 2, 32), [])) as encode:
            for _ in range(2):
                rt._load_reference_latent(req=req, batch_size=1, messages=[])
            self.assertEqual(encode.call_count, 1)
            for i in range(runtime._REFERENCE_LATENT_CACHE_SIZE):
                rt._load_reference_latent(req=replace(req, reference_cache_key=(str(i),)), batch_size=1, messages=[])
            self.assertEqual(len(rt._reference_latents), runtime._REFERENCE_LATENT_CACHE_SIZE)
            rt._load_reference_latent(req=req, batch_size=1, messages=[])
            self.assertEqual(encode.call_count, runtime._REFERENCE_LATENT_CACHE_SIZE + 2)


class BatchContracts(unittest.TestCase):
    def test_lengths_seeds_and_text_do_not_break_batch_compatibility(self):
        first = runtime.SamplingRequest(text="one", no_ref=True, seconds=1, seed=1)
        second = replace(first, text="two", seconds=2, seed=2)
        self.assertEqual(runtime.batch_compatibility_key(first), runtime.batch_compatibility_key(second))
        self.assertNotEqual(runtime.batch_compatibility_key(first), runtime.batch_compatibility_key(replace(first, num_steps=5)))
        self.assertIsNone(runtime.batch_compatibility_key(replace(first, speaker_uncond_mode="noise")))
        padded = runtime._right_pad_cat([torch.ones(1, 2, 3), torch.ones(1, 4, 3)])
        self.assertEqual(padded.shape, (2, 4, 3))
        self.assertFalse(padded[0, 2:].any())
