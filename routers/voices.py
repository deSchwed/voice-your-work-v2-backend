from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

import models
from auth import CurrentUser
from config import settings
from database import get_db
from models import Role, Tier
from schemas.voices import (
    VoiceCloneCreate,
    VoiceCloneGenerate,
    VoiceCloneGenerateResponse,
    VoiceCloneResponse,
    VoiceCloneResponsePrivate,
    VoiceDesign,
    VoiceDesignResponse,
)
from utils.sound_utils import delete_audio_file, process_ref_audio
from voice_engine.queue import voice_queue

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
        .where(models.VoiceClone.visibility)
        .where(models.VoiceClone.is_ready)
        .options(selectinload(models.VoiceClone.owner))
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
    await db.refresh(new_voice_clone, attribute_names=["owner"])
    return new_voice_clone


@router.patch("/{voice_id}", response_model=VoiceCloneResponsePrivate)
async def upload_ref_audio(
    voice_id: int,
    file: UploadFile,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Uploads reference audio file for selected voice clone and generates preview audio."""
    result = await db.execute(
        select(models.VoiceClone)
        .where(models.VoiceClone.id == voice_id)
        .options(selectinload(models.VoiceClone.owner))
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

    await voice_queue.enqueue_preview(
        voice_id=voice.id,
        ref_text=voice.ref_text,
        ref_audio=voice.ref_audio_path,
        name=voice.name,
    )

    return voice


@router.delete("/{voice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_voice_clone(
    voice_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Deletes selected Voice Clone."""
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
    prompt: VoiceCloneGenerate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Queue a TTS generation request for the given voice."""
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
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Voice not ready yet",
        )
    if not voice.visibility and voice.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to use this voice",
        )
    generation = models.VoiceGenerate(
        user_id=current_user.id,
        voice_id=voice_id,
        prompt_text=prompt.prompt_text,
        language=prompt.language,
    )
    db.add(generation)
    await db.commit()
    await db.refresh(generation)

    tier = Tier.basic if current_user.role == Role.basic else Tier.premium
    await voice_queue.enqueue_generate(
        generation_id=generation.id,
        text=prompt.prompt_text,
        language=prompt.language,
        ref_audio=voice.ref_audio_path,
        ref_text=voice.ref_text,
        tier=tier,
    )

    result = await db.execute(
        select(models.VoiceGenerate)
        .where(models.VoiceGenerate.id == generation.id)
        .options(selectinload(models.VoiceGenerate.queue_job))
    )
    return result.scalars().first()


@router.get(
    "/generate/{generation_id}",
    response_model=VoiceCloneGenerateResponse,
    status_code=status.HTTP_200_OK,
)
async def get_generation(
    generation_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Poll the status of a queued generation request."""
    result = await db.execute(
        select(models.VoiceGenerate)
        .where(models.VoiceGenerate.id == generation_id)
        .options(selectinload(models.VoiceGenerate.queue_job))
    )
    generation = result.scalars().first()
    if not generation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation not found",
        )
    if generation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this generation",
        )

    return generation


@router.post(
    "/design",
    response_model=VoiceDesignResponse,
    status_code=status.HTTP_201_CREATED,
)
async def design(
    design_prompt: VoiceDesign,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Design a custom voice"""
    if current_user.role == Role.basic:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot use voice design feature as a basic user",
        )
    new_voice_design = models.VoiceDesign(
        user_id=current_user.id,
        name=design_prompt.name,
        prompt_text=design_prompt.prompt_text,
        instruct=design_prompt.instruct,
        language=design_prompt.language,
    )

    db.add(new_voice_design)
    await db.commit()
    await db.refresh(new_voice_design)

    await voice_queue.enqueue_design(
        design_id=new_voice_design.id,
        name=design_prompt.name,
        text=design_prompt.prompt_text,
        instruct=design_prompt.instruct,
        language=design_prompt.language,
    )

    result = await db.execute(
        select(models.VoiceDesign)
        .where(models.VoiceDesign.id == new_voice_design.id)
        .options(selectinload(models.VoiceDesign.queue_job))
    )
    return result.scalars().first()
