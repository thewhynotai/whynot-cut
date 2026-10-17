# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
# Ported from the owner's Kalam engine (engine/setup_models.py); see adobe/tools/README.md. Release-time / first-run tool: it
# converts and downloads the Kalam model pack into <engine home>/tools/kalam/models (HF cache: tools/kalam/hf), never into the
# plugin folder. Changes to the upstream file (portability audit): relative imports; the MLX conversion (convert_hf_whisper,
# main) refuses to run off macOS; ALIGNER_REPO names the aligner download; main_cli replaces the upstream `__main__` block
# (default folder = the engine home pack, HF_HOME kept inside it unless the caller set it). The conversion code is unchanged.
"""Download / convert the models Kalam uses. usage: setup_models.py <models_dir>  (HF_HOME decides the HF cache)"""
import json
import os
import sys
from pathlib import Path

from . import platform as _platform
from . import revisions as _revisions
from .store import Store

ARABIC_SRC = "oddadmix/whisper-large-v3-turbo-arabic-dialectal"
OTHERS = ["mlx-community/whisper-large-v3-turbo", "mlx-community/parakeet-tdt-0.6b-v2",
          "MahmoudAshraf/mms-300m-1130-forced-aligner"]
# The revisions, licences and the aligner pair live in revisions.py (ONE table, shared with the runtime lookups: a download
# pinned to a commit leaves no "main" reference in the cache, so the runtime must ask for the same revision).
REVISIONS, LICENCES, ALIGNER_REPO, ALIGNER_REV = _revisions.REVISIONS, _revisions.LICENCES, _revisions.ALIGNER_REPO, _revisions.ALIGNER_REV
_rev = _revisions.pinned


def _notice(repo: str) -> None:
    """one line before a model is downloaded: its name, licence and pinned revision (size: not recorded)"""
    print("    model: %s | licence: %s | revision: %s" % (repo, LICENCES.get(repo, "see the licence table"), _rev(repo)[:8]),
          flush=True)
_MAC_ONLY = "the MLX models are for Apple Silicon (macOS) only: use the portable pack (--portable) on this machine"

# Hugging Face Whisper names -> mlx_whisper names
_REPL = [("model.", ""), (".layers.", ".blocks."), (".self_attn_layer_norm", ".attn_ln"),
         (".encoder_attn_layer_norm", ".cross_attn_ln"), (".self_attn.", ".attn."), (".encoder_attn.", ".cross_attn."),
         (".final_layer_norm", ".mlp_ln"), (".q_proj", ".query"), (".k_proj", ".key"), (".v_proj", ".value"),
         (".out_proj", ".out"), (".fc1", ".mlp1"), (".fc2", ".mlp2"),
         ("decoder.embed_positions.weight", "decoder.positional_embedding"),
         ("decoder.embed_tokens", "decoder.token_embedding"), ("encoder.layer_norm", "encoder.ln_post"),
         ("decoder.layer_norm", "decoder.ln")]


def convert_hf_whisper(repo: str, out: Path) -> None:
    if sys.platform != "darwin":
        raise RuntimeError(_MAC_ONLY)
    import mlx.core as mx
    from huggingface_hub import snapshot_download
    src = Path(snapshot_download(repo, allow_patterns=["*.json", "model.safetensors"], revision=_rev(repo)))
    with open(src / "config.json", encoding="utf-8") as f:
        cfg = json.load(f)
    dims = {"n_mels": cfg["num_mel_bins"], "n_audio_ctx": cfg["max_source_positions"], "n_audio_state": cfg["d_model"],
            "n_audio_head": cfg["encoder_attention_heads"], "n_audio_layer": cfg["encoder_layers"],
            "n_vocab": cfg["vocab_size"], "n_text_ctx": cfg["max_target_positions"], "n_text_state": cfg["d_model"],
            "n_text_head": cfg["decoder_attention_heads"], "n_text_layer": cfg["decoder_layers"]}
    weights = {}
    for k, v in mx.load(str(src / "model.safetensors")).items():
        if k.startswith("proj_out") or k.endswith("encoder.embed_positions.weight"):
            continue
        for a, b in _REPL:
            k = k.replace(a, b)
        if "conv" in k and k.endswith("weight"):
            v = v.transpose(0, 2, 1)  # torch (out, in, k) -> mlx (out, k, in)
        weights[k] = v.astype(mx.float16)
    out.mkdir(parents=True, exist_ok=True)
    mx.save_safetensors(str(out / "weights.safetensors"), weights)
    with open(out / "config.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(dict(dims, model_type="whisper"), f, indent=1)


# portable (Windows / any OS) copies: CTranslate2 Whisper + Parakeet ONNX; folder names match kalam/transcribe.py
CT2_ARABIC, CT2_OTHER, ONNX_ENGLISH = "ct2-whisper-turbo-ar-dialectal", "ct2-whisper-large-v3-turbo", "parakeet-tdt-0.6b-v2-onnx"
OTHER_SRC = "openai/whisper-large-v3-turbo"
ONNX_SRC = "istupakov/parakeet-tdt-0.6b-v2-onnx"
ONNX_FILES = ["config.json", "vocab.txt", "nemo128.onnx", "decoder_joint-model.onnx", "encoder-model.onnx",
              "encoder-model.onnx.data"]


def write_preprocessor(out: Path, n_mels: int) -> None:
    """faster-whisper reads the mel count from preprocessor_config.json (the Egyptian repo has none)"""
    with open(Path(out) / "preprocessor_config.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump({"chunk_length": 30, "feature_extractor_type": "WhisperFeatureExtractor", "feature_size": n_mels,
                   "hop_length": 160, "n_fft": 400, "n_samples": 480000, "nb_max_frames": 3000, "padding_side": "right",
                   "padding_value": 0.0, "processor_class": "WhisperProcessor", "return_attention_mask": False,
                   "sampling_rate": 16000}, f, indent=1)


