# main.py — Single-file Streamlit ridesharing MVP (refactored, RLS-aware)
import streamlit as st
from supabase import create_client, Client
import requests
from datetime import datetime, time
from functools import lru_cache
import math
import time as pytime

# ===========================
# CONFIG / INIT
# ===========================
st.set_page_config(page_title="Ridesharing MVP", layout="centered")

SUPABASE_URL = st.secrets.get("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY")  # ensure this is set in Streamlit Cloud Secrets
ORS_API_KEY = st.secrets.get("ORS_API_KEY")    # optional but recommended

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error(
        "Missing Supabase secrets. Add SUPABASE_URL and SUPABASE_KEY in Streamlit Cloud Secrets. "
        "See app settings -> Secrets."
    )
    st.stop()

# Create supabase client
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error(f"Failed to create Supabase client: {e}")
    st.stop()

# ===========================
# HELPERS / UTILITIES
# ===========================
def format_departure(dep):
    """Return HH:MM:SS string"""
    if isinstance(dep, time):
        return dep.strftime("%H:%M:%S")
    if isinstance(dep, str):
        try:
            dt = datetime.strptime(dep, "%H:%M")
            return dt.strftime("%H:%M:%S")
        except ValueError:
            return dep
    return str(dep)

def validate_coordinates(coords):
    """Ensure coords is a list of two floats"""
    if not isinstance(coords, (list, tuple)) or len(coords) != 2:
        return False
    try:
        float(coords[0]); float(coords[1])
        return True
    except Exception:
        return False

@lru_cache(maxsize=1000)
def geocode_postcode_cached(postcode: str, retries=2):
    """
    Return [lat, lon] list or None.
    Caches results to reduce API usage.
    """
    if not ORS_API_KEY:
        return None
    url = "https://api.openrouteservice.org/geocode/search"
    params = {"api_key": ORS_API_KEY, "text": postcode, "boundary.country": "NL"}
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, timeout=5)
            r.raise_for_status()
            data = r.json()
            coords = data["features"][0]["geometry"]["coordinates"]  # [lon, lat]
            return [float(coords[1]), float(coords[0])]  # lat, lon
        except Exception as e:
            if attempt < retries:
                pytime.sleep(1)
                continue
            return None

def route_distance_time(start, end):
    """Return (distance_km, duration_min) via OpenRouteService or (None, None)"""
    if not ORS_API_KEY:
        return None, None
    try:
        url = "https://api.openrouteservice.org/v2/directions/driving-car"
        headers = {"Authorization": ORS_API_KEY}
        body = {"coordinates": [[start[1], start[0]], [end[1], end[0]]]}
        r = requests.post(url, json=body, headers=headers, timeout=6)
        r.raise_for_status()
        data = r.json()
        dist = data["routes"][0]["summary"]["distance"] / 1000  # km
        dur = data["routes"][0]["summary"]["duration"] / 60     # minutes
        return dist, dur
    except Exception:
        return None, None

def haversine_km(a, b):
    """Fast haversine distance (km) between two [lat, lon] points"""
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    R = 6371.0
    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(h))

# ===========================
# AUTH (very simple)
# ===========================
if "user" not in st.session_state:
    st.session_state.user = None  # will hold {"id": ..., "email": ...}

def normalize_user(user_obj):
    if not user_obj:
        return None
    # supabase Python client returns .user (object) — be defensive
    try:
        uid = getattr(user_obj, "id", None) or user_obj.get("id")
        email = getattr(user_obj, "email", None) or user_obj.get("email")
        return {"id": uid, "email": email}
    except Exception:
        return None

def show_login():
    st.title("Login or Register")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    action = st.radio("Action", ["Login", "Register"])
    if st.button(action):
        try:
            if action == "Login":
                resp = supabase.auth.sign_in_with_password({"email": email, "password": password})
            else:
                resp = supabase.auth.sign_up({"email": email, "password": password})
            user = resp.user if hasattr(resp, "user") else resp.get("user")
            st.session_state.user = normalize_user(user)
            if st.session_state.user:
                st.success(f"{action} successful!")
                st.experimental_rerun()
            else:
                st.error(f"{action} failed. Check credentials or check Supabase logs.")
        except Exception as e:
            st.error(f"Auth error: {e}")

# If not logged in, show login and stop
if not st.session_state.user:
    show_login()
    st.stop()

