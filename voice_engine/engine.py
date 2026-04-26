import uuid
from pathlib import Path

import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

from models import Tier

GENERATE_DIR = Path("media/generate")
DESIGN_DIR = Path("media/design")
PREVIEW_DIR = Path("media/preview")


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
        self.clone_model_premium = Qwen3TTSModel.from_pretrained(
            "models/Qwen3-TTS-12Hz-1.7B-Base",
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
        DESIGN_DIR.mkdir(parents=True, exist_ok=True)
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

    def generate(
        self, text: str, ref_text: str, ref_audio: str, language: str, tier: Tier
    ) -> str:
        if tier == "premium":
            wavs, sr = self.clone_model_premium.generate_voice_clone(  # type: ignore
                text=text,
                language=language,
                ref_audio=ref_audio,
                ref_text=ref_text,
            )
        else:
            wavs, sr = self.clone_model.generate_voice_clone(  # type: ignore
                text=text,
                language=language,
                ref_audio=ref_audio,
                ref_text=ref_text,
            )
        filename = f"{uuid.uuid4().hex}.wav"
        filepath = GENERATE_DIR / filename
        sf.write(filepath, wavs[0], sr)
        return filename

    def design(self, text: str, instruct: str, language: str) -> str:
        wavs, sr = self.design_model.generate_voice_design(  # type: ignore
            text=text,
            instruct=instruct,
            language=language,
        )
        filename = f"{uuid.uuid4().hex}.wav"
        filepath = DESIGN_DIR / filename
        sf.write(filepath, wavs[0], sr)
        return filename

    def generate_preview(self, ref_text: str, ref_audio: str, name: str) -> str:
        preview_text = (
            f"Hi! My name is {name}, and this is what I sound like. Nice to meet you!"
        )
        # Use 1.7B model for previews, so they are of higher quality
        wavs, sr = self.clone_model_premium.generate_voice_clone(  # type: ignore
            text=preview_text,
            language="English",
            ref_audio=ref_audio,
            ref_text=ref_text,
        )
        filename = f"{uuid.uuid4().hex}.wav"
        filepath = PREVIEW_DIR / filename
        sf.write(filepath, wavs[0], sr)
        return filename


tts_engine = QwenTTSEngine()
