"""Request bodies for the HTTP API."""
from typing import Optional
from pydantic import BaseModel, Field


class AppointmentRequest(BaseModel):
    place: str
    time: str                              # 24-hour HH:MM
    duration_minutes: int = 60


class TripRequest(BaseModel):
    city: str
    date: Optional[str] = None            # YYYY-MM-DD, local to the city; defaults to today there
    start_time: str = "10:00"             # 24-hour HH:MM
    end_time: str = "19:00"
    start_location: Optional[str] = None  # hotel name or address; defaults to the city center
    end_location: Optional[str] = None    # train station, airport, venue; defaults to start_location
    loves: list[str] = Field(default_factory=list)
    skips: list[str] = Field(default_factory=list)
    must_see: list[str] = Field(default_factory=list)
    appointments: list[AppointmentRequest] = Field(default_factory=list)
    pace: str = "normal"                  # relaxed | normal | packed
    getting_around: str = "transit"       # walk | transit | ride
    by_neighborhood: bool = True
    user_list: list[str] = Field(default_factory=list)  # place names pasted from a blog or list


class ParseRequest(BaseModel):
    message: str


class InterpretRequest(BaseModel):
    session_id: str
    text: str


class ReplanRequest(BaseModel):
    session_id: str
    event: str                            # done | rain | late | tired | skip | reset
    delay_minutes: int = 40
