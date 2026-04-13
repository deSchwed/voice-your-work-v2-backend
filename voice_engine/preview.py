import io
import uuid
from pathlib import Path

import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

PREVIEW_DIR = Path("media/preview")


def generate_preview(ref_text: str, ref_audio: str, name: str) -> str:
    model = Qwen3TTSModel.from_pretrained(
        "models/Qwen3-TTS-12Hz-0.6B-Base",
        device_map="cuda:0",
        dtype=torch.bfloat16,
        attn_implementation="flash_attention_2",
    )

    preview_text = (
        f"Hi! My name is {name}, and this is what I sound like. Nice to meet you!"
    )

    filename = f"{uuid.uuid4().hex}.wav"
    filepath = PREVIEW_DIR / filename
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

    # Generate and save the preview audio
    wavs, sr = model.generate_voice_clone(
        text=preview_text,
        language="English",
        ref_audio=ref_audio,
        ref_text=ref_text,
    )
    sf.write(filepath, wavs[0], sr)

    return filename
