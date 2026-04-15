from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    image_file: Mapped[str | None] = mapped_column(
        String(200), nullable=True, default=None
    )

    reset_tokens: Mapped[list[PasswordResetToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    voice_clones: Mapped[list[VoiceClone]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    voice_generations: Mapped[list[VoiceGenerate]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )

    @property
    def image_path(self) -> str:
        if self.image_file:
            return f"/media/profile_pics/{self.image_file}"
        return "/static/profile_pics/default.jpg"


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    user: Mapped[User] = relationship(back_populates="reset_tokens")


class VoiceClone(Base):
    __tablename__ = "voice_clones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(
        Text, nullable=False, default="A custom Voice."
    )
    visibility: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    times_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    is_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    ref_text: Mapped[str] = mapped_column(Text, nullable=False)
    ref_audio_file: Mapped[str | None] = mapped_column(
        String(200), nullable=True, default=None
    )
    preview_audio_file: Mapped[str | None] = mapped_column(
        String(200), nullable=True, default=None
    )

    owner: Mapped[User] = relationship(back_populates="voice_clones")
    voice_generations: Mapped[list[VoiceGenerate]] = relationship(
        back_populates="voice"
    )

    @property
    def ref_audio_path(self) -> str:
        if self.ref_audio_file:
            return f"media/ref_audio/{self.ref_audio_file}"
        return ""

    @property
    def preview_audio_path(self) -> str:
        if self.preview_audio_file:
            return f"media/preview/{self.preview_audio_file}"
        return ""


class VoiceGenerate(Base):
    __tablename__ = "voice_generations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    voice_id: Mapped[int] = mapped_column(ForeignKey("voice_clones.id"), nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="English")
    is_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    audio_file: Mapped[str | None] = mapped_column(
        String(200), nullable=True, default=None
    )

    owner: Mapped[User] = relationship(back_populates="voice_generations")
    voice: Mapped[VoiceClone] = relationship(back_populates="voice_generations")
    queue_job: Mapped[QueueJob | None] = relationship(
        "QueueJob",
        foreign_keys="[QueueJob.voice_generation_id]",
        back_populates="voice_generation",
        uselist=False,
    )

    @property
    def audio_path(self) -> str:
        if self.audio_file:
            return f"media/generate/{self.audio_file}"
        return ""


class QueueJob(Base):
    __tablename__ = "queue_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    voice_generation_id: Mapped[int | None] = mapped_column(
        ForeignKey("voice_generations.id"), nullable=True, default=None
    )
    voice_clone_id: Mapped[int | None] = mapped_column(
        ForeignKey("voice_clones.id"), nullable=True, default=None
    )

    voice_generation: Mapped[VoiceGenerate | None] = relationship(
        "VoiceGenerate",
        foreign_keys=[voice_generation_id],
        back_populates="queue_job",
    )
    voice_clone: Mapped[VoiceClone | None] = relationship(
        "VoiceClone",
        foreign_keys=[voice_clone_id],
    )
