from datetime import date
from pydantic import BaseModel, Field


class TaskInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    day: date
    recurring: bool = False


class ToggleTask(BaseModel):
    id: int = 0
    recurring_id: int = 0
    day: date
    completed: bool
