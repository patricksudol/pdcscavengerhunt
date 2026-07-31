from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from .models import GameStatus


class PasswordSet(BaseModel):
    password: str = Field(min_length=12, max_length=256)


class PasswordChange(PasswordSet):
    current_password: str = Field(min_length=1, max_length=256)


class UserCreate(BaseModel):
    email_address: EmailStr
    full_name: str = Field(min_length=1, max_length=180)
    is_admin: bool = False


class UserUpdate(BaseModel):
    email_address: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=180)
    is_admin: bool | None = None
    active: bool | None = None


class GameCreate(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=5000)
    instructions: str | None = Field(default=None, max_length=5000)
    closing_message: str | None = Field(default=None, max_length=5000)
    allow_answer_reveal: bool = False


class GameUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=5000)
    instructions: str | None = Field(default=None, max_length=5000)
    closing_message: str | None = Field(default=None, max_length=5000)
    allow_answer_reveal: bool = False
    status: GameStatus | None = None


class ClueCreate(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    content: str = Field(min_length=1, max_length=10000)
    code: str = Field(min_length=2, max_length=120)


class ClueUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    content: str | None = Field(default=None, min_length=1, max_length=10000)
    code: str | None = Field(default=None, min_length=2, max_length=120)


class ClueReorder(BaseModel):
    clue_ids: list[str] = Field(min_length=1)


class HintCreate(BaseModel):
    text: str | None = Field(default=None, max_length=10000)


class HintUpdate(BaseModel):
    text: str | None = Field(default=None, max_length=10000)


class HintReorder(BaseModel):
    hint_ids: list[str] = Field(min_length=1)


class CodeSubmission(BaseModel):
    code: str = Field(min_length=1, max_length=120)


class MembershipUpdate(BaseModel):
    user_ids: list[str]


class ProgressAdjustment(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    clue_id: UUID
