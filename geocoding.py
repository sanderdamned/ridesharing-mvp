import requests
from functools import lru_cache
from config import ORS_API_KEY
import time as pytime

@lru_cache(maxsize=500)
def geocode_postcode(postcode: str, retries=2):
    """Return [lat, lon] list or None"""
    if not ORS_API_KEY:
        return None
    url = "https://api.openrouteservice.org/geocode/search"
    params = {"api_key": ORS_API_KEY, "text": postcode, "boundary.country": "NL"}
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, timeout=5)
            r.raise_for_status()
            coords = r.json()["features"][0]["geometry"]["coordinates"]
            return [float(coords[1]), float(coords[0])]  # lat, lon
        except Exception:
            if attempt < retries:
                pytime.sleep(1)
                continue
            return None

def route_distance_time(start, end):
    """Return (distance_km, duration_min) between two [lat, lon] coords"""
    if not ORS_API_KEY:
        return None, None
    try:
        url = "https://api.openrouteservice.org/v2/directions/driving-car"
        headers = {"Authorization": ORS_API_KEY}
        body = {"coordinates": [[start[1], start[0]], [end[1], end[0]]]}
        r = requests.post(url, json=body, headers=headers, timeout=5)
        r.raise_for_status()
        data = r.json()
        dist = data["routes"][0]["summary"]["distance"] / 1000
        dur = data["routes"][0]["summary"]["duration"] / 60
        return dist, dur
    except Exception:
        return None, None
