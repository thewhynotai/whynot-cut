"""Download / convert the models Kalam uses. usage: setup_models.py <models_dir>  (HF_HOME decides the HF cache)"""
import json
import sys
from pathlib import Path

ARABIC_SRC = "oddadmix/whisper-large-v3-turbo-arabic-dialectal"
OTHERS = ["mlx-community/whisper-large-v3-turbo", "mlx-community/parakeet-tdt-0.6b-v2",
          "MahmoudAshraf/mms-300m-1130-forced-aligner"]

# Hugging Face Whisper names -> mlx_whisper names
_REPL = [("model.", ""), (".layers.", ".blocks."), (".self_attn_layer_norm", ".attn_ln"),
         (".encoder_attn_layer_norm", ".cross_attn_ln"), (".self_attn.", ".attn."), (".encoder_attn.", ".cross_attn."),
         (".final_layer_norm", ".mlp_ln"), (".q_proj", ".query"), (".k_proj", ".key"), (".v_proj", ".value"),
         (".out_proj", ".out"), (".fc1", ".mlp1"), (".fc2", ".mlp2"),
         ("decoder.embed_positions.weight", "decoder.positional_embedding"),
         ("decoder.embed_tokens", "decoder.token_embedding"), ("encoder.layer_norm", "encoder.ln_post"),
         ("decoder.layer_norm", "decoder.ln")]


def convert_hf_whisper(repo: str, out: Path) -> None:
    import mlx.core as mx
    from huggingface_hub import snapshot_download
    src = Path(snapshot_download(repo, allow_patterns=["*.json", "model.safetensors"]))
    cfg = json.load(open(src / "config.json"))
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
    json.dump(dict(dims, model_type="whisper"), open(out / "config.json", "w"), indent=1)


# portable (Windows / any OS) copies: CTranslate2 Whisper + Parakeet ONNX; folder names match kalam/transcribe.py
CT2_ARABIC, CT2_OTHER, ONNX_ENGLISH = "ct2-whisper-turbo-ar-dialectal", "ct2-whisper-large-v3-turbo", "parakeet-tdt-0.6b-v2-onnx"
OTHER_SRC = "openai/whisper-large-v3-turbo"
ONNX_SRC = "istupakov/parakeet-tdt-0.6b-v2-onnx"
ONNX_FILES = ["config.json", "vocab.txt", "nemo128.onnx", "decoder_joint-model.onnx", "encoder-model.onnx",
              "encoder-model.onnx.data"]


def write_preprocessor(out: Path, n_mels: int) -> None:
    """faster-whisper reads the mel count from preprocessor_config.json (the Egyptian repo has none)"""
    json.dump({"chunk_length": 30, "feature_extractor_type": "WhisperFeatureExtractor", "feature_size": n_mels,
               "hop_length": 160, "n_fft": 400, "n_samples": 480000, "nb_max_frames": 3000, "padding_side": "right",
               "padding_value": 0.0, "processor_class": "WhisperProcessor", "return_attention_mask": False,
               "sampling_rate": 16000}, open(Path(out) / "preprocessor_config.json", "w"), indent=1)


def portable_missing(md: Path) -> list:
    md = Path(md)
    need = [(CT2_ARABIC, "model.bin"), (CT2_OTHER, "model.bin"), (ONNX_ENGLISH, "encoder-model.onnx")]
    return [d for d, f in need if not (md / d / f).exists()]


def convert_ct2(repo: str, out: Path) -> None:
    import shutil
    from ctranslate2.converters import TransformersConverter
    from huggingface_hub import snapshot_download
    src = Path(snapshot_download(repo, allow_patterns=["*.json", "model.safetensors", "*.txt"]))
    TransformersConverter(str(src)).convert(str(out), quantization="float16", force=True)
    shutil.copy(src / "tokenizer.json", out / "tokenizer.json")
    write_preprocessor(out, json.load(open(src / "config.json"))["num_mel_bins"])


def main_portable(models_dir: str) -> None:
    from huggingface_hub import snapshot_download
    md = Path(models_dir)
    for d in portable_missing(md):
        print("    preparing " + d + " ...", flush=True)
        if d == CT2_ARABIC:
            convert_ct2(ARABIC_SRC, md / d)
        elif d == CT2_OTHER:
            convert_ct2(OTHER_SRC, md / d)
        else:
            snapshot_download(ONNX_SRC, allow_patterns=ONNX_FILES, local_dir=str(md / d))
    snapshot_download(OTHERS[-1])   # MMS aligner (hf cache)
    print("    portable models ready", flush=True)


def main(models_dir: str) -> None:
    from huggingface_hub import snapshot_download
    md = Path(models_dir)
    ar = md / "whisper-turbo-ar-dialectal"
    if not (ar / "weights.safetensors").exists():
        print("    converting the Egyptian-Arabic model (one time)...", flush=True)
        convert_hf_whisper(ARABIC_SRC, ar)
    for repo in OTHERS:
        snapshot_download(repo)
    print("    models ready", flush=True)


if __name__ == "__main__":
    if "--portable" in sys.argv:
        main_portable(sys.argv[1])
    else:
        main(sys.argv[1])
