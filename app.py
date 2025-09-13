# app.py — Single-file Streamlit ridesharing MVP (refactored, RLS-aware)
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
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY")
ORS_API_KEY = st.secrets.get("ORS_API_KEY")  # optional but recommended

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error(
        "Missing Supabase secrets. Add SUPABASE_URL and SUPABASE_KEY in Streamlit Cloud Secrets."
    )
    st.stop()

# Create Supabase client
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error(f"Failed to create Supabase client: {e}")
    st.stop()

# ===========================
# HELPERS / UTILITIES
# ===========================
def format_departure(dep):
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
    if not isinstance(coords, (list, tuple)) or len(coords) != 2:
        return False
    try:
        float(coords[0]); float(coords[1])
        return True
    except Exception:
        return False

@lru_cache(maxsize=1000)
def geocode_postcode_cached(postcode: str, retries=2):
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
            return [float(coords[1]), float(coords[0])]
        except Exception:
            if attempt < retries:
                pytime.sleep(1)
                continue
            return None

def route_distance_time(start, end):
    if not ORS_API_KEY:
        return None, None
    try:
        url = "https://api.openrouteservice.org/v2/directions/driving-car"
        headers = {"Authorization": ORS_API_KEY}
        body = {"coordinates": [[start[1], start[0]], [end[1], end[0]]]}
        r = requests.post(url, json=body, headers=headers, timeout=6)
        r.raise_for_status()
        data = r.json()
        dist = data["routes"][0]["summary"]["distance"] / 1000
        dur = data["routes"][0]["summary"]["duration"] / 60
        return dist, dur
    except Exception:
        return None, None

def haversine_km(a, b):
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    R = 6371.0
    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(h))

# ===========================
# AUTH
# ===========================
if "user" not in st.session_state:
    st.session_state.user = None

def normalize_user(user_obj):
    if not user_obj:
        return None
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
                st.rerun()
            else:
                st.error(f"{action} failed. Check credentials.")
        except Exception as e:
            st.error(f"Auth error: {e}")

if not st.session_state.user:
    show_login()
    st.stop()

# ===========================
# DB HELPERS
# ===========================
def insert_table_row(table_name: str, payload: dict):
    try:
        res = supabase.table(table_name).insert(payload).execute()
        if isinstance(res, dict) and res.get("error"):
            raise Exception(res["error"])
        return res
    except Exception as e:
        msg = str(e)
        if "row-level security" in msg or "42501" in msg:
            st.error(
                "Insert blocked by Supabase Row-Level Security (RLS).\n\n"
                "➡️ Fix: Add an RLS policy in Supabase for this table, e.g.:\n\n"
                "CREATE POLICY \"Allow insert for authenticated users\" "
                "ON public.rides FOR INSERT USING (auth.uid() IS NOT NULL);"
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
# MAIN UI
# ===========================
st.sidebar.title(f"Welcome, {st.session_state.user.get('email')}")
if st.sidebar.button("Log out"):
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    st.session_state.user = None
    st.rerun()

view = st.sidebar.radio("Go to", ["Post Ride", "Post Passenger", "Find Matches", "Debug"])

# ---------- Post Ride ----------
if view == "Post Ride":
    st.title("Post a Ride (Driver)")
    with st.form("ride_form"):
        origin = st.text_input("Origin Postcode (NL)")
        destination = st.text_input("Destination Postcode (NL)")
        departure = st.time_input("Departure Time", value=datetime.now().time())
        max_extra_km = st.number_input("Max extra distance (km)", 0.0, 100.0, 5.0, step=0.5)
        max_extra_min = st.number_input("Max extra time (minutes)", 0, 240, 15, step=5)
        submit = st.form_submit_button("Submit Ride")

    if submit:
        origin_coords = geocode_postcode_cached(origin) if ORS_API_KEY else None
        dest_coords = geocode_postcode_cached(destination) if ORS_API_KEY else None
        payload = {
            "user_id": st.session_state.user["id"],
            "origin": origin.strip().upper(),
            "destination": destination.strip().upper(),
            "departure": format_departure(departure),
            "origin_coords": origin_coords or [],
            "dest_coords": dest_coords or [],
            "max_extra_km": float(max_extra_km),
            "max_extra_min": int(max_extra_min),
            "created_at": datetime.utcnow().isoformat(),
        }
        res = insert_table_row("rides", payload)
        if res:
            st.success("Ride posted!")

# ---------- Post Passenger ----------
elif view == "Post Passenger":
    st.title("Post a Passenger Request")
    with st.form("passenger_form"):
        origin = st.text_input("Origin Postcode (NL)")
        destination = st.text_input("Destination Postcode (NL)")
        departure = st.time_input("Departure Time", value=datetime.now().time())
        submit = st.form_submit_button("Submit Request")

    if submit:
        origin_coords = geocode_postcode_cached(origin) if ORS_API_KEY else None
        dest_coords = geocode_postcode_cached(destination) if ORS_API_KEY else None
        payload = {
            "user_id": st.session_state.user["id"],
            "origin": origin.strip().upper(),
            "destination": destination.strip().upper(),
            "departure": format_departure(departure),
            "origin_coords": origin_coords or [],
            "dest_coords": dest_coords or [],
            "created_at": datetime.utcnow().isoformat(),
        }
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
        passenger = passengers[-1]
        st.write(f"Passenger: {passenger.get('origin')} → {passenger.get('destination')}")
        matches = []
        for ride in rides:
            if not ride.get("origin_coords") or not ride.get("dest_coords"):
                continue
            base_dist, _ = route_distance_time(ride["origin_coords"], ride["dest_coords"])
            if base_dist is None:
                continue
            d1, _ = route_distance_time(ride["origin_coords"], passenger["origin_coords"])
            d2, _ = route_distance_time(passenger["origin_coords"], passenger["dest_coords"])
            d3, _ = route_distance_time(passenger["dest_coords"], ride["dest_coords"])
            if None in (d1, d2, d3):
                continue
            detour_dist = d1 + d2 + d3
            extra_dist = detour_dist - base_dist
            if extra_dist <= ride.get("max_extra_km", 999):
                matches.append((ride, extra_dist))
        if matches:
            st.subheader("Matching Rides:")
            for ride, ex_d in matches:
                st.write(f"🚗 {ride.get('origin')} → {ride.get('destination')} at {ride.get('departure')}")
                st.write(f"   Extra distance: {ex_d:.1f} km (max {ride.get('max_extra_km')})")
        else:
            st.warning("No suitable matches found.")

# ---------- Debug ----------
elif view == "Debug":
    st.title("Debug Info")
    st.json(st.session_state.user)
    if st.button("List rides"):
        st.json(get_rides())
    if st.button("List my passengers"):
        st.json(get_passengers(st.session_state.user["id"]))
