from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models import UserRole


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: str
    role: UserRole
    student_code: str | None
    is_active: bool
