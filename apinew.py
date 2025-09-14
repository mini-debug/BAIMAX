import streamlit as st
import threading
import time
import json
import base64
import queue
import socket
import ssl
import websocket

from streamlit_webrtc import webrtc_streamer, AudioProcessorBase


# **** SETTINGS OF THE API KEY ****
# Put your real key in .streamlit/secrets.toml as:
OPENAI_KEY = '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'
WS_URL = "wss://api.openai.com/v1/realtime?model=gpt-4o-mini-realtime-preview-2024-12-17"
API_KEY = st.secrets['OPENAI_KEY']  # <-- FIXED API_KEY 
# **** STATE **** 

if "is_speaking" not in st.session_state:  
    st.session_state.is_speaking = False
if "stop_event" not in st.session_state:
    st.session_state.stop_event = threading.Event()
if "messages" not in st.session_state:
    st.session_state.messages = []
if "ws" not in st.session_state:
    st.session_state.ws = None

audio_queue = queue.Queue()

# **** HELPER FUNCTION: The Baymax Face ****
def draw_baymax_face(is_speaking: bool):
    # Darker eyes when speaking
    eye_color = "#676867" if is_speaking else "#000000"

    html = f"""
    <div style="
        width:600px;
        height:300px;
        background:#EBEBEB;
        display:flex;
        flex-direction:column;
        align-items:center;
        justify-content:center;
        border-radius:20px;">
        
        <!-- Eyes -->
        <div style="display:flex;align-items:center;justify-content:center;">
            <div style="
                width:60px;
                height:60px;
                border-radius:50%;
                background:{eye_color};
                margin-right:150px;">
            </div>
            <div style="
                width:60px;
                height:60px;
                border-radius:50%;
                background:{eye_color};">
            </div>
        </div>

        <!-- Mouth/Connector -->
        <div style="
            width:200px;
            height:10px;
            background:{eye_color};
            margin-top:10px;">
        </div>
    </div>
    """
    return html

