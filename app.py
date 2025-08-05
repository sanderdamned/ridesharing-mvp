import streamlit as st
from supabase import create_client, Client
from geopy.geocoders import Nominatim
import datetime
import os

# ---- CONFIGURATION ----
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "https://your-project.supabase.co")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "your-anon-key")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

geolocator = Nominatim(user_agent="rideshare-nl")

# ---- FUNCTIONS ----
def get_coordinates(address):
    location = geolocator.geocode(f"{address}, Netherlands")
    if location:
        return location.latitude, location.longitude
    return None, None

def signup(email, password):
    try:
        result = supabase.auth.sign_up({"email": email, "password": password})
        return result
    except Exception as e:
        st.error(f"Signup failed: {e}")
        return None

def login(email, password):
    try:
        result = supabase.auth.sign_in_with_password({"email": email, "password": password})
        return result
    except Exception as e:
        st.error(f"Login failed: {e}")
        return None

def post_trip(user_id):
    st.header("Post a Ride")

    from_address = st.text_input("Pickup address (e.g., 1098 XH 23)")
    to_address = st.text_input("Drop-off address (e.g., 1012 AB 1)")
    departure_datetime = st.datetime_input("Departure Time", value=datetime.datetime.now())
    seats_available = st.number_input("Seats Available", min_value=1, max_value=7, value=1)

    if st.button("Post Ride"):
        from_lat, from_lon = get_coordinates(from_address)
        to_lat, to_lon = get_coordinates(to_address)

        if None in (from_lat, from_lon, to_lat, to_lon):
            st.error("Could not find coordinates for one of the locations.")
            return

        data = {
            "user_id": user_id,
            "from_address": from_address,
            "from_lat": from_lat,
            "from_lon": from_lon,
            "to_address": to_address,
            "to_lat": to_lat,
            "to_lon": to_lon,
            "departure_time": departure_datetime.isoformat(),
            "seats_available": seats_available,
        }

        supabase.table("trips").insert(data).execute()
        st.success("Ride posted successfully!")

def view_trips():
    st.header("Available Trips")
    response = supabase.table("trips").select("*").order("departure_time").execute()
    trips = response.data

    if not trips:
        st.info("No trips available.")
        return

    for trip in trips:
        st.markdown(f"""
        🚗 **From:** {trip['from_address']}  
        📍 **To:** {trip['to_address']}  
        ⏰ **Departure:** {trip['departure_time']}  
        👥 **Seats:** {trip['seats_available']}  
        """)

# ---- MAIN APP ----
st.set_page_config(page_title="NL Rideshare", layout="centered")

st.title("🇳🇱 Ridesharing Platform – NL")

menu = st.sidebar.selectbox("Choose option", ["Login", "Sign Up", "View Trips"])

if menu == "Sign Up":
    st.subheader("Create Account")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Sign Up"):
        user = signup(email, password)
        if user:
            st.success("Account created. Please log in.")

elif menu == "Login":
    st.subheader("Login")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        auth_data = login(email, password)
        if auth_data:
            st.session_state["user"] = auth_data.user.id
            st.success("Login successful!")

if "user" in st.session_state:
    st.sidebar.success("Logged in")
    post_trip(st.session_state["user"])

view_trips()
