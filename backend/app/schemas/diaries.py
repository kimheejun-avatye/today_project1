from pydantic import BaseModel, Field


class DiaryInput(BaseModel):
    content: str = Field(max_length=100000)
    emotion: str = Field(default="", max_length=40)
    status: str = "DRAFT"
    shared: bool = False
    version: int


class CommentInput(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
