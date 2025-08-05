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
            result = supabase.auth.sign_in_with_password({"email": email, "password": password})
            if result.session:
                st.session_state["user"] = {
                    "id": result.user.id,
                    "email": result.user.email,
                }
                st.success("Logged in!")
                st.rerun()
            else:
                st.error("Login failed. Email might not be confirmed.")
        except Exception as e:
            st.error(f"Login error: {e}")

def signup():
    st.subheader("Sign Up")
    email = st.text_input("Email", key="signup_email")
    password = st.text_input("Password", type="password", key="signup_password")

    if st.button("Sign Up"):
        try:
            result = supabase.auth.sign_up({"email": email, "password": password})
            st.success("Signed up! Check your email to confirm before logging in.")
        except Exception as e:
            st.error(f"Signup failed: {e}")

# --- Post Trip ---
def post_trip(user_id):
    st.subheader("Post a Trip")

    start_postcode = st.text_input("Start Postal Code")
    start_number = st.text_input("Start House Number")
    end_postcode = st.text_input("End Postal Code")
    end_number = st.text_input("End House Number")

    # Initialize departure_time in session state if not present
    if "departure_time" not in st.session_state:
        st.session_state["departure_time"] = datetime.datetime.now()

    departure_time = st.datetime_input("Departure Time", value=st.session_state["departure_time"])

    # Update session_state if changed
    if departure_time != st.session_state["departure_time"]:
        st.session_state["departure_time"] = departure_time

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
            # Reset departure_time after successful post
            st.session_state["departure_time"] = datetime.datetime.now()
        except Exception as e:
            st.error(f"Error posting trip: {e}")

# --- View Trips ---
def view_trips():
    st.subheader("Available Trips")
    try:
        response = supabase.table("trips").select("*").order("departure_time").execute()
        trips = response.data

        if not trips:
            st.info("No trips available.")
            return

        for trip in trips:
            st.markdown(f"""
            **From:** {trip['start_address']}  
            **To:** {trip['end_address']}  
            **Departure:** {trip['departure_time']}
            """)
            st.markdown("---")
    except Exception as e:
        st.error(f"Failed to load trips: {e}")

# --- Main App ---
def main():
    st.title("🚗 Dutch Ridesharing Platform")

    menu = ["Login", "Sign Up", "View Trips", "Post Trip", "Logout"]
    choice = st.sidebar.selectbox("Menu", menu)

    user = st.session_state.get("user")

    if choice == "Login":
        if user:
            st.success(f"Already logged in as {user['email']}")
        else:
            login()

    elif choice == "Sign Up":
        signup()

    elif choice == "View Trips":
        view_trips()

    elif choice == "Post Trip":
        if not user:
            st.warning("You must be logged in to post a trip.")
        else:
            post_trip(user_id=user["id"])

    elif choice == "Logout":
        st.session_state.clear()
        st.success("Logged out.")
        st.rerun()

if __name__ == "__main__":
    main()
