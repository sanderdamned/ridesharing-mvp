import streamlit as st
from supabase import create_client, Client
import datetime
import requests
import math

# ----------------------------
# Setup & config
# ----------------------------
st.set_page_config(page_title="NL Carpool Platform", layout="centered")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
ORS_API_KEY  = st.secrets["ORS_API_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Keep session user
if "user" not in st.session_state:
    st.session_state.user = None


# ----------------------------
# Utilities
# ----------------------------
def geocode_nl(query: str):
    """Geocode a NL location string with Nominatim. Returns (lat, lon) or (None, None)."""
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "countrycodes": "nl", "limit": 1},
            headers={"User-Agent": "rideshare-app-nl"},
            timeout=12,
        )
        r.raise_for_status()
        data = r.json()
        if not data:
            return None, None
        return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        return None, None


def ors_directions_summary(coordinates_lonlat: list[list[float]]):
    """
    Call ORS directions (driving-car) with 2+ coordinates.
    coordinates_lonlat: [[lon, lat], ...]
    Returns (distance_m, duration_s).
    """
    url = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
    headers = {"Authorization": ORS_API_KEY, "Content-Type": "application/json"}
    body = {"coordinates": coordinates_lonlat}
    resp = requests.post(url, json=body, headers=headers, timeout=25)
    resp.raise_for_status()
    feat = resp.json()["features"][0]
    summary = feat["properties"]["summary"]
    return int(round(summary["distance"])), int(round(summary["duration"]))


def pretty_km(m):
    return f"{m/1000:.1f} km"


def pretty_min(sec):
    return f"{math.ceil(sec/60)} min"


# ----------------------------
# Auth
# ----------------------------
def login():
    st.title("Login or Register")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    action = st.radio("Action", ["Login", "Register"], horizontal=True)

    if st.button(action):
        try:
            if action == "Login":
                res = supabase.auth.sign_in_with_password({"email": email, "password": password})
            else:
                res = supabase.auth.sign_up({"email": email, "password": password})
            st.session_state.user = res.user
            st.success(f"{action} successful!")
            st.experimental_rerun()
        except Exception as e:
            st.error(f"{action} failed: {e}")


# ----------------------------
# Driver: Post a trip
# ----------------------------
def post_driver_trip(user_id):
    st.header("Post a Driver Trip")
    start_txt = st.text_input("From (NL location)")
    end_txt   = st.text_input("To (NL location)")
    dep_dt    = st.datetime_input("Departure Time", value=datetime.datetime.now())
    seats     = st.number_input("Available Seats", min_value=1, step=1)

    if st.button("Post Trip"):
        s_lat, s_lon = geocode_nl(start_txt)
        e_lat, e_lon = geocode_nl(end_txt)
        if not s_lat or not e_lat:
            st.error("Could not geocode one of the locations.")
            return

        # Get baseline driver route stats with ORS
        try:
            base_dist, base_dur = ors_directions_summary([[s_lon, s_lat], [e_lon, e_lat]])
        except Exception as e:
            st.error(f"ORS routing failed: {e}")
            return

        # Save to DB (store baseline route metrics for later detour calc)
        supabase.table("trips").insert({
            "driver_id": user_id,
            "start_location": start_txt,
            "start_lat": s_lat,
            "start_lon": s_lon,
            "end_location": end_txt,
            "end_lat": e_lat,
            "end_lon": e_lon,
            "datetime": dep_dt.isoformat(),
            "seats_available": int(seats),
            "route_distance_m": base_dist,
            "route_duration_s": base_dur,
        }).execute()

        st.success(f"Trip posted. Base route: {pretty_km(base_dist)}, {pretty_min(base_dur)}")


# ----------------------------
# Passenger: Simple search (legacy)
# ----------------------------
def search_trips(rider_id):
    st.header("Quick Search (start/end proximity)")
    origin = st.text_input("Start location (NL)")
    dest   = st.text_input("Destination (NL)")
    pref_t = st.time_input("Preferred Departure Time", value=datetime.time(8, 0))

    if st.button("Find Trips"):
        o_lat, o_lon = geocode_nl(origin)
        d_lat, d_lon = geocode_nl(dest)
        if not o_lat or not d_lat:
            st.error("Locations not found.")
            return

        response = supabase.table("trips").select("*").execute()
        results = []
        for t in response.data or []:
            # crude bbox-like filter (lat-only)
            dist_score = abs(t["start_lat"] - o_lat) + abs(t["end_lat"] - d_lat)
            if dist_score < 1:
                results.append(t)

        if results:
            for t in results:
                st.markdown(f"""
**From**: {t["start_location"]} → **To**: {t["end_location"]}  
**Departure**: {t["datetime"]}  
**Seats**: {t["seats_available"]}  
Baseline: {pretty_km(t.get("route_distance_m", 0))}, {pretty_min(t.get("route_duration_s", 0))}
""")
        else:
            st.info("No matching trips found.")


