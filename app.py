import streamlit as st
import requests
from datetime import datetime, time
from functools import lru_cache
import math
import time as pytime

# ===========================
# CONFIG / INIT
# ===========================
st.set_page_config(page_title="Ridesharing MVP", layout="centered")

NHOST_AUTH_URL = st.secrets.get("NHOST_AUTH_URL")
NHOST_GRAPHQL_URL = st.secrets.get("NHOST_GRAPHQL_URL")
NHOST_KEY = st.secrets.get("NHOST_ADMIN_SECRET")
ORS_API_KEY = st.secrets.get("ORS_API_KEY")  # optional

if not NHOST_AUTH_URL or not NHOST_GRAPHQL_URL or not NHOST_KEY:
    st.error("Missing Nhost secrets. Add NHOST_AUTH_URL, NHOST_GRAPHQL_URL, and NHOST_ADMIN_SECRET in Streamlit Cloud Secrets.")
    st.stop()

# ===========================
# HELPERS
# ===========================
def format_departure(dep):
    if isinstance(dep, time):
        return dep.strftime("%H:%M:%S")
    if isinstance(dep, str):
        try:
            dt = datetime.strptime(dep, "%H:%M")
            return dt.strftime("%H:%M:%S")
        except ValueError:
            return dep
    return str(dep)

@lru_cache(maxsize=1000)
def geocode_postcode_cached(postcode: str, retries=2):
    if not ORS_API_KEY:
        return []
    url = "https://api.openrouteservice.org/geocode/search"
    params = {"api_key": ORS_API_KEY, "text": postcode, "boundary.country": "NL"}
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, timeout=5)
            r.raise_for_status()
            data = r.json()
            coords = data["features"][0]["geometry"]["coordinates"]  # [lon, lat]
            return [float(coords[1]), float(coords[0])]
        except Exception:
            if attempt < retries:
                pytime.sleep(1)
                continue
            return []

def route_distance_time(start, end):
    if not ORS_API_KEY:
        return None, None
    try:
        url = "https://api.openrouteservice.org/v2/directions/driving-car"
        headers = {"Authorization": ORS_API_KEY}
        body = {"coordinates": [[start[1], start[0]], [end[1], end[0]]]}
        r = requests.post(url, json=body, headers=headers, timeout=6)
        r.raise_for_status()
        data = r.json()
        dist = data["routes"][0]["summary"]["distance"] / 1000
        dur = data["routes"][0]["summary"]["duration"] / 60
        return dist, dur
    except Exception:
        return None, None

def haversine_km(a, b):
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    R = 6371.0
    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(h))

