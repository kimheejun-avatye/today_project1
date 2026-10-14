from pydantic import BaseModel, Field


class Profile(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    nickname: str = Field(min_length=1, max_length=40)