# ----------------------------
# Passenger: Find Matches (real ORS detour logic)
# ----------------------------
def find_matches_view(user_id):
    st.header("Find Driver Matches (Detour-based)")

    pickup_txt  = st.text_input("Pickup location (NL)")
    dropoff_txt = st.text_input("Dropoff location (NL)")
    col1, col2 = st.columns(2)
    with col1:
        desired_date = st.date_input("Desired Pickup Date", value=datetime.date.today())
    with col2:
        desired_time = st.time_input("Desired Pickup Time", value=datetime.datetime.now().time())
    desired_dt = datetime.datetime.combine(desired_date, desired_time)

    st.markdown("**Filters**")
    c1, c2, c3 = st.columns(3)
    with c1:
        time_window = st.slider("Time window (± min)", 10, 120, 45, 5)
    with c2:
        # step=0.5 km
        max_extra_km = st.slider("Max extra distance (km)", 0.5, 30.0, 5.0, 0.5)
    with c3:
        max_extra_min = st.slider("Max extra time (min)", 1, 90, 15, 1)

    if st.button("Find Matches"):
        p_lat, p_lon = geocode_nl(pickup_txt)
        d_lat, d_lon = geocode_nl(dropoff_txt)
        if not p_lat or not d_lat:
            st.error("Could not geocode pickup or dropoff.")
            return

        earliest = (desired_dt - datetime.timedelta(minutes=time_window)).isoformat()
        latest   = (desired_dt + datetime.timedelta(minutes=time_window)).isoformat()

        # First filter by time window to reduce ORS calls
        q = (
            supabase.table("trips")
            .select("*")
            .gte("datetime", earliest)
            .lte("datetime", latest)
            .order("datetime")
            .execute()
        )
        candidates = q.data or []
        if not candidates:
            st.warning("No driver trips in that time window.")
            return

        max_extra_m   = int(round(max_extra_km * 1000))
        max_extra_sec = max_extra_min * 60
        matches = []
        failed = 0

        with st.spinner("Computing detours (ORS)…"):
            for t in candidates:
                try:
                    s_lat, s_lon = t["start_lat"], t["start_lon"]
                    e_lat, e_lon = t["end_lat"], t["end_lon"]

                    # Base route: DriverStart -> DriverEnd
                    base_dist = t.get("route_distance_m")
                    base_dur  = t.get("route_duration_s")
                    if base_dist is None or base_dur is None:
                        # compute if not stored (fallback)
                        base_dist, base_dur = ors_directions_summary([[s_lon, s_lat], [e_lon, e_lat]])

                    # Detour route: DriverStart -> Pickup -> Dropoff -> DriverEnd
                    detour_dist, detour_dur = ors_directions_summary([
                        [s_lon, s_lat],
                        [p_lon, p_lat],
                        [d_lon, d_lat],
                        [e_lon, e_lat],
                    ])

                    extra_dist = detour_dist - base_dist
                    extra_time = detour_dur - base_dur

                    if extra_dist <= max_extra_m and extra_time <= max_extra_sec:
                        # Also compute absolute time difference for sorting / info
                        driver_dt = datetime.datetime.fromisoformat(t["datetime"])
                        td_min = abs((driver_dt - desired_dt).total_seconds()) / 60.0

                        matches.append({
                            **t,
                            "_extra_distance_m": int(extra_dist),
                            "_extra_time_s": int(extra_time),
                            "_time_diff_min": int(round(td_min)),
                            "_detour_distance_m": detour_dist,
                            "_detour_duration_s": detour_dur,
                        })
                except Exception:
                    failed += 1
                    continue

        if not matches:
            msg = "No matches found under your detour limits."
            if failed:
                msg += f" (Some routes failed to compute: {failed})"
            st.warning(msg)
            return

        # Sort: smallest extra_time then extra_distance, then time diff
        matches.sort(key=lambda m: (m["_extra_time_s"], m["_extra_distance_m"], m["_time_diff_min"]))

        st.success(f"Found {len(matches)} match(es).")
        for m in matches:
            st.markdown(f"""
**Driver trip**  
From: {m['start_location']} → To: {m['end_location']}  
Departs: {m['datetime']}  
Seats: {m['seats_available']}

**Baseline**  
• Distance: {pretty_km(m.get('route_distance_m', 0))}  
• Duration: {pretty_min(m.get('route_duration_s', 0))}

**With your pickup & dropoff**  
• Detour distance: {pretty_km(m['_detour_distance_m'])}  
• Detour duration: {pretty_min(m['_detour_duration_s'])}

**Extra for driver**  
• Extra distance: {pretty_km(m['_extra_distance_m'])}  
• Extra time: {pretty_min(m['_extra_time_s'])}  
• Time difference at departure: {m['_time_diff_min']} min
---
""")


# ----------------------------
# MAIN
# ----------------------------
if not st.session_state.user:
    login()
    st.stop()

# sidebar
st.sidebar.write(f"Logged in as **{st.session_state.user['email']}**")
if st.sidebar.button("Log out"):
    supabase.auth.sign_out()
    st.session_state.user = None
    st.experimental_rerun()

choice = st.sidebar.selectbox(
    "Choose Action",
    ["Post a Driver Trip", "Quick Search", "Find Matches (Detour-based)"]
)

user_id = st.session_state.user.id

if choice == "Post a Driver Trip":
    post_driver_trip(user_id)
elif choice == "Quick Search":
    search_trips(user_id)
else:
    find_matches_view(user_id)
