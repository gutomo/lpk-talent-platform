from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.enums import Locale, UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    org_id: int
    name: str
    email: str
    role: UserRole
    locale: Locale
