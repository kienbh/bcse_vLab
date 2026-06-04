from pydantic import BaseModel, EmailStr, Field

from app.models import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


class AdminCreateUserRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=255)
    role: UserRole = UserRole.STUDENT
    student_code: str | None = Field(None, max_length=64)
    external: bool = Field(
        False,
        description="External team (e.g. ESAS): scoped to devices granted via SpecialAccess.",
    )
    initial_password: str | None = Field(
        None, min_length=8, max_length=128,
        description="Optional override; if omitted, DEFAULT_PASSWORD is used (must change on first login)",
    )


class AdminResetPasswordRequest(BaseModel):
    new_password: str | None = Field(
        None, min_length=8, max_length=128,
        description="Optional. If omitted, resets to DEFAULT_PASSWORD.",
    )
