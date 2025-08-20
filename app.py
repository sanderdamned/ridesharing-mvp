import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime
import requests
import datetime as dt

# ----------------- SUPABASE SETUP -----------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="Ridesharing MVP", layout="wide")

# ----------------- SESSION STATE -----------------
if "user" not in st.session_state:
    st.session_state.user = None

# ----------------- AUTH -----------------
def login():
    st.title("Login or Register")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    action = st.radio("Action", ["Login", "Register"])

    if st.button(action):
        try:
            if action == "Login":
                user = supabase.auth.sign_in_with_password(
                    {"email": email, "password": password}
                )
            else:
                user = supabase.auth.sign_up(
                    {"email": email, "password": password}
                )

            st.session_state.user = user.user
            st.success(f"{action} successful!")
            st.rerun()

        except Exception as e:
            st.error(f"Error: {e}")

if not st.session_state.user:
    login()
    st.stop()

# ----------------- LOGOUT -----------------
st.sidebar.title(f"Welcome, {st.session_state.user['email']}")
if st.sidebar.button("Log out"):
    supabase.auth.sign_out()
    st.session_state.user = None
    st.rerun()

# ----------------- ORS HELPERS -----------------
def geocode(address):
    """Turn address or postal code into lat/lon using ORS."""
    url = "https://api.openrouteservice.org/geocode/search"
    params = {"api_key": st.secrets["ORS_API_KEY"], "text": address}
    resp = requests.get(url, params=params).json()
    coords = resp["features"][0]["geometry"]["coordinates"]  # [lon, lat]
    return coords[1], coords[0]

def distance_m(lat1, lon1, lat2, lon2):
    """Driving distance in meters between two coords."""
    url = "https://api.openrouteservice.org/v2/matrix/driving-car"
    headers = {
        "Authorization": st.secrets["ORS_API_KEY"],
        "Content-Type": "application/json",
    }
    body = {"locations": [[lon1, lat1], [lon2, lat2]]}
    resp = requests.post(url, json=body, headers=headers)
    data = resp.json()
    return data["distances"][0][1]  # meters

# ----------------- VIEWS -----------------
def post_ride_view(user_id):
    st.header("🚗 Offer a Ride")

    pickup = st.text_input("Pickup Address / Postal Code")
    dropoff = st.text_input("Dropoff Address / Postal Code")
    date = st.date_input("Date", dt.date.today())
    time = st.time_input("Departure Time", dt.datetime.now().time())
    seats = st.number_input("Available Seats", min_value=1, step=1)

    if st.button("Post Ride"):
        try:
            lat1, lon1 = geocode(pickup)
            lat2, lon2 = geocode(dropoff)
            trip = {
                "user_id": user_id,
                "role": "driver",
                "pickup": pickup,
                "dropoff": dropoff,
                "start_lat": lat1,
                "start_lon": lon1,
                "end_lat": lat2,
                "end_lon": lon2,
                "datetime": dt.datetime.combine(date, time).isoformat(),
                "seats": seats,
            }
            supabase.table("trips").insert(trip).execute()
            st.success("Ride posted!")
        except Exception as e:
            st.error(f"Error posting ride: {e}")

def post_passenger_view(user_id):
    st.header("🧍 Request a Ride")

    pickup = st.text_input("Pickup Address / Postal Code")
    dropoff = st.text_input("Dropoff Address / Postal Code")
    date = st.date_input("Date", dt.date.today())
    time = st.time_input("Preferred Time", dt.datetime.now().time())

    if st.button("Request Ride"):
        try:
            lat1, lon1 = geocode(pickup)
            lat2, lon2 = geocode(dropoff)
            trip = {
                "user_id": user_id,
                "role": "passenger",
                "pickup": pickup,
                "dropoff": dropoff,
                "start_lat": lat1,
                "start_lon": lon1,
                "end_lat": lat2,
                "end_lon": lon2,
                "datetime": dt.datetime.combine(date, time).isoformat(),
            }
            supabase.table("trips").insert(trip).execute()
            st.success("Passenger request posted!")
        except Exception as e:
            st.error(f"Error posting request: {e}")

def find_matches_view(user_id):
    st.header("🔎 Find Matches")

    pickup = st.text_input("Your Pickup Address / Postal Code")
    dropoff = st.text_input("Your Dropoff Address / Postal Code")
    date = st.date_input("Date", dt.date.today())
    time = st.time_input("Time", dt.datetime.now().time())

    max_detour_km = st.slider("Max extra distance (km)", 0.5, 10.0, 2.0, 0.5)
    max_extra_time = st.slider("Max extra driving time (minutes)", 5, 60, 15)

    if st.button("Find Matches"):
        desired_dt = dt.datetime.combine(date, time)

        try:
            p_lat, p_lon = geocode(pickup)
            d_lat, d_lon = geocode(dropoff)

            trips = supabase.table("trips").select("*").execute().data
            matches = []
            for trip in trips:
                if trip["user_id"] == user_id:
                    continue  # don't match with self

                trip_dt = dt.datetime.fromisoformat(trip["datetime"])
                time_diff = abs((trip_dt - desired_dt).total_seconds() / 60)

                pickup_dist = distance_m(p_lat, p_lon, trip["start_lat"], trip["start_lon"])
                dropoff_dist = distance_m(d_lat, d_lon, trip["end_lat"], trip["end_lon"])

                if (
                    pickup_dist <= max_detour_km * 1000
                    and dropoff_dist <= max_detour_km * 1000
                    and time_diff <= max_extra_time
                ):
                    matches.append(
                        {
                            **trip,
                            "_time_diff_min": round(time_diff, 1),
                            "_pickup_distance_m": round(pickup_dist, 1),
                            "_dropoff_distance_m": round(dropoff_dist, 1),
                        }
                    )

            if matches:
                st.success(f"Found {len(matches)} matches:")
                df = pd.DataFrame(matches)
                st.dataframe(df)
            else:
                st.warning("No matches found.")

        except Exception as e:
            st.error(f"Error finding matches: {e}")

# ----------------- MAIN -----------------
st.title("🚘 Ridesharing MVP")

menu = st.sidebar.radio("Menu", ["Offer Ride", "Request Ride", "Find Matches"])

if menu == "Offer Ride":
    post_ride_view(st.session_state.user["id"])
elif menu == "Request Ride":
    post_passenger_view(st.session_state.user["id"])
elif menu == "Find Matches":
    find_matches_view(st.session_state.user["id"])
