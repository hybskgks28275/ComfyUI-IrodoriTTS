from pathlib import Path

from huggingface_hub import hf_hub_download, snapshot_download

CONFIG_PATH = Path(__file__).resolve().parents[2] / "models.json"
QUANTIZATION_VARIANTS = (
    "int8-weight-only", "int8-dynamic", "int4-weight-only",
    "float8-weight-only", "float8-dynamic",
)


def load_model_config(path: Path = CONFIG_PATH):
    """Read the user-editable registry once at ComfyUI startup."""
    import json
    import re
    from urllib.parse import urlsplit

    def repo_spec(entry):
        url = urlsplit(entry["url"])
        parts = url.path.strip("/").split("/")
        if (url.scheme != "https" or url.netloc != "huggingface.co"
                or url.query or url.fragment or len(parts) != 2
                or any(not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", part) for part in parts)):
            raise ValueError("url must use the format https://huggingface.co/owner/repository.")
        revision = entry.get("revision", "main")
        if not isinstance(revision, str) or not revision.strip():
            raise ValueError("revision must be a non-empty string.")
        return "/".join(parts), revision

    try:
        config = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        entries = config["models"]
        if not isinstance(entries, list) or not entries:
            raise ValueError("models must contain at least one model.")
        specs = {}
        folders = set()
        for entry in entries:
            name = entry["model_name"]
            if (not isinstance(name, str) or not name or name in {".", ".."}
                    or name.endswith((" ", ".")) or re.search(r'[<>:"/\\|?*\x00-\x1f]', name)
                    or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", name)):
                raise ValueError("model_name must be a folder name without path separators.")
            if name.casefold() in folders or name.casefold() == "semantic-dacvae-japanese-32dim":
                raise ValueError(f"Duplicate model folder name: {name}")
            folders.add(name.casefold())
            repo = repo_spec(entry)
            variants = entry.get("variants")
            if variants is None:
                specs[name] = repo
            else:
                if (not isinstance(variants, list) or not variants
                        or any(v not in QUANTIZATION_VARIANTS for v in variants)
                        or len(set(variants)) != len(variants)):
                    raise ValueError(f"{name}: variants must contain supported quantization methods without duplicates.")
                for variant in variants:
                    specs[f"{name}/{variant}"] = repo
        default = config["default_model"]
        if default not in specs:
            raise ValueError("default_model is not in the model list.")
        codec_repo, codec_revision = repo_spec(config["codec"])
        return default, specs, codec_repo, codec_revision
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise ValueError(f"Check model configuration {path}: {exc}") from exc


DEFAULT_MODEL, MODEL_SPECS, CODEC_REPO, CODEC_REVISION = load_model_config()


def resolve_models(root: Path, allow_download: bool, model_name: str = DEFAULT_MODEL) -> tuple[Path, Path]:
    if model_name not in MODEL_SPECS:
        raise ValueError(f"Unsupported model_name: {model_name}")
    repo, revision = MODEL_SPECS[model_name]
    model_folder, _, variant = model_name.partition("/")
    model_dir = root / model_folder
    checkpoint_name = f"{variant}/model.safetensors" if variant else "model.safetensors"
    checkpoint = model_dir / checkpoint_name
    tokenizer_files = [model_dir / "tokenizer" / name for name in
                       ("tokenizer.json", "tokenizer_config.json")]
    codec_dir = root / "Semantic-DACVAE-Japanese-32dim"
    codec = codec_dir / "weights.pth"
    required = [checkpoint, *tokenizer_files, codec]
    missing = [str(path) for path in required if not path.is_file()]
    if missing and not allow_download:
        raise FileNotFoundError("Missing model files. Enable allow_download: "
                                + ", ".join(missing))
    if not checkpoint.is_file() or any(not path.is_file() for path in tokenizer_files):
        snapshot_download(repo, revision=revision,
                          allow_patterns=[checkpoint_name, "tokenizer/*"],
                          local_dir=str(model_dir))
    if not codec.is_file():
        hf_hub_download(CODEC_REPO, "weights.pth", revision=CODEC_REVISION,
                        local_dir=str(codec_dir))
    return checkpoint, codec
