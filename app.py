import streamlit as st
from supabase import create_client, Client

# Replace with your Supabase project URL and anon key
SUPABASE_URL = "https://ivzlapmdomoxwzwptixb.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Iml2emxhcG1kb21veHd6d3B0aXhiIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQzMzA1MDgsImV4cCI6MjA2OTkwNjUwOH0.tgjQ_RBX-62xlJv7RuugHrPuz7XxINHhc2zYF7laMGE"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("🔐 Supabase Auth Test App")

# Show session user info if logged in
if "user" in st.session_state:
    st.success("Logged in as:")
    st.json(st.session_state["user"])
    if st.button("Logout"):
        del st.session_state["user"]
        st.rerun()

else:
    # Tabs for login and signup
    tab1, tab2 = st.tabs(["🔐 Login", "🆕 Signup"])

    with tab1:
        st.subheader("Login")
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Login"):
            try:
                user = supabase.auth.sign_in_with_password({"email": email, "password": password})
                st.write("DEBUG: Login response:", user)
                if user.session:
                    st.session_state["user"] = user
                    st.rerun()
                else:
                    st.error("Login failed: No session returned.")
            except Exception as e:
                st.error(f"Login error: {e}")

    with tab2:
        st.subheader("Signup")
        new_email = st.text_input("Email", key="signup_email")
        new_password = st.text_input("Password", type="password", key="signup_password")
        if st.button("Signup"):
            try:
                user = supabase.auth.sign_up({"email": new_email, "password": new_password})
                st.success("Signup successful. Please check your email to confirm.")
                st.write("DEBUG: Signup response:", user)
            except Exception as e:
                st.error(f"Signup error: {e}")
