"""Request bodies for the HTTP API."""
from typing import Literal, Optional
from pydantic import BaseModel, Field


class TripRequest(BaseModel):
    city: str
    date: Optional[str] = None            # YYYY-MM-DD, local to the city; defaults to today there
    start_time: str = "10:00"             # 24-hour HH:MM
    end_time: str = "19:00"
    start_location: Optional[str] = None  # hotel name or address; defaults to the city center
    loves: list[str] = Field(default_factory=list)
    skips: list[str] = Field(default_factory=list)
    must_see: list[str] = Field(default_factory=list)
    pace: Literal["relaxed", "normal", "packed"] = "normal"
    getting_around: Literal["walk", "transit", "ride"] = "transit"
    by_neighborhood: bool = True
    user_list: list[str] = Field(default_factory=list)  # place names pasted from a blog or list


class ParseRequest(BaseModel):
    message: str


class InterpretRequest(BaseModel):
    session_id: str
    text: str


class ReplanRequest(BaseModel):
    session_id: str
    event: Literal["done", "rain", "late", "tired", "skip", "reset"]
    delay_minutes: int = 30
