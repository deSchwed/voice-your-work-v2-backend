from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .users import UserPublic


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
    user: UserPublic


class VoiceCloneResponsePrivate(VoiceCloneResponse):
    ref_text: str = Field(min_length=1)
    ref_audio_file: str | None
    ref_audio_path: str | None
    is_ready: bool


class VoiceCloneGenerate(BaseModel):
    prompt_text: str = Field(min_length=1, max_length=500)
    language: str = Field(min_length=1)


class VoiceCloneGenerateResponse(BaseModel):
    filepath: str = Field(min_length=1)
