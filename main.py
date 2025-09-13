import streamlit as st
from auth import login
from db import insert_ride, insert_passenger, get_rides, get_passengers
from geocoding import geocode_postcode
from utils import format_departure, validate_coordinates
from matching import find_matches
from models import Ride, PassengerRequest

st.set_page_config(page_title="Ridesharing MVP", layout="centered")

# ================== SESSION STATE ==================
if "user" not in st.session_state:
    st.session_state.user = None

# ================== AUTH ==================
if not st.session_state.user:
    login()
    st.stop()

# Sidebar
email = st.session_state.user.get("email")
if email:
    st.sidebar.title(f"Welcome, {email}")
if st.sidebar.button("Log out"):
    st.session_state.user = None
    st.rerun()

view = st.sidebar.radio("Go to", ["Post Ride", "Post Passenger", "Find Matches"])

# ================== VIEWS ==================
if view == "Post Ride":
    st.title("Post a Ride")
    with st.form("ride_form"):
        origin = st.text_input("Origin Postcode")
        destination = st.text_input("Destination Postcode")
        departure = st.time_input("Departure Time")
        max_extra_km = st.number_input("Max extra distance (km)", 0.0, 50.0, 2.0)
        max_extra_min = st.number_input("Max extra time (minutes)", 0, 180, 15)
        submit = st.form_submit_button("Submit Ride")
    if submit:
        origin_coords = geocode_postcode(origin)
        dest_coords = geocode_postcode(destination)
        if not validate_coordinates(origin_coords) or not validate_coordinates(dest_coords):
            st.error("Invalid coordinates")
        else:
            ride = Ride(
                user_id=st.session_state.user["id"],
                origin=origin,
                destination=destination,
                departure=format_departure(departure),
                origin_coords=origin_coords,
                dest_coords=dest_coords,
                max_extra_km=max_extra_km,
                max_extra_min=max_extra_min
            )
            insert_ride(ride.dict())
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
        if not validate_coordinates(origin_coords) or not validate_coordinates(dest_coords):
            st.error("Invalid coordinates")
        else:
            passenger = PassengerRequest(
                user_id=st.session_state.user["id"],
                origin=origin,
                destination=destination,
                departure=format_departure(departure),
                origin_coords=origin_coords,
                dest_coords=dest_coords
            )
            insert_passenger(passenger.dict())
            st.success("Passenger request posted!")

elif view == "Find Matches":
    st.title("Find Matches")
    passengers = get_passengers(st.session_state.user["id"])
    rides = get_rides()
    if not passengers:
        st.info("Post a passenger request first.")
    else:
        passenger = passengers[-1]
        st.write(f"Passenger request: {passenger['origin']} → {passenger['destination']}")
        matches = find_matches(passenger, rides)
        if matches:
            for m in matches:
                st.write(f"Ride ID: {m.ride_id}, Extra Distance: {m.extra_distance:.1f} km")
        else:
            st.info("No matches found.")
