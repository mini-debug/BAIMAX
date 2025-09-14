import streamlit as st
from gemini_module import query_gemini
from calendar_module import get_upcoming_events
from heart_rate_module import get_bpm
from threading import Thread

st.set_page_config("Baymax Assistant", layout="wide")
st.title("🤖 Baymax Personal Health Assistant")

tab1, tab2, tab3 = st.tabs(["💬 Chat", "📅 Calendar", "❤️ Heart Rate"])

with tab1:
    st.header("Chat with Baymax")
    user_input = st.text_input("You:")
    if user_input:
        response = query_gemini(user_input)
        st.success(response)

with tab2:
    st.header("Upcoming Events")
    for event in get_upcoming_events():
        st.write(f"- **{event['start']}**: {event['summary']}")

with tab3:
    st.header("Heart Rate Monitor")
    bpm_placeholder = st.empty()

    def run_bpm():
        bpm = get_bpm()
        bpm_placeholder.metric("Heart Rate", f"{bpm:.2f} BPM")

    if st.button("Start BPM Scan"):
        Thread(target=run_bpm).start()
