import sys
import datetime
import requests
import streamlit as st
from supabase import create_client
from geopy.geocoders import Nominatim
from shapely.geometry import LineString, Point
from pyproj import Transformer

# --- Supabase setup using Streamlit secrets ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
ORS_API_KEY = st.secrets["ORS_API_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
geolocator = Nominatim(user_agent="rideshare-app-nl")

# --- ORS Setup ---
ORS_URL = "https://api.openrouteservice.org/v2/directions/driving-car"

# Project lon/lat (EPSG:4326) -> Dutch RD New meters (EPSG:28992) for accurate distances
_to_m = Transformer.from_crs("EPSG:4326", "EPSG:28992", always_xy=True).transform
_to_ll = Transformer.from_crs("EPSG:28992", "EPSG:4326", always_xy=True).transform


def fetch_route_from_ors(start_lat, start_lon, end_lat, end_lon):
    """Fetch a route from ORS."""
    params = {
        "api_key": ORS_API_KEY,
        "start": f"{start_lon},{start_lat}",
        "end": f"{end_lon},{end_lat}",
    }
    r = requests.get(ORS_URL, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    feat = data["features"][0]
    coords = feat["geometry"]["coordinates"]  # [[lon,lat], ...]
    distance_m = int(round(feat["properties"]["summary"]["distance"]))
    duration_s = int(round(feat["properties"]["summary"]["duration"]))
    return coords, distance_m, duration_s


def linestring_meters_from_coords(coords_ll):
    coords_m = [_to_m(lon, lat) for lon, lat in coords_ll]
    return LineString(coords_m)


def point_meters(lon, lat):
    return Point(_to_m(lon, lat))


def rerun():
    sys.exit()


# --- Auth ---
def login():
    st.subheader("Login")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        try:
            result = supabase.auth.sign_in_with_password(
                {"email": email, "password": password}
            )
            if result.session:
                st.session_state["user"] = {
                    "id": result.user.id,
                    "email": result.user.email,
                }
                st.success("Logged in!")
                rerun()
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
            supabase.auth.sign_up({"email": email, "password": password})
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

    date = st.date_input(
        "Departure Date",
        value=st.session_state["rider_departure_date"],
        key="rider_date",
    )
    time = st.time_input(
        "Departure Time",
        value=st.session_state["rider_departure_time"],
        key="rider_time",
    )

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

            # Fetch ORS route
            coords, dist_m, dur_s = fetch_route_from_ors(
                start_lat=start_location.latitude,
                start_lon=start_location.longitude,
                end_lat=end_location.latitude,
                end_lon=end_location.longitude,
            )

            trip_data = {
                "user_id": user_id,
                "start_address": start_address,
                "start_lat": start_location.latitude,
                "start_lon": start_location.longitude,
                "end_address": end_address,
                "end_lat": end_location.latitude,
                "end_lon": end_location.longitude,
                "departure_time": departure_datetime.isoformat(),
                "route_geometry": {"type": "LineString", "coordinates": coords},
                "route_distance_m": dist_m,
                "route_duration_s": dur_s,
            }

            supabase.table("trips").insert(trip_data).execute()
            st.success("Rider trip posted successfully!")

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

    date = st.date_input(
        "Desired Pickup Date",
        value=st.session_state["passenger_departure_date"],
        key="passenger_date",
    )
    time = st.time_input(
        "Desired Pickup Time",
        value=st.session_state["passenger_departure_time"],
        key="passenger_time",
    )

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

            coords, dist_m, dur_s = fetch_route_from_ors(
                start_lat=pickup_location.latitude,
                start_lon=pickup_location.longitude,
                end_lat=dropoff_location.latitude,
                end_lon=dropoff_location.longitude,
            )

            passenger_trip_data = {
                "user_id": user_id,
                "pickup_address": pickup_address,
                "pickup_lat": pickup_location.latitude,
                "pickup_lon": pickup_location.longitude,
                "dropoff_address": dropoff_address,
                "dropoff_lat": dropoff_location.latitude,
                "dropoff_lon": dropoff_location.longitude,
                "desired_pickup_time": departure_datetime.isoformat(),
                "route_geometry": {"type": "LineString", "coordinates": coords},
                "route_distance_m": dist_m,
                "route_duration_s": dur_s,
            }

            supabase.table("passenger_trips").insert(passenger_trip_data).execute()
            st.success("Passenger trip posted successfully!")

            st.session_state["passenger_departure_date"] = datetime.date.today()
            st.session_state["passenger_departure_time"] = datetime.datetime.now().time()

        except Exception as e:
            st.error(f"Error posting passenger trip: {e}")


# --- Matching ---
def find_driver_matches_for_passenger(
    pickup_lat,
    pickup_lon,
    dropoff_lat,
    dropoff_lon,
    desired_pickup_dt,
    time_window_minutes=45,
    max_pickup_distance_m=600,
    max_dropoff_distance_m=600,
    limit=20,
):
    earliest = (desired_pickup_dt - datetime.timedelta(minutes=time_window_minutes)).isoformat()
    latest = (desired_pickup_dt + datetime.timedelta(minutes=time_window_minutes)).isoformat()

    resp = (
        supabase.table("trips")
        .select("*")
        .gte("departure_time", earliest)
        .lte("departure_time", latest)
        .limit(200)
        .execute()
    )
    drivers = resp.data or []

    p_pick_m = point_meters(pickup_lon, pickup_lat)
    p_drop_m = point_meters(dropoff_lon, dropoff_lat)

    matches = []
    for d in drivers:
        try:
            geom = d.get("route_geometry")
            if not geom or geom.get("type") != "LineString":
                continue
            coords_ll = geom.get("coordinates", [])
            if len(coords_ll) < 2:
                continue

            line_m = linestring_meters_from_coords(coords_ll)
            dist_pick = line_m.distance(p_pick_m)
            dist_drop = line_m.distance(p_drop_m)
            if dist_pick > max_pickup_distance_m or dist_drop > max_dropoff_distance_m:
                continue

            s_pick = line_m.project(p_pick_m)
            s_drop = line_m.project(p_drop_m)
            if s_drop <= s_pick:
                continue

            driver_dep = datetime.datetime.fromisoformat(d["departure_time"])
            td_min = abs((driver_dep - desired_pickup_dt).total_seconds()) / 60.0

            score = (dist_pick + dist_drop) * 0.002 + max(0, td_min - 10) * 0.5
            d["_match_score"] = round(score, 3)
            d["_pickup_distance_m"] = int(dist_pick)
            d["_dropoff_distance_m"] = int(dist_drop)
            d["_time_diff_min"] = int(round(td_min))
            d["_along_start_m"] = int(s_pick)
            d["_along_end_m"] = int(s_drop)

            matches.append(d)
        except Exception:
            continue

    matches.sort(key=lambda x: x["_match_score"])
    return matches[:limit]


def find_matches_view(user_id):
    st.subheader("Find Driver Matches for My Passenger Trip")
    q = (
        supabase.table("passenger_trips")
        .select("*")
        .eq("user_id", user_id)
        .order("desired_pickup_time")
        .execute()
    )
    my_trips = q.data or []
    if not my_trips:
        st.info("You have no passenger trips yet.")
        return

    trip_labels = [
        f"{t['pickup_address']} → {t['dropoff_address']} @ {t['desired_pickup_time']}"
        for t in my_trips
    ]
    idx = st.selectbox(
        "Select your trip", list(range(len(my_trips))), format_func=lambda i: trip_labels[i]
    )
    t = my_trips[idx]

    pickup_lat, pickup_lon = t["pickup_lat"], t["pickup_lon"]
    drop_lat, drop_lon = t["dropoff_lat"], t["dropoff_lon"]
    desired_dt = datetime.datetime.fromisoformat(t["desired_pickup_time"])

    time_window = st.slider("Time window (± minutes)", 10, 120, 45, 5)
    max_pick = st.slider("Max pickup distance (m)", 100, 2000, 600, 50)
    max_drop = st.slider("Max dropoff distance (m)", 100, 2000, 600, 50)

    if st.button("Find Matches"):
        with st.spinner("Matching..."):
            matches = find_driver_matches_for_passenger(
                pickup_lat,
                pickup_lon,
                drop_lat,
                drop_lon,
                desired_dt,
                time_window_minutes=time_window,
                max_pickup_distance_m=max_pick,
                max_dropoff_distance_m=max_drop,
                limit=20,
            )

        if not matches:
            st.warning("No matches found.")
            return

        st.success(f"Found {len(matches)} match(es):")
        for m in matches:
            st.markdown(
                f"""
**Driver trip**  
From: {m['start_address']}  
To: {m['end_address']}  
Departs: {m['departure_time']}  
Route distance: {m.get('route_distance_m','?')} m, duration: {m.get('route_duration_s','?')} s  

**Match details**  
• Pickup distance: {m['_pickup_distance_m']} m  
• Dropoff distance: {m['_dropoff_distance_m']} m  
• Time diff: {m['_time_diff_min']} min  
• Score: {m['_match_score']}  
---
"""
            )


# --- View Trips ---
def view_rider_trips():
    st.subheader("Available Rider Trips")
    try:
        response = supabase.table("trips").select("*").order("departure_time").execute()
        trips = response.data
        if not trips:
            st.info("No rider trips available.")
            return
        for trip in trips:
            st.markdown(
                f"""
**From:** {trip['start_address']}  
**To:** {trip['end_address']}  
**Departure:** {trip['departure_time']}
"""
            )
            st.markdown("---")
    except Exception as e:
        st.error(f"Failed to load rider trips: {e}")


def view_passenger_trips():
    st.subheader("Available Passenger Trips")
    try:
        response = (
            supabase.table("passenger_trips")
            .select("*")
            .order("desired_pickup_time")
            .execute()
        )
        trips = response.data
        if not trips:
            st.info("No passenger trips available.")
            return
        for trip in trips:
            st.markdown(
                f"""
**Pickup:** {trip['pickup_address']}  
**Dropoff:** {trip['dropoff_address']}  
**Desired Pickup:** {trip['desired_pickup_time']}
"""
            )
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
        "Find Matches",
        "Logout",
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
            st.warning("You must be logged in to post a passenger trip.")
        else:
            post_passenger_trip(user_id=user["id"])
    elif choice == "Find Matches":
        if not user:
            st.warning("You must be logged in to find matches.")
        else:
            find_matches_view(user_id=user["id"])
    elif choice == "Logout":
        st.session_state.clear()
        st.success("Logged out.")
        rerun()


if __name__ == "__main__":
    main()
