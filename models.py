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
        back_populates="user", cascade="all, delete-orphan"
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

    user: Mapped[User] = relationship(back_populates="voice_clones")

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