# ===========================
# NHOST AUTH / GRAPHQL
# ===========================
def nhost_sign_up(email, password):
    url = f"{NHOST_AUTH_URL}/signup/email-password"
    r = requests.post(url, json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()

def nhost_sign_in(email, password):
    url = f"{NHOST_AUTH_URL}/signin/email-password"
    r = requests.post(url, json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()

def nhost_sign_out(refresh_token):
    url = f"{NHOST_AUTH_URL}/signout"
    headers = {"Authorization": f"Bearer {refresh_token}"}
    r = requests.post(url, headers=headers)
    return r.ok

def nhost_graphql(query, variables=None, admin_secret=None):
    headers = {"x-hasura-admin-secret": admin_secret} if admin_secret else {}
    json_payload = {"query": query}
    if variables:
        json_payload["variables"] = variables
    r = requests.post(NHOST_GRAPHQL_URL, json=json_payload, headers=headers)
    r.raise_for_status()
    return r.json()

# ===========================
# SESSION
# ===========================
if "user" not in st.session_state:
    st.session_state.user = None
if "access_token" not in st.session_state:
    st.session_state.access_token = None

def normalize_user(user_obj):
    if not user_obj:
        return None
    uid = user_obj.get("id")
    email = user_obj.get("email")
    return {"id": uid, "email": email}

def show_login():
    st.title("Login or Register")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    action = st.radio("Action", ["Login", "Register"])
    if st.button(action):
        try:
            if action == "Login":
                resp = nhost_sign_in(email, password)
                user = resp.get("user")
                st.session_state.access_token = resp.get("session", {}).get("access_token")
            else:
                resp = nhost_sign_up(email, password)
                user = resp.get("user")
                st.success("Registration successful. Please log in.")
                return
            st.session_state.user = normalize_user(user)
            if st.session_state.user:
                st.experimental_rerun()
            else:
                st.error("Auth failed. Check credentials.")
        except Exception as e:
            st.error(f"Auth error: {e}")

if not st.session_state.user:
    show_login()
    st.stop()

# ===========================
# DB HELPERS
# ===========================
def insert_table_row(table_name: str, payload: dict):
    def format_array(arr):
        return f"[{','.join(str(x) for x in arr)}]" if arr else "[]"

    payload_copy = payload.copy()
    for key in ["origin_coords", "dest_coords"]:
        if key in payload_copy and payload_copy[key]:
            payload_copy[key] = format_array(payload_copy[key])
        else:
            payload_copy[key] = "[]"

    fields = ", ".join(
        f"{k}: {v}" if isinstance(v, (int, float)) else f'{k}: "{v}"'
        for k, v in payload_copy.items()
    )
    query = f"""
    mutation {{
        insert_{table_name}(objects: {{ {fields} }}) {{
            returning {{ id }}
        }}
    }}
    """
    try:
        res = nhost_graphql(query, admin_secret=NHOST_KEY)
        if "errors" in res:
            raise Exception(res["errors"])
        return res.get("data")
    except Exception as e:
        st.error(f"Insert error: {e}")
        return None

def get_rides():
    query = """
    query {
        rides {
            id user_id origin destination departure
            origin_coords dest_coords max_extra_km max_extra_min
        }
    }
    """
    try:
        res = nhost_graphql(query, admin_secret=NHOST_KEY)
        return res.get("data", {}).get("rides", [])
    except Exception as e:
        st.error(f"Failed fetching rides: {e}")
        return []

def get_passengers(user_id=None):
    where_clause = f'(where: {{user_id: {{_eq: "{user_id}"}}}})' if user_id else ""
    query = f"""
    query {{
        passengers{where_clause} {{
            id user_id origin destination departure
            origin_coords dest_coords
        }}
    }}
    """
    try:
        res = nhost_graphql(query, admin_secret=NHOST_KEY)
        return res.get("data", {}).get("passengers", [])
    except Exception as e:
        st.error(f"Failed fetching passengers: {e}")
        return []

# ===========================
# MAIN UI
# ===========================
st.sidebar.title(f"Welcome, {st.session_state.user.get('email')}")
if st.sidebar.button("Log out"):
    st.session_state.user = None
    st.session_state.access_token = None
    st.experimental_rerun()

view = st.sidebar.radio("Go to", ["Post Ride", "Post Passenger", "Find Matches", "Debug"])

# ---------- Post Ride ----------
if view == "Post Ride":
    st.title("Post a Ride (Driver)")
    with st.form("ride_form"):
        origin = st.text_input("Origin Postcode (NL)")
        destination = st.text_input("Destination Postcode (NL)")
        departure = st.time_input("Departure Time", value=datetime.now().time())
        max_extra_km = st.number_input("Max extra distance (km)", 0.0, 100.0, 5.0, step=0.5)
        max_extra_min = st.number_input("Max extra time (minutes)", 0, 240, 15, step=5)
        submit = st.form_submit_button("Submit Ride")

    if submit:
        origin_coords = geocode_postcode_cached(origin)
        dest_coords = geocode_postcode_cached(destination)
        payload = {
            "user_id": st.session_state.user["id"],
            "origin": origin.strip().upper(),
            "destination": destination.strip().upper(),
            "departure": format_departure(departure),
            "origin_coords": origin_coords,
            "dest_coords": dest_coords,
            "max_extra_km": float(max_extra_km),
            "max_extra_min": int(max_extra_min),
            "created_at": datetime.utcnow().isoformat(),
        }
        res = insert_table_row("rides", payload)
        if res: st.success("Ride posted!")

# ---------- Post Passenger ----------
elif view == "Post Passenger":
    st.title("Post a Passenger Request")
    with st.form("passenger_form"):
        origin = st.text_input("Origin Postcode (NL)")
        destination = st.text_input("Destination Postcode (NL)")
        departure = st.time_input("Departure Time", value=datetime.now().time())
        submit = st.form_submit_button("Submit Request")

    if submit:
        origin_coords = geocode_postcode_cached(origin)
        dest_coords = geocode_postcode_cached(destination)
        payload = {
            "user_id": st.session_state.user["id"],
            "origin": origin.strip().upper(),
            "destination": destination.strip().upper(),
            "departure": format_departure(departure),
            "origin_coords": origin_coords,
            "dest_coords": dest_coords,
            "created_at": datetime.utcnow().isoformat(),
        }
        res = insert_table_row("passengers", payload)
        if res: st.success("Passenger request posted!")

# ---------- Find Matches ----------
elif view == "Find Matches":
    st.title("Find Matches (Detour-based)")
    passengers = get_passengers(st.session_state.user["id"])
    rides = get_rides()
    if not passengers:
        st.info("You need to post a passenger request first.")
    else:
        passenger = passengers[-1]
        st.write(f"Passenger: {passenger.get('origin')} → {passenger.get('destination')}")
        matches = []
        for ride in rides:
            if not ride.get("origin_coords") or not ride.get("dest_coords"):
                continue
            base_dist, _ = route_distance_time(ride["origin_coords"], ride["dest_coords"])
            if base_dist is None:
                continue
            d1, _ = route_distance_time(ride["origin_coords"], passenger["origin_coords"])
            d2, _ = route_distance_time(passenger["origin_coords"], passenger["dest_coords"])
            d3, _ = route_distance_time(passenger["dest_coords"], ride["dest_coords"])
            if None in (d1, d2, d3):
                continue
            detour_dist = d1 + d2 + d3
            extra_dist = detour_dist - base_dist
            if extra_dist <= ride.get("max_extra_km", 999):
                matches.append((ride, extra_dist))
        if matches:
            st.subheader("Matching Rides:")
            for ride, ex_d in matches:
                st.write(f"🚗 {ride.get('origin')} → {ride.get('destination')} at {ride.get('departure')}")
                st.write(f"   Extra distance: {ex_d:.1f} km (max {ride.get('max_extra_km')})")
        else:
            st.warning("No suitable matches found.")

# ---------- Debug ----------
elif view == "Debug":
    st.title("Debug Info")
    st.json(st.session_state.user)
    if st.button("List rides"): st.json(get_rides())
    if st.button("List my passengers"): st.json(get_passengers(st.session_state.user["id"]))
