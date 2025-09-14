import streamlit as st
from threading import Thread
from gemini_module import query_gemini
from calendar_module import get_upcoming_events
from heart_rate_module import get_bpm
from bavoice3 import start_voice_interaction_ui
import baymax_ai_face

# Streamlit page configuration
st.set_page_config(
    page_title="Baymax Assistant",
    layout="wide"
)

# Title
st.title("🤖 Baymax - Your Personal Healthcare Assistant")

# Create tabs
tab1, tab2, tab3, tab4 = st.tabs([
    "Gemini Assistant",
    "Google Calendar",
    "Heart Rate Monitor",
    "Voice Assistant"
])

# === TAB 1: Gemini Assistant ===
with tab1:
    st.header("🧠 Gemini AI Assistant")
    prompt = st.text_area("Ask something:", placeholder="e.g., What are symptoms of flu?")

    if st.button("Send to Gemini"):
        if prompt.strip():
            with st.spinner("Thinking..."):
                try:
                    response = query_gemini(prompt)
                    st.markdown("### 💬 Response")
                    st.write(response)
                except Exception as e:
                    st.error(f"Error: {e}")
        else:
            st.warning("Please enter a prompt.")

# === TAB 2: Google Calendar ===
with tab2:
    st.header("📅 Upcoming Events")
    try:
        events = get_upcoming_events()
        if events:
            for event in events:
                st.write(f"- **{event['start']}**: {event['summary']}")
        else:
            st.info("No upcoming events found.")
    except Exception as e:
        st.error(f"Error fetching calendar events: {e}")

# === TAB 3: Heart Rate Monitor ===
with tab3:
    st.header("❤️ Heart Rate Monitor")

    bpm_placeholder = st.empty()

    def run_bpm():
        try:
            bpm = get_bpm()
            bpm_placeholder.metric("Heart Rate", f"{bpm:.2f} BPM")
        except Exception as e:
            st.error(f"Error measuring heart rate: {e}")

    if st.button("Start BPM Scan"):
        Thread(target=run_bpm, daemon=True).start()

# === TAB 4: Voice Assistant ===
with tab4:
    st.header("🎙️ Baymax Voice Assistant")

    # Session flag to control assistant visibility
    if "show_voice_assistant" not in st.session_state:
        st.session_state.show_voice_assistant = False

    if st.button("Start Voice Assistant"):
        st.session_state.show_voice_assistant = True

    if st.session_state.show_voice_assistant:
        from bavoice3 import start_voice_interaction_ui
        start_voice_interaction_ui()