# ===========================
# DB helpers (wrap operations and surface RLS issues)
# ===========================
def insert_table_row(table_name: str, payload: dict):
    """Insert row and return result. Surface RLS errors friendly."""
    try:
        res = supabase.table(table_name).insert(payload).execute()
        # supabase-py returns dict-like with 'data'/'error' sometimes
        # If insertion blocked by RLS, Supabase often returns status_code 403/42501
        if hasattr(res, "error") and res.error:
            raise Exception(res.error)
        # If response is dict-like:
        if isinstance(res, dict) and res.get("error"):
            raise Exception(res["error"])
        return res
    except Exception as e:
        # Provide actionable message for the common RLS error
        msg = str(e)
        if "row-level security" in msg or "42501" in msg or "permission denied" in msg:
            st.error(
                "Insert failed due to Supabase Row-Level Security (RLS). "
                "Fix options:\n\n"
                "1) In Supabase dashboard for your `rides` (or inserted) table, add an RLS policy to allow inserts for authenticated users. Example SQL:\n\n"
                "   CREATE POLICY \"Allow insert for authenticated users\" ON public.rides FOR INSERT USING (auth.uid() IS NOT NULL);\n\n"
                "2) Or use your **service_role** key on the server (NOT recommended in client-side apps) so the insert bypasses RLS.\n\n"
                "If you added the policy, try again. See Supabase docs for Row Level Security."
            )
        else:
            st.error(f"Insert error: {e}")
        return None

def get_rides():
    try:
        res = supabase.table("rides").select("*").execute()
        return res.data if hasattr(res, "data") else res.get("data", [])
    except Exception as e:
        st.error(f"Failed fetching rides: {e}")
        return []

def get_passengers(user_id=None):
    try:
        q = supabase.table("passengers").select("*")
        if user_id:
            q = q.eq("user_id", user_id)
        res = q.execute()
        return res.data if hasattr(res, "data") else res.get("data", [])
    except Exception as e:
        st.error(f"Failed fetching passengers: {e}")
        return []

# ===========================
# UI / Main Flow
# ===========================
st.sidebar.title(f"Welcome, {st.session_state.user.get('email')}")
if st.sidebar.button("Log out"):
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    st.session_state.user = None
    st.experimental_rerun()

view = st.sidebar.radio("Go to", ["Post Ride", "Post Passenger", "Find Matches", "Debug"])

# ---------- Post Ride ----------
if view == "Post Ride":
    st.title("Post a Ride (Driver)")
    with st.form("ride_form"):
        origin = st.text_input("Origin Postcode (NL)", value="")
        destination = st.text_input("Destination Postcode (NL)", value="")
        departure = st.time_input("Departure Time", value=datetime.now().time())
        max_extra_km = st.number_input("Max extra distance (km)", 0.0, 100.0, 5.0, step=0.5)
        max_extra_min = st.number_input("Max extra time (minutes)", 0, 240, 15, step=5)
        submit = st.form_submit_button("Submit Ride")

    if submit:
        # quick validation
        if not origin or not destination:
            st.error("Origin and destination are required.")
        else:
            origin_coords = geocode_postcode_cached(origin) if ORS_API_KEY else None
            dest_coords = geocode_postcode_cached(destination) if ORS_API_KEY else None

            if ORS_API_KEY and (not validate_coordinates(origin_coords) or not validate_coordinates(dest_coords)):
                st.error("Failed to geocode one of the postcodes — check ORS_API_KEY and postcode format.")
            else:
                payload = {
                    "user_id": st.session_state.user["id"],
                    "origin": origin.strip().upper(),
                    "destination": destination.strip().upper(),
                    "departure": format_departure(departure),
                    "origin_coords": origin_coords or [],   # store empty list if no ORS
                    "dest_coords": dest_coords or [],
                    "max_extra_km": float(max_extra_km),
                    "max_extra_min": int(max_extra_min),
                    "created_at": datetime.utcnow().isoformat(),
                }
                st.write("DEBUG: inserting payload (not all fields required in your DB):", payload)
                res = insert_table_row("rides", payload)
                if res:
                    st.success("Ride posted!")

