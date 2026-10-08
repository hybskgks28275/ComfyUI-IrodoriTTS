# Third-party code

`src/modules/vendor/irodori_tts` contains the inference dependency closure from
[Aratako/Irodori-TTS](https://github.com/Aratako/Irodori-TTS), commit
`8224dafb46d0aba89209a8f905f1cb7e3299d9c1` (v4.1-Small default).
MIT license: `src/modules/vendor/IRODORI_LICENSE`.

Training scripts, dataset, optimizer, training progress, and Gradio helpers are omitted.
Some internal classes/functions for LoRA, speaker inversion, quantization conversion, and older
architectures remain because the official inference modules import them. The custom
node exposes none of these features. It resolves v4.1-Small and v4-Large checkpoints,
including their official torchao quantized variants for inference.

Local modifications:

- `rf.py`: optional sampling step callback for ComfyUI progress/cancellation.
- `inference_runtime.py`: forwards that callback to the sampler.
- `config.py`: backports `flow_parameterization="rf_velocity"` from upstream
  `89f9d8fbd4d51ea019867ee1197725ede1df13c5` to read v4-Large metadata.
  The local runtime rejects other parameterizations; MeanFlow is not exposed.
- `inference_runtime.py`: converts tensors to the requested precision while moving
  them, avoiding temporary full-FP32 GPU allocation for BF16 loads. Complex rotary
  buffers retain their original dtype. Uses PyTorch's module conversion machinery
  to move torchao wrapper subclasses together with their packed weights.
- `inference_runtime.py`: optional CPU staging for ComfyUI Dynamic VRAM, while
  retaining the requested execution device in the runtime.
- `model.py`: optional execution-device override, because CPU-staged parameters
  no longer indicate the sampler's device. `dynamic_vram.py` supplies ComfyUI
  casting operations and preserves Irodori/T5Gemma2 normalization formulas.

DACVAE is installed separately from
[facebookresearch/dacvae](https://github.com/facebookresearch/dacvae) commit
`414c20785fc3a28373073ea8ef7a1316eeeaca6e`. It is not copied into this repository.

Pinned model revisions:

- Aratako/Irodori-TTS-v4.1-Small: `2b28324dc263ed5e6638b3cf3dd94c82ead07b4b`
- Aratako/Irodori-TTS-v4-Large: `2e0c55428ce97268a507f1feeb2478f8d9148e8b`
  (Gemma model license; see its model card and bundled terms/NOTICE).
- Aratako/Irodori-TTS-v4.1-Small-Quantized: `ef04e6c3ba56138ae23e86a2eabc004f76990e37` (MIT).
- Aratako/Irodori-TTS-v4-Large-Quantized: `bdef9592db4426bd1c99ccdf0cfc3a213223fb61` (Gemma).
- Aratako/Semantic-DACVAE-Japanese-32dim: `47376ee24834d7a05a48ebabfe3cde29b3c5e214`

The Small/ModernBERT and Large/T5Gemma2 inference paths use Transformers 5.3.0. The upstream
application requirements also cover training and other backbones; they are not
installed wholesale by this node. Neither PEFT nor Gradio is required.
The official quantized checkpoints additionally require torchao 0.16.x
([pytorch/ao](https://github.com/pytorch/ao), BSD-3-Clause), listed separately in
`requirements-quantized.txt`; ordinary models do not require this optional dependency.
