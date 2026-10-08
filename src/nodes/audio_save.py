"""Audio output with local date templates and ComfyUI playback."""
from datetime import datetime
from pathlib import Path
import re

import av
import soundfile as sf
import torch
import folder_paths
from comfy_api.latest import io, ui

BITRATES = ["64", "96", "128", "160", "192", "256", "320"]


def expand_date(value, now):
    replacements = {
        "yyyymmddhhmmss": now.strftime("%Y%m%d%H%M%S"),
        "yyyymmdd": now.strftime("%Y%m%d"),
        "hhmmss": now.strftime("%H%M%S"),
    }
    for token, replacement in replacements.items():
        value = value.replace("{" + token + "}", replacement).replace(token, replacement)
    return value


def output_location(root, directory, prefix, now):
    directory = expand_date(directory, now).replace("\\", "/")
    prefix = expand_date(prefix, now)
    parts = directory.split("/") if directory else []
    for part in [*parts, prefix]:
        if (not part or part in {".", ".."} or part.endswith((" ", "."))
                or re.search(r'[<>:"/\\|?*\x00-\x1f]', part)
                or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part)):
            raise ValueError("Invalid save name. Specify a relative directory and filename prefix.")
    base = (Path(root) / "audio").resolve()
    target = base.joinpath(*parts).resolve()
    if not base.is_relative_to(Path(root).resolve()) or not target.is_relative_to(base):
        raise ValueError("The save directory must be inside output/audio.")
    return target, prefix


def save_audio(audio, root, filename_prefix, directory, format, bitrate, bit_depth, now=None):
    if format not in {"wav", "mp3", "flac"} or str(bitrate) not in BITRATES or str(bit_depth) not in {"16", "24"}:
        raise ValueError("Invalid format, bitrate, or bit_depth.")
    waveform = audio.get("waveform") if isinstance(audio, dict) else None
    rate = audio.get("sample_rate") if isinstance(audio, dict) else None
    if (not isinstance(waveform, torch.Tensor) or waveform.ndim != 3
            or waveform.shape[0] < 1 or waveform.shape[1] not in (1, 2) or waveform.shape[2] < 1):
        raise ValueError("Connect non-empty mono or stereo AUDIO to audio.")
    if not isinstance(rate, int) or isinstance(rate, bool) or rate <= 0:
        raise ValueError("sample_rate must be a positive integer.")
    waveform = waveform.detach().to(device="cpu", dtype=torch.float32)
    if not torch.isfinite(waveform).all():
        raise ValueError("Audio contains NaN or Inf.")
    if format == "mp3" and rate not in {8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000}:
        raise ValueError("Unsupported MP3 sample rate. Use WAV/FLAC or resample to a supported rate such as 48 kHz.")
    if format == "mp3" and rate < 32000 and int(bitrate) > 160:
        raise ValueError("MP3 below 32 kHz requires a bitrate of 160 kbps or less.")
    target, prefix = output_location(root, directory, filename_prefix, now or datetime.now())
    target.mkdir(parents=True, exist_ok=True)
    results = []
    counter = 1
    for sample in waveform:
        while True:
            path = target / f"{prefix}_{counter:05d}.{format}"
            counter += 1
            try:
                stream = path.open("xb")
                break
            except FileExistsError:
                continue
        try:
            with stream:
                if format in {"wav", "flac"}:
                    sf.write(stream, sample.T.numpy(), rate, format=format.upper(), subtype=f"PCM_{bit_depth}")
                else:
                    with av.open(stream, mode="w", format="mp3") as container:
                        layout = "mono" if sample.shape[0] == 1 else "stereo"
                        encoder = container.add_stream("libmp3lame", rate=rate, layout=layout)
                        encoder.bit_rate = int(bitrate) * 1000
                        frame = av.AudioFrame.from_ndarray(sample.clamp(-1, 1).T.contiguous().reshape(1, -1).numpy(), format="flt", layout=layout)
                        frame.sample_rate = rate
                        frame.pts = 0
                        container.mux(encoder.encode(frame))
                        container.mux(encoder.encode(None))
        except Exception:
            path.unlink(missing_ok=True)
            raise
        results.append({"filename": path.name, "subfolder": target.relative_to(Path(root).resolve()).as_posix(), "type": "output"})
    return results


class IrodoriTTSSaveAudio(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="IrodoriTTSSaveAudio", display_name="Irodori TTS Save Audio",
            category="audio/Irodori TTS", is_output_node=True,
            description="Save and preview audio under output/audio. Date templates use the local time at execution.",
            inputs=[
                io.Audio.Input("audio"),
                io.String.Input("filename_prefix", default="Irodori_{yyyymmddhhmmss}", tooltip="Filename prefix. Replace {yyyymmddhhmmss}, {yyyymmdd}, and {hhmmss} with the date and time."),
                io.String.Input("directory", default="{yyyymmdd}", tooltip="Path relative to output/audio. Leave empty to save directly there. Supports date templates and nested folders."),
                io.Combo.Input("format", options=["wav", "mp3", "flac"], default="wav"),
                io.Combo.Input("bitrate", options=BITRATES, default="192", tooltip="MP3 bitrate in kbps. Ignored for WAV and FLAC."),
                io.Combo.Input("bit_depth", options=["16", "24"], default="16", tooltip="WAV and FLAC bit depth. Ignored for MP3."),
            ], outputs=[io.Audio.Output("audio")],
        )

    @classmethod
    def execute(cls, audio, filename_prefix, directory, format, bitrate, bit_depth):
        results = save_audio(audio, folder_paths.get_output_directory(), filename_prefix, directory, format, bitrate, bit_depth)
        return io.NodeOutput(audio, ui=ui.SavedAudios(results))
