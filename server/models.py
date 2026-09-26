"""Request bodies for the HTTP API."""
from typing import Literal, Optional
from pydantic import BaseModel, Field


class MealRequest(BaseModel):
    name: Literal["breakfast", "lunch", "dinner"]
    time: str = Field(pattern=r"^([01]?\d|2[0-3]):[0-5]\d$")  # preferred start, 24-hour HH:MM


class TripRequest(BaseModel):
    city: str
    date: Optional[str] = None            # YYYY-MM-DD, local to the city; defaults to today there
    start_time: str = "10:00"             # 24-hour HH:MM
    end_time: str = "19:00"
    start_location: Optional[str] = None  # hotel name or address; defaults to the city center
    end_location: Optional[str] = None    # station, airport, hotel, etc.; defaults to start_location
    loves: list[str] = Field(default_factory=list)
    skips: list[str] = Field(default_factory=list)
    must_see: list[str] = Field(default_factory=list)
    pace: Literal["relaxed", "normal", "packed"] = "normal"
    getting_around: Literal["walk", "transit", "ride"] = "transit"
    by_neighborhood: bool = True
    meals: list[MealRequest] = Field(default_factory=lambda: [
        MealRequest(name="lunch", time="12:30"),
        MealRequest(name="dinner", time="19:00"),
    ])
    auto_breaks: bool = True
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
