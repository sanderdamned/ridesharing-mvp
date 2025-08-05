import streamlit as st
from supabase import create_client
from geopy.geocoders import Nominatim
import datetime

# --- Supabase setup ---
SUPABASE_URL = "https://ivzlapmdomoxwzwptixb.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Iml2emxhcG1kb21veHd6d3B0aXhiIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQzMzA1MDgsImV4cCI6MjA2OTkwNjUwOH0.tgjQ_RBX-62xlJv7RuugHrPuz7XxINHhc2zYF7laMGE"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

geolocator = Nominatim(user_agent="rideshare-app-nl")

# --- Auth ---
def login():
    st.subheader("Login")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        try:
            user = supabase.auth.sign_in_with_password({"email": email, "password": password})
            if user.session:
                st.success("Logged in!")
                st.session_state["user"] = user
                st.rerun()  # replaced deprecated experimental_rerun
            else:
                st.error("Login failed, email not confirmed or wrong credentials.")
        except Exception as e:
            st.error(f"Login error: {e}")

def signup():
    st.subheader("Sign up")
    email = st.text_input("Email", key="signup_email")
    password = st.text_input("Password", type="password", key="signup_password")
    if st.button("Sign up"):
        try:
            user = supabase.auth.sign_up({"email": email, "password": password})
            st.session_state["user"] = user
            st.success("Signed up! Please check your email.")
            st.rerun()  # replaced deprecated experimental_rerun
        except Exception as e:
            st.error(f"Signup failed: {e}")

# --- Trip Posting ---
def post_trip(user_id):
    st.subheader("Post a Trip")

    if "departure_time" not in st.session_state:
        st.session_state.departure_time = datetime.datetime.now()

    start_postcode = st.text_input("Start Postal Code")
    start_number = st.text_input("Start House Number")
    end_postcode = st.text_input("End Postal Code")
    end_number = st.text_input("End House Number")

    departure_time = st.datetime_input("Departure Time", value=st.session_state.departure_time)
    st.session_state.departure_time = departure_time

    if st.button("Submit Trip"):
        try:
            start_address = f"{start_postcode} {start_number}, Netherlands"
            end_address = f"{end_postcode} {end_number}, Netherlands"
            start_location = geolocator.geocode(start_address)
            end_location = geolocator.geocode(end_address)

            if not start_location or not end_location:
                st.error("Could not find coordinates for one of the addresses.")
                return

            trip_data = {
                "user_id": user_id,
                "start_address": start_address,
                "start_lat": start_location.latitude,
                "start_lon": start_location.longitude,
                "end_address": end_address,
                "end_lat": end_location.latitude,
                "end_lon": end_location.longitude,
                "departure_time": departure_time.isoformat(),
            }

            supabase.table("trips").insert(trip_data).execute()
            st.success("Trip posted successfully!")
        except Exception as e:
            st.error(f"Error posting trip: {e}")

# --- Trip Viewer ---
def view_trips():
    st.subheader("Available Trips")

    try:
        response = supabase.table("trips").select("*").order("departure_time").execute()
        trips = response.data

        if not trips:
            st.info("No trips found.")
            return

        for trip in trips:
            st.markdown(f"**From:** {trip['start_address']}  \n**To:** {trip['end_address']}  \n**Departure:** {trip['departure_time']}")
            st.markdown("---")
    except Exception as e:
        st.error(f"Failed to load trips: {e}")

# --- Main ---
def main():
    st.title("🚗 Dutch Ridesharing Platform")

    menu = ["Login", "Sign Up", "View Trips", "Post Trip", "Logout"]
    choice = st.sidebar.selectbox("Menu", menu)

    user_session = st.session_state.get("user")
    logged_in = user_session and "user" in user_session

    if choice == "Login":
        if not logged_in:
            login()
        else:
            st.success("Already logged in!")
            st.write(f"Welcome, {user_session['user'].user_metadata['email']}")

    elif choice == "Sign Up":
        signup()

    elif choice == "View Trips":
        view_trips()

    elif choice == "Post Trip":
        if not logged_in:
            st.warning("You must be logged in to post a trip.")
            return
        user_id = user_session["user"]["id"]
        post_trip(user_id)

    elif choice == "Logout":
        st.session_state.clear()
        st.success("Logged out.")
        st.rerun()

if __name__ == "__main__":
    main()
