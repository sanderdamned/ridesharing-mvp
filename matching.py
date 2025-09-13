from geocoding import route_distance_time
from models import Match

def find_matches(passenger, rides):
    matches = []
    for ride in rides:
        base_dist, base_time = route_distance_time(ride["origin_coords"], ride["dest_coords"])
        if base_dist is None: continue
        detour1, _ = route_distance_time(ride["origin_coords"], passenger["origin_coords"])
        detour2, _ = route_distance_time(passenger["origin_coords"], ride["dest_coords"])
        if detour1 is None or detour2 is None: continue
        extra_dist = detour1 + detour2 - base_dist
        extra_time = 0  # placeholder, can also compute using ORS
        if extra_dist <= ride.get("max_extra_km", 2) and extra_time <= ride.get("max_extra_min", 15):
            matches.append(Match(ride_id=ride["id"], extra_distance=extra_dist, extra_time=extra_time))
    return matches
