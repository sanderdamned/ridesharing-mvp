import streamlit as st
from supabase import create_client
from geopy.geocoders import Nominatim
import datetime

# --- Supabase setup using Streamlit secrets ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
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
                st.experimental_rerun()
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

# --- Post Rider Trip ---
def post_rider_trip(user_id):
    st.subheader("Post a Rider Trip (Offer a Ride)")

    start_postcode = st.text_input("Start Postal Code", key="rider_start_postcode")
    start_number = st.text_input("Start House Number", key="rider_start_number")
    end_postcode = st.text_input("End Postal Code", key="rider_end_postcode")
    end_number = st.text_input("End House Number", key="rider_end_number")

    if "rider_departure_date" not in st.session_state:
        st.session_state["rider_departure_date"] = datetime.date.today()
    if "rider_departure_time" not in st.session_state:
        st.session_state["rider_departure_time"] = datetime.datetime.now().time()

    date = st.date_input("Departure Date", value=st.session_state["rider_departure_date"], key="rider_date")
    time = st.time_input("Departure Time", value=st.session_state["rider_departure_time"], key="rider_time")

    departure_datetime = datetime.datetime.combine(date, time)

    if st.button("Submit Rider Trip"):
        try:
            start_address = f"{start_postcode} {start_number}, Netherlands"
            end_address = f"{end_postcode} {end_number}, Netherlands"

            start_location = geolocator.geocode(start_address, timeout=5)
            end_location = geolocator.geocode(end_address, timeout=5)

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
                "departure_time": departure_datetime.isoformat(),
            }

            supabase.table("trips").insert(trip_data).execute()
            st.success("Rider trip posted successfully!")

            # Reset session state
            st.session_state["rider_departure_date"] = datetime.date.today()
            st.session_state["rider_departure_time"] = datetime.datetime.now().time()

        except Exception as e:
            st.error(f"Error posting rider trip: {e}")

# --- Post Passenger Trip ---
def post_passenger_trip(user_id):
    st.subheader("Post a Passenger Trip (Request a Ride)")

    pickup_postcode = st.text_input("Pickup Postal Code", key="passenger_pickup_postcode")
    pickup_number = st.text_input("Pickup House Number", key="passenger_pickup_number")
    dropoff_postcode = st.text_input("Dropoff Postal Code", key="passenger_dropoff_postcode")
    dropoff_number = st.text_input("Dropoff House Number", key="passenger_dropoff_number")

    if "passenger_departure_date" not in st.session_state:
        st.session_state["passenger_departure_date"] = datetime.date.today()
    if "passenger_departure_time" not in st.session_state:
        st.session_state["passenger_departure_time"] = datetime.datetime.now().time()

    date = st.date_input("Desired Pickup Date", value=st.session_state["passenger_departure_date"], key="passenger_date")
    time = st.time_input("Desired Pickup Time", value=st.session_state["passenger_departure_time"], key="passenger_time")

    departure_datetime = datetime.datetime.combine(date, time)

    if st.button("Submit Passenger Trip"):
        try:
            pickup_address = f"{pickup_postcode} {pickup_number}, Netherlands"
            dropoff_address = f"{dropoff_postcode} {dropoff_number}, Netherlands"

            pickup_location = geolocator.geocode(pickup_address, timeout=5)
            dropoff_location = geolocator.geocode(dropoff_address, timeout=5)

            if not pickup_location or not dropoff_location:
                st.error("Could not find coordinates for one of the addresses.")
                return

            passenger_trip_data = {
                "user_id": user_id,
                "pickup_address": pickup_address,
                "pickup_lat": pickup_location.latitude,
                "pickup_lon": pickup_location.longitude,
                "dropoff_address": dropoff_address,
                "dropoff_lat": dropoff_location.latitude,
                "dropoff_lon": dropoff_location.longitude,
                "desired_pickup_time": departure_datetime.isoformat(),
            }

            supabase.table("passenger_trips").insert(passenger_trip_data).execute()
            st.success("Passenger trip posted successfully!")

            # Reset session state
            st.session_state["passenger_departure_date"] = datetime.date.today()
            st.session_state["passenger_departure_time"] = datetime.datetime.now().time()

        except Exception as e:
            st.error(f"Error posting passenger trip: {e}")

# --- View Rider Trips ---
def view_rider_trips():
    st.subheader("Available Rider Trips (Offers)")
    try:
        response = supabase.table("trips").select("*").order("departure_time").execute()
        trips = response.data

        if not trips:
            st.info("No rider trips available.")
            return

        for trip in trips:
            st.markdown(f"""
            **From:** {trip['start_address']}  
            **To:** {trip['end_address']}  
            **Departure:** {trip['departure_time']}
            """)
            st.markdown("---")
    except Exception as e:
        st.error(f"Failed to load rider trips: {e}")

# --- View Passenger Trips ---
def view_passenger_trips():
    st.subheader("Available Passenger Trips (Requests)")
    try:
        response = supabase.table("passenger_trips").select("*").order("desired_pickup_time").execute()
        trips = response.data

        if not trips:
            st.info("No passenger trips available.")
            return

        for trip in trips:
            st.markdown(f"""
            **Pickup:** {trip['pickup_address']}  
            **Dropoff:** {trip['dropoff_address']}  
            **Desired Pickup:** {trip['desired_pickup_time']}
            """)
            st.markdown("---")
    except Exception as e:
        st.error(f"Failed to load passenger trips: {e}")

# --- Main App ---
def main():
    st.title("🚗 Dutch Ridesharing Platform")

    menu = [
        "Login",
        "Sign Up",
        "View Rider Trips",
        "Post Rider Trip",
        "View Passenger Trips",
        "Post Passenger Trip",
        "Logout"
    ]
    choice = st.sidebar.selectbox("Menu", menu)

    user = st.session_state.get("user")

    if choice == "Login":
        if user:
            st.success(f"Already logged in as {user['email']}")
        else:
            login()

    elif choice == "Sign Up":
        signup()

    elif choice == "View Rider Trips":
        view_rider_trips()

    elif choice == "Post Rider Trip":
        if not user:
            st.warning("You must be logged in to post a rider trip.")
        else:
            post_rider_trip(user_id=user["id"])

    elif choice == "View Passenger Trips":
        view_passenger_trips()

    elif choice == "Post Passenger Trip":
        if not user:
            st.warning("You must be logged in to
