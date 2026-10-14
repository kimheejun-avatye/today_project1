from typing import Literal
from pydantic import BaseModel, Field, EmailStr


class EmailRequest(BaseModel):
    email: EmailStr
    purpose: str = "SIGNUP"
    captcha_token: str = ""


class CaptchaRequest(BaseModel):
    previous_id: str = Field(default="", max_length=36)


class CaptchaAnswer(BaseModel):
    id: str = Field(max_length=36)
    answer: str = Field(min_length=1, max_length=20)


class Proof(BaseModel):
    id: str
    flow: str


class CodeInput(Proof):
    code: str = Field(min_length=1, max_length=20)


class Signup(Proof):
    password: str = Field(min_length=12, max_length=128)
    name: str = Field(min_length=1, max_length=80)
    nickname: str = Field(min_length=1, max_length=40)
    privacy_consent: bool = False
    privacy_consent_version: str = ""


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class Reset(Proof):
    password: str = Field(min_length=12, max_length=128)


class GoogleInput(BaseModel):
    credential: str = Field(max_length=10000)
    intent: Literal["login", "signup", "link"] = "login"
    name: str = Field(default="", max_length=80)
    nickname: str = Field(default="", max_length=40)
    captcha_token: str = ""
    link_password: str = ""
    consent: bool = False
    privacy_consent: bool = False
    privacy_consent_version: str = ""
