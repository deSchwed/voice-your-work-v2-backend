import io
import os
import uuid
from pathlib import Path

import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

GENERATE_DIR = Path("media/generate")


class QwenTTSEngine:
    def __init__(self):
        self.clone_model = None
        self.design_model = None

    def load(self):
        self.clone_model = Qwen3TTSModel.from_pretrained(
            "models/Qwen3-TTS-12Hz-0.6B-Base",
            device_map="cuda:0",
            dtype=torch.bfloat16,
            attn_implementation="flash_attention_2",
        )
        self.design_model = Qwen3TTSModel.from_pretrained(
            "models/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
            device_map="cuda:0",
            dtype=torch.bfloat16,
            attn_implementation="flash_attention_2",
        )
        GENERATE_DIR.mkdir(parents=True, exist_ok=True)

    def generate(self, text: str, ref_text: str, ref_audio: str, language: str) -> str:

        wavs, sr = self.clone_model.generate_voice_clone(  # type: ignore
            text=text,
            language=language,
            ref_audio=ref_audio,
            ref_text=ref_text,
        )
        filename = f"{uuid.uuid4().hex}.wav"
        filepath = GENERATE_DIR / filename
        sf.write(filepath, wavs[0], sr)
        return str(filepath)


tts_engine = QwenTTSEngine()
