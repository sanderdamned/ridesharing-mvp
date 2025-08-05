import streamlit as st
from supabase import create_client
import pandas as pd
import requests
import datetime
from geopy.geocoders import Nominatim

# --- Supabase Setup ---
SUPABASE_URL = "https://ivzlapmdomoxwzwptixb.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Iml2emxhcG1kb21veHd6d3B0aXhiIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQzMzA1MDgsImV4cCI6MjA2OTkwNjUwOH0.tgjQ_RBX-62xlJv7RuugHrPuz7XxINHhc2zYF7laMGE"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Geocoder Setup ---
geolocator = Nominatim(user_agent="rideshare-app")

def geocode(address):
    location = geolocator.geocode(address)
    if location:
        return location.latitude, location.longitude
    return None, None

# --- Signup/Login ---
st.title("🚗 Dutch Ridesharing Platform")
auth_action = st.sidebar.radio("Login or Signup", ["Login", "Signup"])
email = st.sidebar.text_input("Email")
password = st.sidebar.text_input("Password", type="password")

if auth_action == "Signup":
    if st.sidebar.button("Create Account"):
        try:
            supabase.auth.sign_up({"email": email, "password": password})
            st.sidebar.success("Signup successful. Please login.")
        except Exception as e:
            st.sidebar.error(f"Signup failed: {e}")
    st.stop()
elif auth_action == "Login":
    if st.sidebar.button("Login"):
        try:
            user = supabase.auth.sign_in_with_password({"email": email, "password": password})
            st.session_state["user"] = user
            st.sidebar.success("Logged in!")
        except Exception as e:
            st.sidebar.error(f"Login failed: {e}")
    if "user" not in st.session_state:
        st.stop()

user_id = st.session_state["user"]["user"]["id"]

# --- Tabs ---
tab = st.selectbox("Choose Action", ["Post Trip", "View Trips"])

if tab == "Post Trip":
    st.header("Post a New Ride")

    departure_postal = st.text_input("Departure Postal Code", max_chars=7)
    departure_number = st.text_input("Departure House Number")
    arrival_postal = st.text_input("Arrival Postal Code", max_chars=7)
    arrival_number = st.text_input("Arrival House Number")
    time = st.datetime_input("Departure Time", value=datetime.datetime.now())
    seats = st.number_input("Available Seats", min_value=1, max_value=10, value=1)

    if st.button("Post Trip"):
        dep_address = f"{departure_postal} {departure_number}, Netherlands"
        arr_address = f"{arrival_postal} {arrival_number}, Netherlands"
        dep_lat, dep_lng = geocode(dep_address)
        arr_lat, arr_lng = geocode(arr_address)

        if None in [dep_lat, dep_lng, arr_lat, arr_lng]:
            st.error("Could not find coordinates for one of the addresses.")
        else:
            supabase.table("trips").insert({
                "user_id": user_id,
                "departure_postal": departure_postal,
                "departure_number": departure_number,
                "arrival_postal": arrival_postal,
                "arrival_number": arrival_number,
                "departure_lat": dep_lat,
                "departure_lng": dep_lng,
                "arrival_lat": arr_lat,
                "arrival_lng": arr_lng,
                "departure_time": time.isoformat(),
                "seats": seats
            }).execute()
            st.success("Trip posted successfully!")

elif tab == "View Trips":
    st.header("Available Rides")
    response = supabase.table("trips").select("*").order("departure_time").execute()
    trips = response.data
    if not trips:
        st.info("No trips posted yet.")
    else:
        for trip in trips:
            st.markdown(f"""
                **From:** {trip['departure_postal']} {trip['departure_number']}  
                **To:** {trip['arrival_postal']} {trip['arrival_number']}  
                **Time:** {trip['departure_time']}  
                **Seats Available:** {trip['seats']}
            """)
