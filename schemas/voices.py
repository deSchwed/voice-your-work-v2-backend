from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .users import UserPublic

SUPPORTED_LANGUAGES = Literal[
    "Chinese",
    "English",
    "Japanese",
    "Korean",
    "German",
    "French",
    "Russian",
    "Portuguese",
    "Spanish",
    "Italian",
]


class VoiceCloneBase(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    description: str | None = Field(default=None)
    visibility: bool


class VoiceCloneCreate(VoiceCloneBase):
    ref_text: str = Field(min_length=1)


class VoiceCloneUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None)
    visibility: bool


class VoiceCloneResponse(VoiceCloneBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: datetime
    owner: UserPublic


class VoiceCloneResponsePrivate(VoiceCloneResponse):
    ref_text: str = Field(min_length=1)
    ref_audio_file: str | None
    ref_audio_path: str
    is_ready: bool


class VoiceCloneGenerate(BaseModel):
    prompt_text: str = Field(min_length=1, max_length=500)
    language: SUPPORTED_LANGUAGES


class QueueJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    error_message: str | None
    created_at: datetime


class VoiceCloneGenerateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    voice_id: int
    prompt_text: str
    language: str
    is_generated: bool
    audio_path: str
    created_at: datetime
    queue_job: QueueJobResponse | None
