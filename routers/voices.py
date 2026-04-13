from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

import models
from auth import CurrentUser
from config import settings
from database import get_db
from schemas.voices import (
    VoiceCloneCreate,
    VoiceCloneGenerate,
    VoiceCloneGenerateResponse,
    VoiceCloneResponse,
    VoiceCloneResponsePrivate,
    VoiceCloneUpdate,
)
from utils.sound_utils import delete_audio_file, process_ref_audio
from voice_engine.engine import tts_engine
from voice_engine.preview import generate_preview

router = APIRouter()


@router.get(
    "",
    response_model=list[VoiceCloneResponse],
    status_code=status.HTTP_200_OK,
)
async def get_voices_all(
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Return a list of all public voices that are set to ready."""
    result = await db.execute(
        select(models.VoiceClone)
        .where(models.VoiceClone.visibility == True)
        .where(models.VoiceClone.is_ready == True)
        .options(selectinload(models.VoiceClone.user))
        .order_by(models.VoiceClone.times_used.desc())
    )
    voices = result.scalars().all()
    return voices


@router.post(
    "",
    response_model=VoiceCloneResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_clone(
    voice_clone: VoiceCloneCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    new_voice_clone = models.VoiceClone(
        user_id=current_user.id,
        name=voice_clone.name,
        description=voice_clone.description,
        visibility=voice_clone.visibility,
        ref_text=voice_clone.ref_text,
    )
    db.add(new_voice_clone)
    await db.commit()
    await db.refresh(new_voice_clone, attribute_names=["user"])
    return new_voice_clone


@router.patch("/{voice_id}", response_model=VoiceCloneResponsePrivate)
async def upload_ref_audio(
    voice_id: int,
    file: UploadFile,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Uploads reference audio file for selected voice clone to ready it for usage by generating preview audio."""
    result = await db.execute(
        select(models.VoiceClone).where(models.VoiceClone.id == voice_id)
    )
    voice = result.scalars().first()
    if not voice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voice clone not found",
        )

    if voice.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this voice clone",
        )

    if not file.content_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Could not determine file type. Please upload a valid audio file",
        )

    content = await file.read()

    if len(content) > settings.max_upload_size_wav_file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size is {settings.max_upload_size_wav_file // (1024 * 1024)}MB",
        )

    try:
        new_filename = await run_in_threadpool(
            process_ref_audio, content, file.content_type
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(err),
        )

    old_filename = voice.ref_audio_file
    old_preview = voice.preview_audio_file

    voice.ref_audio_file = new_filename

    await db.commit()
    await db.refresh(voice)

    if old_filename:
        delete_audio_file(old_filename)
    if old_preview:
        delete_audio_file(old_preview, is_preview=True)

    # Generate preview audio
    preview_filename = generate_preview(
        voice.ref_text, voice.ref_audio_path, voice.name
    )

    voice.preview_audio_file = preview_filename
    voice.is_ready = True

    await db.commit()
    await db.refresh(voice)

    return voice


@router.delete("/{voice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_voice_clone(
    voice_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Deletes selected Voice Clone"""
    result = await db.execute(
        select(models.VoiceClone).where(models.VoiceClone.id == voice_id)
    )
    voice = result.scalars().first()
    if not voice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voice clone not found",
        )

    if voice.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this voice clone",
        )

    old_filename = voice.ref_audio_file
    old_preview = voice.preview_audio_file

    await db.delete(voice)
    await db.commit()

    if old_filename:
        delete_audio_file(old_filename)
    if old_preview:
        delete_audio_file(old_preview, is_preview=True)


@router.post(
    "/generate/{voice_id}",
    response_model=VoiceCloneGenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_single(
    voice_id: int,
    generate_prompt: VoiceCloneGenerate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Generate TTS file with the provided text,"""
    result = await db.execute(
        select(models.VoiceClone).where(models.VoiceClone.id == voice_id)
    )
    voice = result.scalars().first()

    if not voice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voice not found",
        )
    if not voice.is_ready:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Voice not ready yet"
        )
    if not voice.visibility and voice.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to use this voice",
        )

    tts_engine.load()

    # TODO: check language
    try:
        filepath = tts_engine.generate(
            text=generate_prompt.prompt_text,
            language=generate_prompt.language,
            ref_audio=voice.ref_audio_path,
            ref_text=voice.ref_text,
        )
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(err)
        ) from err

    return {"filepath": filepath}
