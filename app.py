import streamlit as st
from supabase import create_client, Client
from datetime import datetime, time, timedelta
from functools import lru_cache
import math
import time as pytime
from geopy.geocoders import Nominatim

# ===========================
# CONFIG / INIT
# ===========================
st.set_page_config(page_title="Ridesharing MVP", layout="centered")

SUPABASE_URL = st.secrets.get("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY")
ORS_API_KEY = st.secrets.get("ORS_API_KEY")  # optional

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Missing Supabase secrets. Add SUPABASE_URL and SUPABASE_KEY in Streamlit Cloud Secrets.")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ===========================
# HELPERS
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

@lru_cache(maxsize=1000)
def geocode_postcode_cached(postcode: str, retries=2):
    geolocator = Nominatim(user_agent="ridesharing_app")
    for attempt in range(retries + 1):
        try:
            location = geolocator.geocode(postcode + ", Netherlands", timeout=10)
            if location:
                return [location.latitude, location.longitude]
            return []
        except Exception:
            if attempt < retries:
                pytime.sleep(1)
                continue
            return []

def route_distance_time(start, end):
    """Returns (distance_km, duration_minutes). Uses simple haversine-based estimate."""
    if not start or not end:
        return None, None
    lat1, lon1 = start
    lat2, lon2 = end
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    dist = R * c
    dur = dist / 50 * 60  # assume 50 km/h avg speed
    return dist, dur

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
if "access_token" not in st.session_state:
    st.session_state.access_token = None

def normalize_user(user_obj):
    if not user_obj:
        return None
    return {"id": getattr(user_obj, "id", None), "email": getattr(user_obj, "email", None)}

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
            if getattr(resp, "user", None):
                st.session_state.user = normalize_user(resp.user)
                st.session_state.access_token = resp.session.access_token if getattr(resp, "session", None) else None
                st.success(f"{action} successful. You are logged in as {resp.user.email}.")
            else:
                st.error(f"{action} failed: {resp}")
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
        if not getattr(res, "data", None):
            st.error(f"Insert error: {res}")
            return None
        return res.data
    except Exception as e:
        st.error(f"Insert exception: {e}")
        return None

def update_table_row(table_name: str, row_id: str, payload: dict):  # NEW
    try:
        res = supabase.table(table_name).update(payload).eq("id", row_id).execute()
        return res.data
    except Exception as e:
        st.error(f"Update exception: {e}")
        return None

def get_table_rows(table_name: str, filter_by: dict = None):
    try:
        query = supabase.table(table_name).select("*")
        if filter_by:
            for k, v in filter_by.items():
                query = query.eq(k, v)
        res = query.execute()
        return res.data or []
    except Exception as e:
        st.error(f"Query exception: {e}")
        return []

# ===========================
# MAIN UI
# ===========================
st.sidebar.title(f"Welcome, {st.session_state.user['email']}")
if st.sidebar.button("Log out"):
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    st.session_state.user = None
    st.session_state.access_token = None
    st.info("Logged out. Please refresh the page.")
    st.stop()

view = st.sidebar.radio("Go to", ["Post Ride", "Post Passenger", "Find Matches", "My Matches", "Rate", "Debug"])

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
        origin_coords = geocode_postcode_cached(origin)
        dest_coords = geocode_postcode_cached(destination)
        payload = {
            "user_id": st.session_state.user["id"],
            "origin": origin.strip().upper(),
            "destination": destination.strip().upper(),
            "departure": format_departure(departure),
            "origin_coords": origin_coords,
            "dest_coords": dest_coords,
            "max_extra_km": float(max_extra_km),
            "max_extra_min": int(max_extra_min),
            "created_at": datetime.utcnow().isoformat(),
        }
        if insert_table_row("rides", payload):
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
        origin_coords = geocode_postcode_cached(origin)
        dest_coords = geocode_postcode_cached(destination)
        payload = {
            "user_id": st.session_state.user["id"],
            "origin": origin.strip().upper(),
            "destination": destination.strip().upper(),
            "departure": format_departure(departure),
            "origin_coords": origin_coords,
            "dest_coords": dest_coords,
            "created_at": datetime.utcnow().isoformat(),
        }
        if insert_table_row("passengers", payload):
            st.success("Passenger request posted!")

