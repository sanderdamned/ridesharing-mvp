payload = {
    "user_id": st.session_state.user["id"],
    "origin": origin,
    "destination": destination,
    "departure": str(departure),
    "origin_coords": origin_coords,
    "dest_coords": dest_coords,
    "max_extra_km": float(max_extra_km),
    "max_extra_min": int(max_extra_min)
}
st.write("DEBUG payload:", payload)

supabase.table("rides").insert(payload).execute()

