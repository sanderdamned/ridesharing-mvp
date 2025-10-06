import streamlit as st
from supabase import create_client, Client
from datetime import datetime, time, timedelta
from functools import lru_cache
import math
import time as pytime
import requests

# ===========================
# CONFIG / INIT
# ===========================
st.set_page_config(page_title="Ridesharing MVP", layout="centered")

SUPABASE_URL = st.secrets.get("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY")
OPENCAGE_KEY = st.secrets.get("OPENCAGE_KEY")  # 👈 add this to your Streamlit Secrets

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Missing Supabase secrets. Add SUPABASE_URL and SUPABASE_KEY in Streamlit Cloud Secrets.")
    st.stop()

if not OPENCAGE_KEY:
    st.error("Missing OpenCage key. Add OPENCAGE_KEY to Streamlit Cloud Secrets.")
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
    """
    Geocode a Dutch postcode using OpenCage API.
    Returns [lat, lon] or [] if not found.
    """
    url = f"https://api.opencagedata.com/geocode/v1/json?q={postcode},Netherlands&key={OPENCAGE_KEY}&limit=1"
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                results = data.get("results", [])
                if results:
                    lat = results[0]["geometry"]["lat"]
                    lon = results[0]["geometry"]["lng"]
                    return [lat, lon]
                else:
                    st.warning(f"No results for postcode {postcode}.")
                    return []
            else:
                st.warning(f"OpenCage error ({r.status_code}): {r.text}")
        except Exception as e:
            st.warning(f"Geocoding error ({attempt+1}/{retries}): {e}")
            pytime.sleep(1)
    return []


def haversine_km(a, b):
    if not a or not b:
        return 9999
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    R = 6371.0
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
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
                st.session_state.access_token = (
                    resp.session.access_token if getattr(resp, "session", None) else None
                )
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
        return res.data if getattr(res, "data", None) else []
    except Exception as e:
        st.error(f"Insert exception: {e}")
        return []


def update_table_row(table_name: str, row_id: str, payload: dict):
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
        return res.data if getattr(res, "data", None) else []
    except Exception as e:
        st.error(f"Query exception: {e}")
        return []


# ===========================
# MATCH LOGIC
# ===========================
def check_for_matches(new_ride):
    rides = get_table_rows("rides", {"ride_date": new_ride["ride_date"]})
    for ride in rides:
        if ride["id"] == new_ride["id"]:
            continue
        if new_ride["role"] == ride["role"]:
            continue

        driver = new_ride if new_ride["role"] == "driver" else ride
        passenger = new_ride if new_ride["role"] == "passenger" else ride

        dep_driver = datetime.strptime(driver["departure"], "%H:%M:%S")
        dep_pass = datetime.strptime(passenger["departure"], "%H:%M:%S")
        if not (dep_driver - timedelta(minutes=15) <= dep_pass <= dep_driver + timedelta(minutes=5)):
            continue

        if haversine_km(driver["origin_coords"], passenger["origin_coords"]) > driver.get("max_extra_km", 999):
            continue
        if haversine_km(driver["dest_coords"], passenger["dest_coords"]) > driver.get("max_extra_km", 999):
            continue

        insert_table_row(
            "matches",
            {
                "driver_id": driver["id"],
                "passenger_id": passenger["id"],
                "status": "requested",
                "created_at": datetime.utcnow().isoformat(),
            },
        )
        st.info("🚀 Match found! Check 'My Matches' to confirm.")


# ===========================
# MAIN UI
# ===========================
menu = ["Welcome", "Submit Ride", "My Matches", "Rate"]
choice = st.sidebar.radio("Menu", menu)

# ---------- Welcome ----------
if choice == "Welcome":
    st.title("Welcome 🎉")
    profile = get_table_rows("profiles", {"id": st.session_state.user["id"]})
    if profile:
        p = profile[0]
        st.write(f"👤 Name: {p.get('name')}")
        st.write(f"🚗 Car: {p.get('car_brand')} ({p.get('car_color')})")
        st.write(f"🎵 Favorite song: {p.get('fav_song')}")
    else:
        with st.form("profile_form"):
            name = st.text_input("Your name")
            brand = st.text_input("Car brand")
            color = st.text_input("Car color")
            song = st.text_input("Favorite car song")
            submit = st.form_submit_button("Save profile")
        if submit:
            insert_table_row(
                "profiles",
                {
                    "id": st.session_state.user["id"],
                    "name": name,
                    "car_brand": brand,
                    "car_color": color,
                    "fav_song": song,
                },
            )
            st.success("Profile saved! Please refresh.")

# ---------- Submit Ride ----------
elif choice == "Submit Ride":
    st.title("Submit a Ride")
    with st.form("ride_form"):
        origin = st.text_input("Origin Postcode (NL)")
        destination = st.text_input("Destination Postcode (NL)")
        ride_date = st.date_input("Date of departure", value=datetime.today())
        departure = st.time_input("Expected Departure Time", value=datetime.now().time())
        role = st.radio("I am a", ["driver", "passenger"])
        max_extra_km, pickup = None, None
        if role == "driver":
            max_extra_km = st.number_input("Max extra distance (km)", 0.0, 100.0, 5.0, step=0.5)
        else:
            pickup = st.text_input("Exact pickup location")
        submit = st.form_submit_button("Submit Ride")

    if submit:
        origin_coords = geocode_postcode_cached(origin)
        dest_coords = geocode_postcode_cached(destination)

        if not origin_coords or not dest_coords:
            st.error("Could not geocode one or both postcodes. Try a nearby one.")
            st.stop()

        payload = {
            "user_id": st.session_state.user["id"],
            "role": role,
            "origin": origin.strip().upper(),
            "destination": destination.strip().upper(),
            "ride_date": ride_date.isoformat(),
            "departure": format_departure(departure),
            "origin_coords": origin_coords,
            "dest_coords": dest_coords,
            "max_extra_km": float(max_extra_km) if max_extra_km else None,
            "pickup_location": pickup,
            "created_at": datetime.utcnow().isoformat(),
        }
        new_ride = insert_table_row("rides", payload)
        if new_ride:
            st.success("Ride posted!")
            check_for_matches(new_ride[0])

# ---------- My Matches ----------
elif choice == "My Matches":
    st.title("My Matches")
    my_rides = get_table_rows("rides", {"user_id": st.session_state.user["id"]})
    ride_ids = [r["id"] for r in my_rides]
    all_matches = get_table_rows("matches")
    my_matches = [m for m in all_matches if m["driver_id"] in ride_ids or m["passenger_id"] in ride_ids]

    if not my_matches:
        st.info("No matches yet.")
    for m in my_matches:
        st.write(m)

# ---------- Ratings ----------
elif choice == "Rate":
    st.title("Rate your rides")
    confirmed_matches = get_table_rows("matches", {"status": "driver_confirmed"})
    for match in confirmed_matches:
        if match.get("passenger_id") == st.session_state.user["id"]:
            rating = st.slider(f"Rate your driver for match {match['id']}", 1, 5)
            if st.button(f"Submit rating driver {match['id']}"):
                update_table_row("matches", match["id"], {"rating_driver": rating})
                st.success("Rating submitted!")
        my_rides = get_table_rows("rides", {"id": match["ride_id"]})
        if my_rides and my_rides[0]["user_id"] == st.session_state.user["id"]:
            rating = st.slider(f"Rate your passenger for match {match['id']}", 1, 5)
            if st.button(f"Submit rating passenger {match['id']}"):
                update_table_row("matches", match["id"], {"rating_passenger": rating})
                st.success("Rating submitted!")
