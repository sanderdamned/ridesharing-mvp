import streamlit as st
from supabase import create_client, Client
import datetime
import requests

# Setup
SUPABASE_URL = "https://ivzlapmdomoxwzwptixb.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Iml2emxhcG1kb21veHd6d3B0aXhiIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQzMzA1MDgsImV4cCI6MjA2OTkwNjUwOH0.tgjQ_RBX-62xlJv7RuugHrPuz7XxINHhc2zYF7laMGE"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="NL Carpool Platform", layout="centered")

# Session
if "user" not in st.session_state:
    st.session_state.user = None

# Auth
def login():
    st.title("Login or Sign Up")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        try:
            user = supabase.auth.sign_in_with_password({"email": email, "password": password})
            st.session_state.user = user.user
        except Exception as e:
            st.error("Login failed.")
    if st.button("Sign Up"):
        try:
            user = supabase.auth.sign_up({"email": email, "password": password})
            st.session_state.user = user.user
        except Exception as e:
            st.error("Signup failed. " + str(e))

# Get coordinates from OpenStreetMap (NL focused)
def get_coords(location_name):
    response = requests.get("https://nominatim.openstreetmap.org/search", params={
        "q": location_name,
        "format": "json",
        "countrycodes": "nl",
        "limit": 1
    })
    if response.ok and response.json():
        data = response.json()[0]
        return float(data["lat"]), float(data["lon"])
    return None, None

# Post trip
def post_trip(user_id):
    st.header("Post a Trip")
    start = st.text_input("From (NL location)")
    end = st.text_input("To (NL location)")
    time = st.datetime_input("Departure Time", value=datetime.datetime.now())
    seats = st.number_input("Available Seats", min_value=1, step=1)

    if st.button("Post Trip"):
        start_lat, start_lon = get_coords(start)
        end_lat, end_lon = get_coords(end)
        if start_lat and end_lat:
            supabase.table("trips").insert({
                "driver_id": user_id,
                "start_location": start,
                "start_lat": start_lat,
                "start_lon": start_lon,
                "end_location": end,
                "end_lat": end_lat,
                "end_lon": end_lon,
                "datetime": time.isoformat(),
                "seats_available": seats
            }).execute()
            st.success("Trip posted.")
        else:
            st.error("Could not find coordinates for one of the locations.")

# Search trips
def search_trips(rider_id):
    st.header("Search for Trips")
    origin = st.text_input("Start location (NL)")
    dest = st.text_input("Destination (NL)")
    time = st.time_input("Preferred Departure Time", value=datetime.time(8, 0))

    if st.button("Find Trips"):
        o_lat, o_lon = get_coords(origin)
        d_lat, d_lon = get_coords(dest)
        if not o_lat or not d_lat:
            st.error("Locations not found.")
            return

        # naive radius filter
        response = supabase.table("trips").select("*").execute()
        results = []
        for trip in response.data:
            dist = abs(trip["start_lat"] - o_lat) + abs(trip["end_lat"] - d_lat)
            if dist < 1:  # approx ~10-15km
                results.append(trip)

        if results:
            for trip in results:
                st.markdown(f"""
                **From**: {trip["start_location"]} → **To**: {trip["end_location"]}  
                **Departure**: {trip["datetime"]}  
                **Seats**: {trip["seats_available"]}  
                """)
                if st.button(f"Request Seat for Trip {trip['id']}"):
                    supabase.table("trip_requests").insert({
                        "trip_id": trip["id"],
                        "rider_id": rider_id
                    }).execute()
                    st.success("Requested to join trip.")
        else:
            st.info("No matching trips found.")

# MAIN FLOW
if not st.session_state.user:
    login()
else:
    user_id = st.session_state.user.id
    st.sidebar.write("Logged in as", st.session_state.user.email)
    option = st.sidebar.selectbox("Choose Action", ["Post a Trip", "Search Trips", "Log out"])

    if option == "Post a Trip":
        post_trip(user_id)
    elif option == "Search Trips":
        search_trips(user_id)
    elif option == "Log out":
        st.session_state.user = None