# ---------- Find Matches ----------
elif view == "Find Matches":
    st.title("Find Matches (Detour-based)")
    passengers = get_table_rows("passengers", {"user_id": st.session_state.user["id"]})
    rides = get_table_rows("rides")

    if not passengers:
        st.info("You need to post a passenger request first.")
    else:
        passenger = passengers[-1]
        st.write(f"Passenger: {passenger.get('origin')} → {passenger.get('destination')}")

        matches = []
        for ride in rides:
            if ride["user_id"] == st.session_state.user["id"]:  # 🚫 skip own rides
                continue
            if not ride.get("origin_coords") or not ride.get("dest_coords"):
                continue
            base_dist, _ = route_distance_time(ride["origin_coords"], ride["dest_coords"])
            d1, _ = route_distance_time(ride["origin_coords"], passenger["origin_coords"])
            d2, _ = route_distance_time(passenger["origin_coords"], passenger["dest_coords"])
            d3, _ = route_distance_time(passenger["dest_coords"], ride["dest_coords"])
            if None in (base_dist, d1, d2, d3):
                continue
            detour_dist = d1 + d2 + d3
            extra_dist = detour_dist - base_dist

            if extra_dist <= ride.get("max_extra_km", 999):
                fee_passenger = detour_dist * 0.12
                earning_rider = detour_dist * 0.10
                matches.append((ride, detour_dist, fee_passenger, earning_rider))

        if matches:
            st.subheader("Matching Rides:")
            for ride, dist, fee_p, earn_r in matches:
                st.write(f"🚗 {ride['origin']} → {ride['destination']} at {ride['departure']}")
                st.write(f"   Distance: {dist:.1f} km | Passenger pays €{fee_p:.2f} | Rider earns €{earn_r:.2f}")
                if st.button(f"Request Match with {ride['id']}"):
                    insert_table_row("matches", {
                        "ride_id": ride["id"],
                        "passenger_id": passenger["id"],
                        "status": "requested",
                        "created_at": datetime.utcnow().isoformat(),
                    })
                    st.success("Match requested!")
        else:
            st.warning("No suitable matches found.")

# ---------- My Matches ----------
elif view == "My Matches":
    st.title("My Matches")
    matches = get_table_rows("matches", {"status": "requested"})
    for match in matches:
        # Passenger flow
        if match.get("passenger_id") and st.session_state.user["id"] == match["passenger_id"]:
            pickup = st.text_input(f"Pickup location for match {match['id']}")
            if st.button(f"Confirm pickup {match['id']}"):
                update_table_row("matches", match["id"], {"pickup": pickup, "status": "passenger_confirmed"})
                st.success("Pickup shared with driver.")

        # Driver flow
        if match.get("ride_id"):
            ride = get_table_rows("rides", {"id": match["ride_id"]})
            if ride and st.session_state.user["id"] == ride[0]["user_id"]:
                brand = st.text_input(f"Car brand for match {match['id']}")
                color = st.text_input(f"Car color for match {match['id']}")
                plate = st.text_input(f"License plate (optional) for match {match['id']}")
                if st.button(f"Final confirm {match['id']}"):
                    update_table_row("matches", match["id"], {
                        "car_brand": brand,
                        "car_color": color,
                        "car_plate": plate,
                        "status": "driver_confirmed"
                    })
                    st.success("Ride confirmed!")

# ---------- Ratings ----------
elif view == "Rate":
    st.title("Rate your rides")
    confirmed_matches = get_table_rows("matches", {"status": "driver_confirmed"})
    for match in confirmed_matches:
        # Passenger rates driver
        if match.get("passenger_id") == st.session_state.user["id"]:
            rating = st.slider(f"Rate your driver for match {match['id']}", 1, 5)
            if st.button(f"Submit rating driver {match['id']}"):
                update_table_row("matches", match["id"], {"rating_driver": rating})
                st.success("Rating submitted!")

        # Driver rates passenger
        ride = get_table_rows("rides", {"id": match["ride_id"]})
        if ride and ride[0]["user_id"] == st.session_state.user["id"]:
            rating = st.slider(f"Rate your passenger for match {match['id']}", 1, 5)
            if st.button(f"Submit rating passenger {match['id']}"):
                update_table_row("matches", match["id"], {"rating_passenger": rating})
                st.success("Rating submitted!")

# ---------- Debug ----------
elif view == "Debug":
    st.title("Debug Info")
    st.json({"user": st.session_state.user})
    st.json({"rides": get_table_rows("rides")})
    st.json({"passengers": get_table_rows("passengers")})
    st.json({"matches": get_table_rows("matches")})
