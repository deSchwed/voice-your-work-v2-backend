import uuid
from io import BytesIO
from pathlib import Path

import soundfile as sf

REF_AUDIO_DIR = Path("media/ref_audio")
PREVIEW_DIR = Path("media/preview")
MAX_DURATION_SECONDS = 30
TARGET_SAMPLE_RATE = 24000  # Qwen3-TTS native sample rate

ALLOWED_AUDIO_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/flac",
    "audio/ogg",
}


def process_ref_audio(content: bytes, content_type: str) -> str:
    """Process a ref audio file as bytes, validate, trimp, resample and save it."""
    if content_type not in ALLOWED_AUDIO_TYPES:
        raise ValueError(f"Unsupported file format: {content_type}")

    with sf.SoundFile(BytesIO(content)) as audio_file:
        duration = len(audio_file) / audio_file.samplerate
        if duration > MAX_DURATION_SECONDS:
            raise ValueError(
                f"Audio too long: {duration:.1f}s (max {MAX_DURATION_SECONDS})"
            )
        if duration < 3:
            raise ValueError(f"Audio too short: {duration:.1f}s (min 3s)")

        samples = audio_file.read(dtype="float32")
        original_rate = audio_file.samplerate

    # Convert stereo to mono by averaging channels
    if samples.ndim > 1:
        samples = samples.mean(axis=1)

    # Resample to Qwen's native rate if needed
    if original_rate != TARGET_SAMPLE_RATE:
        from math import gcd

        from scipy.signal import resample_poly

        g = gcd(TARGET_SAMPLE_RATE, original_rate)
        samples = resample_poly(samples, TARGET_SAMPLE_RATE // g, original_rate // g)

    # Normalize amplitude
    # peak = np.abs(samples).max()
    # if peak > 0:
    #     samples = samples / peak * 0.95

    filename = f"{uuid.uuid4().hex}.wav"
    filepath = REF_AUDIO_DIR / filename
    REF_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    sf.write(filepath, samples, TARGET_SAMPLE_RATE, subtype="PCM_16")

    return filename


def delete_audio_file(filename: str | None, is_preview: bool = False) -> None:
    if filename is None:
        return
    filepath = PREVIEW_DIR / filename if is_preview else REF_AUDIO_DIR / filename
    if filepath.exists():
        filepath.unlink()
