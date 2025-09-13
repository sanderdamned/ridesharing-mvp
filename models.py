from pydantic import BaseModel, conlist
from typing import List

class Coordinates(BaseModel):
    lat: float
    lon: float

class Ride(BaseModel):
    user_id: str
    origin: str
    destination: str
    departure: str
    origin_coords: conlist(float, min_items=2, max_items=2)
    dest_coords: conlist(float, min_items=2, max_items=2)
    max_extra_km: float = 2.0
    max_extra_min: int = 15

class PassengerRequest(BaseModel):
    user_id: str
    origin: str
    destination: str
    departure: str
    origin_coords: conlist(float, min_items=2, max_items=2)
    dest_coords: conlist(float, min_items=2, max_items=2)

class Match(BaseModel):
    ride_id: str
    extra_distance: float
    extra_time: float
