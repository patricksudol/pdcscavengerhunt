from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class GameStatus(enum.StrEnum):
    draft = "draft"
    open = "open"
    closed = "closed"


class MediaType(enum.StrEnum):
    photo = "photo"
    video = "video"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email_address: Mapped[str] = mapped_column(String(320))
    normalized_email_address: Mapped[str] = mapped_column(
        String(320), unique=True, index=True
    )
    full_name: Mapped[str] = mapped_column(String(180))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    session_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list[GamePlayer]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="GamePlayer.user_id",
    )


class PasswordSetupToken(Base):
    __tablename__ = "password_setup_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Game(Base):
    __tablename__ = "games"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text)
    instructions: Mapped[str | None] = mapped_column(Text)
    closing_message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[GameStatus] = mapped_column(
        Enum(GameStatus, native_enum=False), default=GameStatus.draft, index=True
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    memberships: Mapped[list[GamePlayer]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )
    clues: Mapped[list[Clue]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
        order_by="Clue.position",
    )


class GamePlayer(Base):
    __tablename__ = "game_players"
    __table_args__ = (
        UniqueConstraint("game_id", "user_id", name="uq_game_players_game_user"),
        Index("ix_game_players_user_game", "user_id", "game_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    game_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    assigned_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    game: Mapped[Game] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships", foreign_keys=[user_id])
    completions: Mapped[list[ClueCompletion]] = relationship(
        back_populates="membership", cascade="all, delete-orphan"
    )


class Clue(Base):
    __tablename__ = "clues"
    __table_args__ = (
        UniqueConstraint("game_id", "position", name="uq_clues_game_position"),
        UniqueConstraint("code_fingerprint", name="uq_clues_code_fingerprint"),
        Index("ix_clues_game_position", "game_id", "position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    game_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(180))
    content: Mapped[str] = mapped_column(Text)
    code: Mapped[str | None] = mapped_column(String(120))
    code_fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    game: Mapped[Game] = relationship(back_populates="clues")
    completions: Mapped[list[ClueCompletion]] = relationship(
        back_populates="clue", cascade="all, delete-orphan"
    )
    media: Mapped[list[ClueMedia]] = relationship(
        back_populates="clue", cascade="all, delete-orphan"
    )


class ClueMedia(Base):
    __tablename__ = "clue_media"
    __table_args__ = (
        UniqueConstraint("clue_id", "media_type", name="uq_clue_media_clue_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    clue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clues.id", ondelete="CASCADE"), index=True
    )
    media_type: Mapped[MediaType] = mapped_column(
        Enum(MediaType, native_enum=False), index=True
    )
    provider_key: Mapped[str] = mapped_column(String(255), unique=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(80))
    size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(20), default="ready", server_default="ready", index=True
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    clue: Mapped[Clue] = relationship(back_populates="media")


class ClueCompletion(Base):
    __tablename__ = "clue_completions"
    __table_args__ = (
        UniqueConstraint(
            "game_player_id", "clue_id", name="uq_clue_completions_membership_clue"
        ),
        Index("ix_clue_completions_membership_time", "game_player_id", "completed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    game_player_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("game_players.id", ondelete="CASCADE"), index=True
    )
    clue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clues.id", ondelete="CASCADE"), index=True
    )
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    membership: Mapped[GamePlayer] = relationship(back_populates="completions")
    clue: Mapped[Clue] = relationship(back_populates="completions")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_created_at", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(String(500))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    request_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
