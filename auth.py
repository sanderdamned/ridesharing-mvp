import streamlit as st
from db import supabase

def login():
    st.title("Login or Register")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    action = st.radio("Action", ["Login", "Register"])
    
    if st.button(action):
        try:
            if action == "Login":
                user_response = supabase.auth.sign_in_with_password({"email": email, "password": password})
            else:
                user_response = supabase.auth.sign_up({"email": email, "password": password})
            user = user_response.user
            st.session_state.user = {"id": getattr(user, "id", None), "email": getattr(user, "email", None)}
            if st.session_state.user["id"]:
                st.success(f"{action} successful!")
                st.rerun()
            else:
                st.error(f"{action} failed. Check credentials.")
        except Exception as e:
            st.error(f"Error: {e}")
