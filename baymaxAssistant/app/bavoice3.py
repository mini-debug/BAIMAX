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
WS_URL = "wss://api.openai.com/v1/realtime?model=gpt-4o-mini-realtime-preview-2024-12-17"
API_KEY = st.secrets.get("OPENAI_KEY", "sk-YOURKEY")  # We have to put our key in .streamlit/secrets.toml       

# **** STATE **** 
if "is_speaking" not in st.session_state:  # 
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
    eye_color = "#000000" if not is_speaking else "#676867"
    html = f"""
    <div style='width:600px;height:300px;background:#EBEBEB;display:flex;flex-direction:column;align-items:center;justify-content:center;border-radius:20px;'>
        <div style='display:flex;align-items:center;justify-content:center;'>
            <div style='width:60px;height:60px;border-radius:50%;background:{eye_color};margin-right:150px;'></div>
            <div style='width:60px;height:60px;border-radius:50%;background:{eye_color};'></div>
        </div>
        <div style='width:200px;height:10px;background:{eye_color};margin-top:10px;'></div>
    </div>
    """
    return html

# **** WEBSOCKET SETUP ****
def create_connection_with_ipv4(*args, **kwargs):
    original_getaddrinfo = socket.getaddrinfo
    def getaddrinfo_ipv4(host, port, family=socket.AF_INET, *args):
        return original_getaddrinfo(host, port, socket.AF_INET, *args)
    socket.getaddrinfo = getaddrinfo_ipv4
    try:
        return websocket.create_connection(*args, **kwargs)
    finally:
        socket.getaddrinfo = original_getaddrinfo

def send_fc_session_update(ws):
    session_config = {
        "type": "session.update",
        "session": {
            "instructions": "You are Baymax, a friendly healthcare companion.",
            "voice": "alloy",
            "temperature": 1,
            "modalities": ["text", "audio"],
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "input_audio_transcription": {
                "model": "whisper-1"
            }
        }
    }
    ws.send(json.dumps(session_config))

def receive_from_openai(ws):
    """Receive events and update state."""
    while not st.session_state.stop_event.is_set():
        try:
            message = ws.recv()
            if not message:
                continue
            message = json.loads(message)
            event_type = message.get("type", "")
            if event_type == "session.created":
                send_fc_session_update(ws)
                intro_message = json.dumps({
                    "type": "response.create",
                    "response": {
                        "instructions": "Hello, I am Baymax, your personal healthcare companion."
                    }
                })
                ws.send(intro_message)

            elif event_type == "response.audio.delta":
                st.session_state.is_speaking = True

            elif event_type == "response.audio.done":
                st.session_state.is_speaking = False

            elif event_type == "response.audio_transcript.delta":
                delta = message['delta']
                st.session_state.messages.append(delta)

            elif event_type == "response.audio_transcript.done":
                transcript = message['transcript']
                st.session_state.messages.append(transcript)

        except Exception as e:
            st.session_state.messages.append(f"WebSocket error: {e}")
            break

def connect_to_openai():
    try:
        ws = create_connection_with_ipv4(
            WS_URL,
            header=[
                f'Authorization: Bearer {API_KEY}',
                'OpenAI-Beta: realtime=v1'
            ],
            sslopt={"cert_reqs": ssl.CERT_NONE}
        )
        st.session_state.ws = ws
        t = threading.Thread(target=receive_from_openai, args=(ws,), daemon=True)
        t.start()
        st.session_state.messages.append("Connected to OpenAI realtime WebSocket.")
    except Exception as e:
        st.session_state.messages.append(f"Failed to connect to OpenAI: {e}")

def send_audio_to_openai():
    """Send mic chunks to OpenAI."""
    while not st.session_state.stop_event.is_set():
        try:
            mic_chunk = audio_queue.get(timeout=1)
        except:
            continue
        if st.session_state.ws:
            encoded_chunk = base64.b64encode(mic_chunk).decode('utf-8')
            message = json.dumps({
                'type': 'input_audio_buffer.append',
                'audio': encoded_chunk
            })
            try:
                st.session_state.ws.send(message)
            except Exception as e:
                st.session_state.messages.append(f"Error sending audio: {e}")

# **** AUDIO PROCESSOR ****
class AudioProcessor(AudioProcessorBase):
    def recv_audio(self, frame):
        # frame: av.AudioFrame
        pcm = frame.to_ndarray().tobytes()
        audio_queue.put(pcm)
        return frame

# **** STREAMLIT UI ****
st.title("Baymax AI — Full Browser Version")

# Baymax Face
st.markdown(draw_baymax_face(st.session_state.is_speaking), unsafe_allow_html=True)

# Buttons
col1, col2 = st.columns(2)
with col1:
    if st.button("Connect to OpenAI"):
        connect_to_openai()
        threading.Thread(target=send_audio_to_openai, daemon=True).start()
with col2:
    if st.button("Stop"):
        st.session_state.stop_event.set()
        if st.session_state.ws:
            try:
                st.session_state.ws.close()
            except:
                pass

# Microphone via WebRTC
webrtc_streamer(key="mic", audio_processor_factory=AudioProcessor, media_stream_constraints={"audio": True, "video": False})

# Live transcript
st.subheader("Live Transcript:")
for m in st.session_state.messages[-15:]:
    st.write(m)