def portable_missing(md: Path) -> list:
    md = Path(md)
    need = [(CT2_ARABIC, "model.bin"), (CT2_OTHER, "model.bin"), (ONNX_ENGLISH, "encoder-model.onnx")]
    return [d for d, f in need if not (md / d / f).exists()]


def convert_ct2(repo: str, out: Path) -> None:
    rev = _rev(repo)                            # refuse an unpinned repo before anything is imported or downloaded
    import shutil
    from ctranslate2.converters import TransformersConverter
    from huggingface_hub import snapshot_download
    src = Path(snapshot_download(repo, allow_patterns=["*.json", "model.safetensors", "*.txt"], revision=rev))
    TransformersConverter(str(src)).convert(str(out), quantization="float16", force=True)
    shutil.copy(src / "tokenizer.json", out / "tokenizer.json")
    with open(src / "config.json", encoding="utf-8") as f:
        n_mels = json.load(f)["num_mel_bins"]
    write_preprocessor(out, n_mels)


def main_portable(models_dir: str) -> None:
    from huggingface_hub import snapshot_download
    md = Path(models_dir)
    for d in portable_missing(md):
        repo = {CT2_ARABIC: ARABIC_SRC, CT2_OTHER: OTHER_SRC}.get(d, ONNX_SRC)
        _notice(repo)
        print("    preparing " + d + " ...", flush=True)
        if d == CT2_ARABIC:
            convert_ct2(ARABIC_SRC, md / d)
        elif d == CT2_OTHER:
            convert_ct2(OTHER_SRC, md / d)
        else:
            snapshot_download(ONNX_SRC, allow_patterns=ONNX_FILES, local_dir=str(md / d), revision=_rev(ONNX_SRC))
    _notice(ALIGNER_REPO)
    snapshot_download(ALIGNER_REPO, revision=ALIGNER_REV)   # the aligner (hf cache)
    print("    portable models ready", flush=True)


def main(models_dir: str) -> None:
    if sys.platform != "darwin":
        raise RuntimeError(_MAC_ONLY)
    from huggingface_hub import snapshot_download
    md = Path(models_dir)
    ar = md / "whisper-turbo-ar-dialectal"
    if not (ar / "weights.safetensors").exists():
        _notice(ARABIC_SRC)
        print("    converting the Egyptian-Arabic model (one time)...", flush=True)
        convert_hf_whisper(ARABIC_SRC, ar)
    for repo in OTHERS:
        _notice(repo)
        snapshot_download(repo, revision=_rev(repo))
    print("    models ready", flush=True)


def main_cli(argv=None) -> int:
    """setup_models [models_dir] [--portable | --mlx]; no folder: <engine home>/tools/kalam/models; no flag: the backend of
    this machine (MLX on a Mac with MLX installed, else portable). HF_HOME stays inside the pack unless the caller set it."""
    args = list(sys.argv[1:] if argv is None else argv)
    flags = [a for a in args if a.startswith("--")]
    rest = [a for a in args if not a.startswith("--")]
    if any(f not in ("--portable", "--mlx") for f in flags) or len(rest) > 1 or len(flags) > 1:
        print("usage: setup_models [models_dir] [--portable | --mlx]", file=sys.stderr)
        return 2
    store = Store()
    os.environ.setdefault("HF_HOME", str(store.hf_dir))
    models = rest[0] if rest else str(store.models_dir)
    portable = (flags[0] == "--portable") if flags else _platform.backend() == "portable"
    (main_portable if portable else main)(models)
    return 0


if __name__ == "__main__":
    sys.exit(main_cli())
