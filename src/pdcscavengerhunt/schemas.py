from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from .models import GameStatus


class PasswordSet(BaseModel):
    password: str = Field(min_length=12, max_length=256)


class PasswordChange(PasswordSet):
    current_password: str = Field(min_length=1, max_length=256)


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    display_name: str = Field(min_length=1, max_length=180)
    is_admin: bool = False

    @field_validator("username")
    @classmethod
    def valid_username(cls, value: str) -> str:
        value = value.strip()
        if not all(character.isalnum() or character in "._-" for character in value):
            raise ValueError("Use only letters, numbers, periods, underscores, or hyphens")
        return value


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=180)
    is_admin: bool | None = None
    active: bool | None = None


class GameCreate(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=5000)
    instructions: str | None = Field(default=None, max_length=5000)


class GameUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=5000)
    instructions: str | None = Field(default=None, max_length=5000)
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


class CodeSubmission(BaseModel):
    code: str = Field(min_length=1, max_length=120)


class MembershipUpdate(BaseModel):
    user_ids: list[str]

