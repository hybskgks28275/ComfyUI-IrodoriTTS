# ComfyUI-IrodoriTTS

[日本語](README.md) | **English**

ComfyUI custom nodes for Japanese text-to-speech with Irodori-TTS v4.1 Small, v4 Large, and their official quantized variants. The nodes use the ComfyUI V3 API (`ComfyExtension`, `io.ComfyNode`, and `define_schema`) and output 48 kHz mono ComfyUI `AUDIO`.

| Mode | Inputs |
| --- | --- |
| `text` | Text to speak |
| `text_caption` | Text and a caption describing the desired delivery |
| `text_reference` | Text and reference audio |
| `text_caption_reference` | Text, caption, and reference audio |
| `text_speaker` | Text and a Speaker Inversion embedding |
| `text_caption_speaker` | Text, caption, and a Speaker Inversion embedding |

Reference audio works without a transcript. You can also apply trained Speaker Inversion embeddings and LoRA adapters during inference.

## Display language

Node labels and custom controls are in English by default. To use Japanese, select **日本語** under **Settings → Locale → Language** in ComfyUI. Other locales use English. Python errors are in English, and the native audio player's controls follow the browser language.

## Installation

### Requirements

- ComfyUI running on Python 3.10 or newer, with V3 API support for `MultiCombo` and `MultiType`.
- Git to clone the repository and install its Git-based codec dependency.
- A CUDA-enabled PyTorch installation and a compatible NVIDIA GPU for CUDA generation. Standard checkpoints also run on the CPU.
- For quantized checkpoints, see the [GPU requirements](#official-quantized-models).

### Install the nodes and dependencies

From the ComfyUI directory that contains `main.py`, clone this repository:

```sh
cd custom_nodes
git clone https://github.com/hybskgks28275/ComfyUI-IrodoriTTS.git
cd ComfyUI-IrodoriTTS
```

If you use a ZIP archive, extract it so that `__init__.py` and `requirements.txt` are directly under `ComfyUI/custom_nodes/ComfyUI-IrodoriTTS/`.

Install the dependencies with **the same Python environment that runs ComfyUI**. Activate its virtual environment first if you use one.

```sh
python -m pip install -r requirements.txt
# For official quantized checkpoints
python -m pip install -r requirements-quantized.txt
# For LoRA adapters
python -m pip install -r requirements-lora.txt
```

Speaker Inversion works with the base dependencies. On ComfyUI Windows Portable, run the following from the portable root, where the `python_embeded/` and `ComfyUI/` directories are located:

```powershell
./python_embeded/python.exe -m pip install -r ./ComfyUI/custom_nodes/ComfyUI-IrodoriTTS/requirements.txt
# For official quantized checkpoints
./python_embeded/python.exe -m pip install -r ./ComfyUI/custom_nodes/ComfyUI-IrodoriTTS/requirements-quantized.txt
# For LoRA adapters
./python_embeded/python.exe -m pip install -r ./ComfyUI/custom_nodes/ComfyUI-IrodoriTTS/requirements-lora.txt
```

Restart ComfyUI and reload the browser after installation.

## Usage

Find **Irodori TTS Generate** in the `audio/Irodori TTS` category, or open a workflow from [examples/](examples/). Drag the JSON file onto the ComfyUI canvas or open it with the workflow menu. Every example uses the standard v4.1 Small checkpoint and saves audio with **Irodori TTS Save Audio**.

| Workflow | Use |
| --- | --- |
| [01_text.json](examples/01_text.json) | Text |
| [06_text_caption.json](examples/06_text_caption.json) | Text and caption |
| [02_text_reference.json](examples/02_text_reference.json) | Text and one or more reference clips |
| [03_text_caption_reference.json](examples/03_text_caption_reference.json) | Text, caption, and one or more reference clips |
| [04_multi_reference.json](examples/04_multi_reference.json) | Text and multiple ordered reference clips |
| [05_multi_caption_reference.json](examples/05_multi_caption_reference.json) | Text, caption, and multiple ordered reference clips |
| [07_text_speaker.json](examples/07_text_speaker.json) | Text and Speaker Inversion |
| [08_text_caption_speaker.json](examples/08_text_caption_speaker.json) | Text, caption, and Speaker Inversion |

1. Enter the Japanese text you want to hear in `text`.
2. In a caption mode, describe the delivery in `caption`, for example `穏やかに、少し楽しそうに話す` (speak calmly, sounding a little cheerful).
3. In a reference mode, connect reference audio. In a speaker mode, select a Speaker Inversion embedding.
4. Set the output directory, filename prefix, and format in **Irodori TTS Save Audio**, then queue the workflow.

### Emojis

**Show emojis** sits below `text` and opens a side panel with 45 labeled emojis. Place the caret or select text before clicking an emoji to insert or replace text. With no caret position, the emoji is appended. Use Ctrl+Z in the text field to undo an insertion. Close the panel with **Hide emojis**, **Close**, or Esc. The panel works in both the classic view and Nodes 2.0.

### Reference audio

1. Put audio files in `irodori_references/` inside the ComfyUI input directory, typically `ComfyUI/input/irodori_references/`. Subdirectories are supported.
2. In **Irodori TTS Load Reference Audios**, open `files` or **Select reference audio (multiple files allowed)** in Nodes 2.0. Select one or more clips. Use **Refresh audio file list** after adding files.
3. Use the up and down arrows in **Reference order (top to bottom)** to set the order. New selections go to the end, and the order is saved in the workflow.
4. Connect the loader to `reference_audio` on the Generate node. A single clip from ComfyUI's standard **Load Audio** also connects to this input.

The runtime converts each clip to mono, normalizes volume, encodes it, and combines the encoded clips in the selected order. Clips can have different durations and sample rates. Official checkpoints use a 120-second total reference limit. A workflow that references a missing file reports an error.

### Model selection

Choose a checkpoint in `model_name`. The default is `Irodori-TTS-v4.1-Small`. Small and Large support all six generation modes. The standard Large model takes about 13.2 GB on disk. Its weights alone use approximately 6.1 GiB in BF16 or 12.3 GiB in FP32.

**System RAM on an 8 GB VRAM GPU:** Dynamic VRAM keeps model weights in system RAM. For the unquantized `Irodori-TTS-v4-Large` checkpoint, allow about 6.1 GiB for BF16 weights alone or 12.3 GiB for FP32 weights. Additional free RAM is needed for temporary allocations during loading, ComfyUI itself, and the codec when it runs on the CPU. The amount of free RAM required depends on precision and workflow. The minimum system RAM for an 8 GB VRAM configuration has yet to be verified.

On a CUDA GPU with BF16 support, enable Dynamic VRAM in ComfyUI and select `dynamic_vram=true`, `precision=bf16`, and `codec_device=cpu` in the Generate node. This places the codec in system RAM.

### Official quantized models

Select a variant such as `Irodori-TTS-v4-Large-Quantized/int8-weight-only` or `Irodori-TTS-v4.1-Small-Quantized/int8-weight-only`. Quantized checkpoints require CUDA and run with BF16 model precision regardless of the `precision` widget.

| Variant | Quantization | GPU requirement |
| --- | --- | --- |
| `int8-weight-only` | INT8 weights, BF16 computation | NVIDIA CUDA with BF16 support |
| `int8-dynamic` | INT8 weights and dynamic INT8 activation quantization | NVIDIA CUDA with BF16 support |
| `int4-weight-only` | INT4 weights, BF16 computation | Ampere or newer (compute capability 8.0+) |
| `float8-weight-only` | FP8 weights and BF16 activations | Ada or newer (compute capability 8.9+) |
| `float8-dynamic` | FP8 weights and dynamic FP8 activation quantization | Ada or newer (compute capability 8.9+) |

The node checks GPU requirements before downloading the checkpoint. Quantized checkpoints support ordered references, model reuse, and optional unloading. Speed depends on the GPU and runtime. FP8 generation has yet to be verified.

### Speaker Inversion and LoRA

Place trained assets under the ComfyUI model directory. The selection lists include subdirectories. Restart ComfyUI and reload the browser to discover new assets.

```text
ComfyUI/models/irodori_tts/
  speakers/
    MyVoice/checkpoint_final.speaker.safetensors
  loras/
    MyAdapter/
      adapter_config.json
      adapter_model.safetensors
```

- For Speaker Inversion, use `text_speaker` or `text_caption_speaker` and choose a file in `speaker_embedding`. Leave `reference_audio` disconnected in these modes. `cfg_reference` sets speaker guidance strength. `speaker_uncond_mode` selects how the unconditional side of CFG is computed, with `mask` by default and `noise` as an alternative.
- For LoRA, choose one PEFT adapter folder with `lora_adapter`. It can be used in any mode, including alongside Speaker Inversion. `lora_strength` ranges from 0 to 2. Use 1 for the trained scale, 0 to disable the whole adapter, or `none` to select the base model.

Match each asset to the base checkpoint used to train it. LoRA runs without merging weights and can be applied to standard and official quantized checkpoints. Changes to the adapter, its strength, or its files reload the model. Speaker embeddings are read for each generation, so switching embeddings reuses the loaded model.

## Generation settings

| Input | Default and behavior |
| --- | --- |
| `steps` | 40 sampling steps |
| `seed` | 0. Use the accompanying control to keep or randomize the seed after generation. |
| `cfg_text` | 3.0. Text guidance strength. |
| `cfg_reference` | 5.0. Reference audio or Speaker Inversion guidance strength. |
| `cfg_caption` | 3.0. Caption guidance strength. |
| `seconds` | 0 for automatic duration. Set a positive value for a fixed duration of up to 30 seconds. |
| `duration_scale` | 1.0. Scales the predicted duration when `seconds=0`. |
| `device` | `auto`. Uses CUDA when available, otherwise CPU. |
| `precision` | `fp32` for standard checkpoints. `bf16` requires a compatible CUDA GPU. |
| `codec_device` | `cpu`. Keeps codec encoding and decoding off the GPU to save VRAM. |
| `allow_download` | `true`. Downloads missing model files at run time. |
| `unload_after_generate` | `false`. Keeps the loaded model and codec for reuse. |
| `dynamic_vram` | `true`. Uses ComfyUI Dynamic VRAM when enabled and running on CUDA. |
| `split_rare_tokens` | `true`. Splits rare long tokens in Small models to reduce misreadings. Changing this setting reloads the model. |
| `length_check` | `false`. With v4.1 Small and `seconds=0`, checks where the reading ends and may regenerate with the same seed at a shorter duration. Extra passes can increase generation time. |

Hold a numeric arrow in the classic view or the minus/plus button in Nodes 2.0 to keep changing the value. The control respects the field's step and limits. Enable **Long generation** (`long_generation`, off by default) in any of the six modes to split a script at punctuation or line breaks and synthesize it sequentially. Set `chunk_max_chars` for the maximum characters per section (default 80) and `pause_ms` for silence between sections (default 250 ms, or 0 for none). With `seconds=0` each section gets a predicted duration. A fixed duration applies per section. The seed increases by one for each section. Connect the single joined `AUDIO` output to Save Audio for playback and export.

### Attention backend

Choose **Attention backend** on the Generate node. The selection is saved in the workflow, and switching it reuses the loaded model.

| Value | Behavior |
| --- | --- |
| `auto` (default) | Uses FlashAttention-3 for supported operations when available, with PyTorch SDPA for other operations. |
| `sdpa` | Uses PyTorch SDPA. |
| `comfy_kitchen` | Uses INT8 Attention with a compatible GPU and a mask-capable comfy-kitchen build. Otherwise uses SDPA. |

INT8 Attention is independent of checkpoint quantization. Output and speed can vary with the backend, GPU, and input length. If cuDNN initialization for variable-length inputs is slow, set `IRODORI_SDPA_CUDNN=0` before starting ComfyUI to exclude cuDNN from masked SDPA.

### Model reuse and VRAM

Generate nodes share one cached model and codec. Changing model, device, precision, effective Dynamic VRAM configuration, token splitting, or LoRA settings can reload the model. Changes to text, seed, mode, reference audio, caption, or speaker embedding reuse it. The runtime also keeps up to 32 encoded reference combinations in CPU memory, keyed by clip contents, sample rate, order, normalization, and length limits.

Click **Release memory** on the Generate node to clear the shared cache after generation, or enable `unload_after_generate` to clear it automatically. Errors and cancellation also clear the cache. Cancellation is checked at each sampling step and between inference stages; a download, model load, or codec operation can take time to return.

When ComfyUI Dynamic VRAM is active, ComfyUI's `ModelPatcherDynamic` transfers and offloads TTS and conditioning weights as needed. Quantized weights retain their packed format during transfer. The codec uses the device selected in `codec_device`. Without Dynamic VRAM, the node unloads other ComfyUI-managed models before generation and manages its own model cache. Look for `DynamicVRAM support detected and enabled` in the ComfyUI startup log.

## Model files and downloads

Models are stored under `irodori_tts/` in ComfyUI's configured model directory. The default layout is:

```text
ComfyUI/models/irodori_tts/
  Irodori-TTS-v4.1-Small/
    model.safetensors
    tokenizer/tokenizer.json
    tokenizer/tokenizer_config.json
  Irodori-TTS-v4-Large/
    model.safetensors
    tokenizer/tokenizer.json
    tokenizer/tokenizer_config.json
  Irodori-TTS-v4.1-Small-Quantized/
    int8-weight-only/model.safetensors
    tokenizer/tokenizer.json
    tokenizer/tokenizer_config.json
  Irodori-TTS-v4-Large-Quantized/
    int8-weight-only/model.safetensors
    tokenizer/tokenizer.json
    tokenizer/tokenizer_config.json
  Semantic-DACVAE-Japanese-32dim/
    weights.pth
```

The node downloads the selected checkpoint and its tokenizer from pinned revisions and reuses the shared codec. The initial Small and codec download is about 3.5 GB. Quantized weights are about 813–906 MiB for Small and 2,818–3,665 MiB for Large. Variants of the same model share a tokenizer.

Set `allow_download=false` to require local model files. Reference clips are processed as temporary WAV files on the local machine and removed after processing. SilentCipher watermarking is optional. When SilentCipher is installed, the runtime can download its model on first use.

### Edit the model list

Edit [models.json](models.json), then restart ComfyUI and reload the browser. Entries appear in the same order in the Generate node. A standard checkpoint entry looks like this:

```json
{
  "model_name": "My-Irodori-Model",
  "url": "https://huggingface.co/OWNER/REPOSITORY"
}
```

For a quantized repository, add a `variants` list:

```json
{
  "model_name": "My-Irodori-Quantized",
  "url": "https://huggingface.co/OWNER/REPOSITORY",
  "revision": "main",
  "variants": ["int8-weight-only", "int8-dynamic", "int4-weight-only"]
}
```

- `model_name` is the display name and local directory name. Use a unique name without path separators.
- `url` is the Hugging Face repository root URL. `revision` accepts a commit, tag, or branch and defaults to `main`.
- `default_model` sets the default selection. To default to a quantized variant, use its expanded name, such as `My-Irodori-Quantized/int8-weight-only`.
- `codec` sets the shared codec repository and revision.

Use only checkpoints compatible with the bundled Irodori runtime. Standard checkpoints need `model.safetensors` at the repository root. Quantized checkpoints need `<variant>/model.safetensors`. Both need `tokenizer/`. If you want to use a different revision or weights while keeping an existing local copy, add an entry with a new `model_name`.

## Save and preview audio

Connect the Generate node's `audio` output to **Irodori TTS Save Audio**. After saving, use the built-in HTML player to play, seek, adjust volume, or mute. Volume changes apply only to playback. The node also passes the input audio through to other nodes.

| Input | Behavior |
| --- | --- |
| `filename_prefix` | Default: `Irodori_{yyyymmddhhmmss}`. |
| `directory` | Relative to ComfyUI's `output/audio/`. Default: `{yyyymmdd}`. Leave blank for the base directory or use a nested path such as `project/{yyyymmdd}`. |
| `format` | `wav`, `mp3`, or `flac`. |
| `bitrate` | MP3 only. 64, 96, 128, 160, 192, 256, or 320 kbps. |
| `bit_depth` | WAV and FLAC only. 16 or 24 bits. |

The filename and directory accept `{yyyymmddhhmmss}`, `{yyyymmdd}`, and `{hhmmss}` with or without braces. They expand to the local time at execution, shared by all items in a batch. Files are numbered, for example `output/audio/20260929/Irodori_20260929153045_00001.wav`. Existing files are preserved.

The save node preserves sample rate and channel count and supports mono, stereo, and audio batches. MP3 requires a standard sample rate from 8 to 48 kHz. Use 160 kbps or less below 32 kHz. If ComfyUI reuses a cached result for unchanged inputs, change the filename prefix or another save input to write a new file.

## Development and verification

Run the tests from this repository using the Python environment that runs ComfyUI. Replace `<path-to-ComfyUI>` with the directory containing `main.py`.

```powershell
$comfyRoot = '<path-to-ComfyUI>'
$env:PYTHONPATH = $comfyRoot
python -m unittest discover -s tests -p 'test_*.py'
python tests/smoke_generate.py --comfy-root "$comfyRoot" --output-dir ./work/smoke
python tests/smoke_dynamic_vram.py --comfy-root "$comfyRoot" --model-name Irodori-TTS-v4.1-Small --output-dir ./work/dynamic-smoke
```

```bash
comfy_root='<path-to-ComfyUI>'
PYTHONPATH="$comfy_root" python -m unittest discover -s tests -p 'test_*.py'
python tests/smoke_generate.py --comfy-root "$comfy_root" --output-dir ./work/smoke
python tests/smoke_dynamic_vram.py --comfy-root "$comfy_root" --model-name Irodori-TTS-v4.1-Small --output-dir ./work/dynamic-smoke
```

The smoke tests need local weights and sufficient memory. To smoke test Speaker Inversion and LoRA, install the LoRA dependencies and run `tests/smoke_personalization.py` with `--comfy-root` and `--output-dir`. It uses synthetic assets to check loading, generation, reuse, offloading, and release. Add `--quantized` to include the Small INT8 weight-only checkpoint in the test.

| Path | Contents |
| --- | --- |
| `__init__.py` | ComfyUI entry point and web directory |
| `src/nodes/` | Generate, reference audio loader, and audio save nodes |
| `src/modules/` | Model settings, quantization, Dynamic VRAM, and routes |
| `src/modules/vendor/` | Bundled Irodori inference code and its license |
| `web/` and `locales/` | Frontend extensions and English and Japanese translations |
| `models.json` | Model list |
| `tests/` and `examples/` | Tests and example workflows |

## Sources and licenses

This custom node is available under the [MIT license](LICENSE). The bundled code and local modifications are documented in [THIRD_PARTY.md](THIRD_PARTY.md). The checkpoints and dependencies have separate terms.

- [Official Irodori-TTS inference code](https://github.com/Aratako/Irodori-TTS)
- [Irodori-TTS v4.1 Small](https://huggingface.co/Aratako/Irodori-TTS-v4.1-Small) and [official quantized variants](https://huggingface.co/Aratako/Irodori-TTS-v4.1-Small-Quantized)
- [Irodori-TTS v4 Large](https://huggingface.co/Aratako/Irodori-TTS-v4-Large) and [official quantized variants](https://huggingface.co/Aratako/Irodori-TTS-v4-Large-Quantized) (Gemma terms)
- [Semantic DACVAE audio codec](https://huggingface.co/Aratako/Semantic-DACVAE-Japanese-32dim)