# ---------- Post Passenger ----------
elif view == "Post Passenger":
    st.title("Post a Passenger Request")
    with st.form("passenger_form"):
        origin = st.text_input("Origin Postcode (NL)", value="")
        destination = st.text_input("Destination Postcode (NL)", value="")
        departure = st.time_input("Departure Time", value=datetime.now().time())
        submit = st.form_submit_button("Submit Request")

    if submit:
        if not origin or not destination:
            st.error("Origin and destination are required.")
        else:
            origin_coords = geocode_postcode_cached(origin) if ORS_API_KEY else None
            dest_coords = geocode_postcode_cached(destination) if ORS_API_KEY else None

            if ORS_API_KEY and (not validate_coordinates(origin_coords) or not validate_coordinates(dest_coords)):
                st.error("Failed to geocode one of the postcodes — check ORS_API_KEY and postcode format.")
            else:
                payload = {
                    "user_id": st.session_state.user["id"],
                    "origin": origin.strip().upper(),
                    "destination": destination.strip().upper(),
                    "departure": format_departure(departure),
                    "origin_coords": origin_coords or [],
                    "dest_coords": dest_coords or [],
                    "created_at": datetime.utcnow().isoformat(),
                }
                st.write("DEBUG: inserting passenger payload:", payload)
                res = insert_table_row("passengers", payload)
                if res:
                    st.success("Passenger request posted!")

# ---------- Find Matches ----------
elif view == "Find Matches":
    st.title("Find Matches (Detour-based)")
    passengers = get_passengers(st.session_state.user["id"])
    rides = get_rides()
    if not passengers:
        st.info("You need to post a passenger request first.")
    else:
        passenger = passengers[-1]  # use most recent
        st.write(f"Passenger request: {passenger.get('origin')} → {passenger.get('destination')} at {passenger.get('departure')}")
        # quick candidate filtering using haversine: we find rides where origin and dest are not extremely far
        candidates = []
        if not rides:
            st.info("No rides available yet.")
        else:
            p_origin = passenger.get("origin_coords") or []
            p_dest = passenger.get("dest_coords") or []
            if not p_origin or not p_dest:
                st.warning("Passenger coordinates missing — geocoding not available. Post passenger with ORS_API_KEY set.")
            else:
                # Pre-filter rides by simple distance (origin near origin, dest near destination)
                for ride in rides:
                    r_origin = ride.get("origin_coords") or []
                    r_dest = ride.get("dest_coords") or []
                    if not r_origin or not r_dest:
                        continue
                    # basic distances
                    d_o = haversine_km(p_origin, r_origin)
                    d_d = haversine_km(p_dest, r_dest)
                    # threshold: origin within 20 km and dest within 20 km (configurable)
                    if d_o <= 20 and d_d <= 20:
                        candidates.append(ride)

                if not candidates:
                    st.warning("No nearby candidate rides found (fast filter).")
                else:
                    # For candidates, compute detour precisely using ORS (limited to top N candidates to save API)
                    # Rank candidates by sum of origin/destination quick distances and select top N
                    candidates_sorted = sorted(candidates, key=lambda r: haversine_km(p_origin, r.get("origin_coords")))
                    top = candidates_sorted[:10]
                    matches = []
                    base_info = []
                    for ride in top:
                        base_dist, base_time = route_distance_time(ride["origin_coords"], ride["dest_coords"])
                        if base_dist is None:
                            continue
                        # route: ride.origin -> passenger.origin -> passenger.dest -> ride.dest
                        dist1, _ = route_distance_time(ride["origin_coords"], passenger["origin_coords"])
                        dist2, _ = route_distance_time(passenger["origin_coords"], passenger["dest_coords"])
                        dist3, _ = route_distance_time(passenger["dest_coords"], ride["dest_coords"])
                        if None in (dist1, dist2, dist3):
                            continue
                        detour_dist = dist1 + dist2 + dist3
                        extra_dist = detour_dist - base_dist
                        # compute times similarly (if ORS returns)
                        # (for simplicity here we set extra_time = None unless you need it)
                        extra_time = None
                        if extra_dist <= ride.get("max_extra_km", 999):
                            matches.append((ride, extra_dist))
                    if matches:
                        st.subheader("Matching Rides:")
                        for ride, ex_d in matches:
                            st.write(f"🚗 Ride {ride.get('origin')} → {ride.get('destination')} at {ride.get('departure')}")
                            st.write(f"   Extra distance: {ex_d:.1f} km | Max allowed: {ride.get('max_extra_km')}")
                    else:
                        st.warning("No suitable matches found after detour calculations.")

# ---------- Debug ----------
elif view == "Debug":
    st.title("Debug / Info")
    st.write("User:", st.session_state.user)
    st.write("Supabase URL:", SUPABASE_URL)
    st.write("ORS available:", bool(ORS_API_KEY))
    if st.button("List rides (raw)"):
        st.json(get_rides())
    if st.button("List my passengers (raw)"):
        st.json(get_passengers(st.session_state.user["id"]))
