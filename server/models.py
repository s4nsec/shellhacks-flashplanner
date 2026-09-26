"""Request bodies for the HTTP API."""
from typing import Literal, Optional
from pydantic import BaseModel, Field


class MealRequest(BaseModel):
    name: Literal["breakfast", "lunch", "dinner"]
    time: str = Field(pattern=r"^([01]?\d|2[0-3]):[0-5]\d$")  # preferred start, 24-hour HH:MM


class Appointment(BaseModel):
    place: str
    time: str                            # 24-hour HH:MM


class StartPlace(BaseModel):
    """A place picked from the browser's autocomplete, so the server needn't look it up again."""
    place_id: str = ""
    name: str
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    utc_offset_minutes: Optional[int] = Field(default=None, ge=-14 * 60, le=14 * 60)


class TripRequest(BaseModel):
    city: str
    date: Optional[str] = None            # YYYY-MM-DD, local to the city; defaults to today there
    start_time: str = "10:00"             # 24-hour HH:MM
    end_time: str = "19:00"
    start_location: Optional[str] = None  # hotel name or address; defaults to the city center
    start_place: Optional[StartPlace] = None  # set when start_location came from autocomplete
    end_location: Optional[str] = None    # station, airport, hotel, etc.; defaults to start_location
    loves: list[str] = Field(default_factory=list)
    skips: list[str] = Field(default_factory=list)
    must_see: list[str] = Field(default_factory=list)
    appointments: list[Appointment] = Field(default_factory=list)  # fixed-time stops
    pace: Literal["relaxed", "normal", "packed"] = "normal"
    getting_around: Literal["walk", "transit", "ride"] = "transit"
    by_neighborhood: bool = True
    meals: list[MealRequest] = Field(default_factory=lambda: [
        MealRequest(name="lunch", time="12:30"),
        MealRequest(name="dinner", time="19:00"),
    ])
    auto_breaks: bool = True
    user_list: list[str] = Field(default_factory=list)  # place names pasted from a blog or list
    notes: str = ""                       # optional free text; the fields above win on conflict


class ParseRequest(BaseModel):
    message: str
    city: str = ""                        # the form's city, when the message doesn't name one


class InterpretRequest(BaseModel):
    session_id: str
    text: str


class ReplanRequest(BaseModel):
    session_id: str
    event: Literal["done", "rain", "late", "tired", "skip", "reset", "include", "lock", "unlock"]
    delay_minutes: int = 30
    place_id: Optional[str] = None        # for include | lock | unlock
