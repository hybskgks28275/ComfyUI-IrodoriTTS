import hashlib
from pathlib import Path

import folder_paths
from comfy_api.latest import io

ReferenceAudios = io.Custom("IRODORI_REFERENCE_AUDIOS")


AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".aiff", ".aif", ".wma", ".mp4", ".webm"}


def reference_directory() -> Path:
    return (Path(folder_paths.get_input_directory()) / "irodori_references").resolve()


def list_reference_files() -> list[str]:
    root = reference_directory()
    if not root.is_dir():
        return []
    return sorted(
        (path.relative_to(root).as_posix() for path in root.rglob("*")
         if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
         and path.resolve().is_relative_to(root)), key=str.casefold)


def resolve_reference_files(files) -> list[Path]:
    root = reference_directory()
    # Accept the old multiline representation as well as the multiselect value.
    if isinstance(files, str):
        files = [name.strip().removeprefix("irodori_references/")
                 for name in files.splitlines() if name.strip()]
    if not isinstance(files, (list, tuple)) or not all(isinstance(name, str) for name in files):
        raise ValueError("Select reference audio from the file list.")
    paths = []
    for name in files:
        path = (root / name).resolve()
        if Path(name).is_absolute() or not path.is_relative_to(root):
            raise ValueError("Select reference files inside input/irodori_references.")
        if path.suffix.lower() not in AUDIO_EXTENSIONS:
            raise ValueError(f"Unsupported audio file format: {name}")
        if not path.is_file():
            raise FileNotFoundError(f"Reference audio not found: {name}")
        paths.append(path)
    if not paths:
        raise ValueError("Place audio in input/irodori_references and select at least one file.")
    return paths


class IrodoriTTSLoadReferenceAudios(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="IrodoriTTSLoadReferenceAudios",
            display_name="Irodori TTS Load Reference Audios",
            category="audio/Irodori TTS",
            description="Select one or more files from input/irodori_references. Each clip keeps its sample rate and duration and is passed through the same output.",
            inputs=[io.MultiCombo.Input(
                "files", options=list_reference_files(), default=[],
                placeholder="Select reference audio (multiple files allowed)", chip=True,
                tooltip="Select files from input/irodori_references. Use the up and down arrows to reorder them. Files are used from top to bottom.",
            )],
            outputs=[ReferenceAudios.Output("reference_audio")],
        )

    @classmethod
    def validate_inputs(cls, files) -> bool | str:
        try:
            resolve_reference_files(files)
        except (ValueError, OSError) as exc:
            return str(exc)
        return True

    @classmethod
    def fingerprint_inputs(cls, files) -> str:
        digest = hashlib.sha256()
        for path in resolve_reference_files(files):
            digest.update(str(path).encode("utf-8"))
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        return digest.hexdigest()

    @classmethod
    def execute(cls, files) -> io.NodeOutput:
        # Match standard Load Audio's format support and PCM conversion.
        from comfy_extras.nodes_audio import load
        import comfy.model_management as mm

        audios = []
        for path in resolve_reference_files(files):
            mm.throw_exception_if_processing_interrupted()
            waveform, sample_rate = load(str(path))
            audios.append({"waveform": waveform.unsqueeze(0), "sample_rate": sample_rate})
        return io.NodeOutput(audios)
