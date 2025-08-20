import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime
import requests
import os

# ================== CONFIG ==================
st.set_page_config(page_title="Ridesharing MVP", layout="centered")

# Load Supabase credentials
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ORS API Key
ORS_API_KEY = st.secrets.get("ORS_API_KEY", None)

# Session state for logged in user
if "user" not in st.session_state:
    st.session_state.user = None

# ================== AUTH ==================
def normalize_user(user_obj):
    """Return a safe dict with id and email"""
    if user_obj is None:
        return None
    return {
        "id": getattr(user_obj, "id", None),
        "email": getattr(user_obj, "email", None)
    }

def login():
    st.title("Login or Register")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    action = st.radio("Action", ["Login", "Register"])

    if st.button(action):
        try:
            if action == "Login":
                user_response = supabase.auth.sign_in_with_password({
                    "email": email,
                    "password": password
                })
            else:
                user_response = supabase.auth.sign_up({
                    "email": email,
                    "password": password
                })

            # normalize user object to a dict with id/email
            st.session_state.user = normalize_user(user_response.user)

            if st.session_state.user["id"] is not None:
                st.success(f"{action} successful!")
                st.rerun()
            else:
                st.error(f"{action} failed. Check credentials.")
        except Exception as e:
            st.error(f"Error: {e}")

# Initialize user session if missing
if "user" not in st.session_state:
    st.session_state.user = None

if not st.session_state.user:
    login()
    st.stop()

# ================== SIDEBAR ==================
if st.session_state.user:
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


# ================== HELPERS ==================
def geocode_postcode(postcode: str):
    """Convert postcode to coordinates using ORS geocoding"""
    if not ORS_API_KEY:
        st.error("ORS_API_KEY missing in Streamlit secrets")
        return None

    url = "https://api.openrouteservice.org/geocode/search"
    params = {"api_key": ORS_API_KEY, "text": postcode, "boundary.country": "NL"}
    r = requests.get(url, params=params)
    data = r.json()
    try:
        coords = data["features"][0]["geometry"]["coordinates"]  # [lon, lat]
        return coords[::-1]  # return as [lat, lon]
    except Exception:
        return None


def route_distance_time(start, end):
    """Get driving distance (km) + duration (min) between two coords"""
    url = "https://api.openrouteservice.org/v2/directions/driving-car"
    headers = {"Authorization": ORS_API_KEY}
    body = {"coordinates": [[start[1], start[0]], [end[1], end[0]]]}
    r = requests.post(url, json=body, headers=headers)
    data = r.json()
    try:
        dist = data["routes"][0]["summary"]["distance"] / 1000  # km
        dur = data["routes"][0]["summary"]["duration"] / 60  # min
        return dist, dur
    except Exception:
        return None, None

# ================== VIEWS ==================
if view == "Post Ride":
    st.title("Post a Ride (Driver)")

    with st.form("ride_form"):
        origin = st.text_input("Origin Postcode")
        destination = st.text_input("Destination Postcode")
        departure = st.time_input("Departure Time")
        max_extra_km = st.number_input("Max extra distance (km)", 0.0, 20.0, 2.0, step=0.5)
        max_extra_min = st.number_input("Max extra time (minutes)", 0, 120, 15, step=5)
        submit = st.form_submit_button("Submit Ride")

    if submit:
        origin_coords = geocode_postcode(origin)
        dest_coords = geocode_postcode(destination)
        if not origin_coords or not dest_coords:
            st.error("Invalid origin or destination postcode")
        else:
            supabase.table("rides").insert({
                "user_id": st.session_state.user["id"],
                "origin": origin,
                "destination": destination,
                "departure": str(departure),
                "origin_coords": origin_coords,
                "dest_coords": dest_coords,
                "max_extra_km": max_extra_km,
                "max_extra_min": max_extra_min
            }).execute()
            st.success("Ride posted!")

elif view == "Post Passenger":
    st.title("Post a Passenger Request")

    with st.form("passenger_form"):
        origin = st.text_input("Origin Postcode")
        destination = st.text_input("Destination Postcode")
        departure = st.time_input("Departure Time")
        submit = st.form_submit_button("Submit Request")

    if submit:
        origin_coords = geocode_postcode(origin)
        dest_coords = geocode_postcode(destination)
        if not origin_coords or not dest_coords:
            st.error("Invalid origin or destination postcode")
        else:
            supabase.table("passengers").insert({
                "user_id": st.session_state.user["id"],
                "origin": origin,
                "destination": destination,
                "departure": str(departure),
                "origin_coords": origin_coords,
                "dest_coords": dest_coords,
            }).execute()
            st.success("Passenger request posted!")

elif view == "Find Matches":
    st.title("Find Matches (Detour-based)")

    passengers = supabase.table("passengers").select("*").eq("user_id", st.session_state.user["id"]).execute().data
    rides = supabase.table("rides").select("*").execute().data

    if not passengers:
        st.info("You need to post a passenger request first.")
    else:
        passenger = passengers[-1]  # latest
        st.write(f"Passenger request: {passenger['origin']} → {passenger['destination']} at {passenger['departure']}")

        if rides:
            matches = []
            for ride in rides:
                base_dist, base_time = route_distance_time(ride["origin_coords"], ride["dest_coords"])
                if base_dist is None:
                    continue

                # detour route: driver picks up passenger first, then goes to their own destination
                detour_dist, detour_time = route_distance_time(ride["origin_coords"], passenger["origin_coords"])
                extra_dist, extra_time = 0, 0
                if detour_dist is not None:
                    to_dest_dist, to_dest_time = route_distance_time(passenger["origin_coords"], ride["dest_coords"])
                    if to_dest_dist:
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
