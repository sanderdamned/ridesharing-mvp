from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def insert_ride(ride: dict):
    return supabase.table("rides").insert(ride).execute()

def insert_passenger(passenger: dict):
    return supabase.table("passengers").insert(passenger).execute()

def get_rides():
    return supabase.table("rides").select("*").execute().data

def get_passengers(user_id=None):
    query = supabase.table("passengers").select("*")
    if user_id:
        query = query.eq("user_id", user_id)
    return query.execute().data
