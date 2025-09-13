import streamlit as st
from supabase import create_client, Client
import requests
from datetime import datetime, time
import time as pytime

# ================== CONFIG ==================
st.set_page_config(page_title="Ridesharing MVP", layout="centered")

# Load Supabase credentials
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

ORS_API_KEY = st.secrets.get("ORS_API_KEY", None)

# ================== SESSION STATE INIT ==================
if "user" not in st.session_state:
    st.session_state.user = None  # None or dict with id/email

# ================== HELPERS ==================
def normalize_user(user_obj):
    if not user_obj:
        return None
    return {
        "id": getattr(user_obj, "id", None),
        "email": getattr(user_obj, "email", None)
    }

def geocode_postcode(postcode: str, retries=2):
    """Return [lat, lon] as float list"""
    if not ORS_API_KEY:
        st.error("ORS_API_KEY missing in Streamlit secrets")
        return None
    url = "https://api.openrouteservice.org/geocode/search"
    params = {"api_key": ORS_API_KEY, "text": postcode, "boundary.country": "NL"}
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, timeout=5)
            r.raise_for_status()
            data = r.json()
            coords = data["features"][0]["geometry"]["coordinates"]  # [lon, lat]
            return [float(coords[1]), float(coords[0])]  # [lat, lon]
        except (requests.RequestException, IndexError, KeyError) as e:
            if attempt < retries:
                pytime.sleep(1)
                continue
            st.error(f"Geocoding failed for '{postcode}': {e}")
            return None

def format_departure(dep):
    """Return HH:MM:SS string"""
    if isinstance(dep, time):
        return dep.strftime("%H:%M:%S")
    elif isinstance(dep, str):
        try:
            dt = datetime.strptime(dep, "%H:%M")
            return dt.strftime("%H:%M:%S")
        except ValueError:
            return dep
    return str(dep)

def route_distance_time(start, end):
    """Return (distance_km, duration_min) using ORS"""
    if not ORS_API_KEY:
        return None, None
    url = "https://api.openrouteservice.org/v2/directions/driving-car"
    headers = {"Authorization": ORS_API_KEY}
    body = {"coordinates": [[start[1], start[0]], [end[1], end[0]]]}
    try:
        r = requests.post(url, json=body, headers=headers, timeout=5)
        r.raise_for_status()
        data = r.json()
        dist = data["routes"][0]["summary"]["distance"] / 1000
        dur = data["routes"][0]["summary"]["duration"] / 60
        return dist, dur
    except Exception:
        return None, None

# ================== AUTH ==================
def login():
    st.title("Login or Register")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    action = st.radio("Action", ["Login", "Register"])

    if st.button(action):
        try:
            if action == "Login":
                user_response = supabase.auth.sign_in_with_password({"email": email, "password": password})
            else:
                user_response = supabase.auth.sign_up({"email": email, "password": password})
            st.session_state.user = normalize_user(user_response.user)
            if st.session_state.user:
                st.success(f"{action} successful!")
                st.rerun()
            else:
                st.error(f"{action} failed.")
        except Exception as e:
            st.error(f"Error: {e}")

if not st.session_state.user:
    login()
    st.stop()

# ================== SIDEBAR ==================
email = st.session_state.user.get("email")
if email:
    st.sidebar.title(f"Welcome, {email}")

if st.sidebar.button("Log out"):
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    st.session_state.user = None
    st.rerun()

view = st.sidebar.radio("Go to", ["Post Ride", "Post Passenger", "Find Matches"])

# ================== VIEWS ==================
if view == "Post Ride":
    st.title("Post a Ride (Driver)")
    with st.form("ride_form"):
        origin = st.text_input("Origin Postcode")
        destination = st.text_input("Destination Postcode")
        departure = st.time_input("Departure Time")
        max_extra_km = st.number_input("Max extra distance (km)", 0.0, 50.0, 2.0, step=0.5)
        max_extra_min = st.number_input("Max extra time (minutes)", 0, 180, 15, step=5)
        submit = st.form_submit_button("Submit Ride")

    if submit:
        if not st.session_state.user or not st.session_state.user.get("id"):
            st.error("You must be logged in to post a ride.")
        else:
            origin_coords = geocode_postcode(origin)
            dest_coords = geocode_postcode(destination)
            if not origin_coords or not dest_coords:
                st.error("Invalid origin or destination postcode")
            else:
                payload = {
                    "user_id": st.session_state.user["id"],
                    "origin": origin.strip().upper(),
                    "destination": destination.strip().upper(),
                    "departure": format_departure(departure),
                    "origin_coords": origin_coords,  # ✅ float list
                    "dest_coords": dest_coords,      # ✅ float list
                    "max_extra_km": float(max_extra_km),
                    "max_extra_min": int(max_extra_min),
                }
                st.write("DEBUG payload:", payload)
                supabase.table("rides").insert(payload).execute()
                st.success("Ride posted!")

elif view == "Post Passenger":
    st.title("Post a Passenger Request")
    with st.form("passenger_form"):
        origin = st.text_input("Origin Postcode")
        destination = st.text_input("Destination Postcode")
        departure = st.time_input("Departure Time")
        submit = st.form_submit_button("Submit Request")

    if submit:
        if not st.session_state.user or not st.session_state.user.get("id"):
            st.error("You must be logged in to post a request.")
        else:
            origin_coords = geocode_postcode(origin)
            dest_coords = geocode_postcode(destination)
            if not origin_coords or not dest_coords:
                st.error("Invalid origin or destination postcode")
            else:
                payload = {
                    "user_id": st.session_state.user["id"],
                    "origin": origin.strip().upper(),
                    "destination": destination.strip().upper(),
                    "departure": format_departure(departure),
                    "origin_coords": origin_coords,  # ✅ float list
                    "dest_coords": dest_coords,      # ✅ float list
                }
                st.write("DEBUG payload:", payload)
                supabase.table("passengers").insert(payload).execute()
                st.success("Passenger request posted!")

elif view == "Find Matches":
    st.title("Find Matches (Detour-based)")

    passengers = supabase.table("passengers").select("*").eq(
        "user_id", st.session_state.user["id"]
    ).execute().data
    rides = supabase.table("rides").select("*").execute().data

    if not passengers:
        st.info("You need to post a passenger request first.")
    else:
        passenger = passengers[-1]
        st.write(f"Passenger request: {passenger['origin']} → {passenger['destination']} at {passenger['departure']}")
        if rides:
            matches = []
            for ride in rides:
                base_dist, base_time = route_distance_time(ride["origin_coords"], ride["dest_coords"])
                if base_dist is None:
                    continue
                detour_dist, detour_time = route_distance_time(ride["origin_coords"], passenger["origin_coords"])
                extra_dist, extra_time = 0, 0
                if detour_dist is not None:
                    to_dest_dist, to_dest_time = route_distance_time(passenger["origin_coords"], ride["dest_coords"])
                    if to_dest_dist is not None:
                        detour_dist += to_dest_dist
                        detour_time += to_dest_time
                        extra_dist = detour_dist - base_dist
                        extra_time = detour_time - base_time
                if extra_dist <= ride["max_extra_km"] and extra_time <= ride["max_extra_min"]:
                    matches.append((ride, extra_dist, extra_time))
            if matches:
                st.subheader("Matching Rides:")
                for ride, ex_d, ex_t in matches:
                    st.write(f"🚗 Ride {ride['origin']} → {ride['destination']} at {ride['departure']}")
                    st.write(f"   Extra distance: {ex_d:.1f} km | Extra time: {ex_t:.0f} min")
            else:
                st.warning("No suitable matches found.")
        else:
            st.info("No rides available yet.")
