from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email_or_username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
