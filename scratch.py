import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

model = Qwen3TTSModel.from_pretrained(
    "models/Qwen3-TTS-12Hz-0.6B-CustomVoice",
    device_map="cuda:0",
    dtype=torch.bfloat16,
    attn_implementation="flash_attention_2",
)

# single inference
wavs, sr = model.generate_custom_voice(
    text="H-hey! You dropped your... uh... calculus notebook? I mean, I think it's yours? Maybe?",
    language="English",  # Pass `Auto` (or omit) for auto language adaptive; if the target language is known, set it explicitly.
    speaker="Ryan",
    instruct="Male, 17 years old, tenor range, gaining confidence - deeper breath support now, though vowels still tighten when nervous",  # Omit if not needed.
)
sf.write("output_custom_voice.wav", wavs[0], sr)
