import struct  # For unpacking binary audio data
import numpy as np  # For audio signal processing
import base64  # For Base64 encoding/decoding and audio data encoding transmission
import json  # Handling JSON format data exchange
import queue  # Thread-safe queue for microphone data buffering
import socket  # Network socket operations
import ssl  # SSL/TLS encryption support
import threading  # Multithreading support
import time  # Time-related operations
#import azure.cognitiveservices.speech as speechsdk # Speech Services Azure

import pyaudio  # Audio input/output processing
import socks  # SOCKS proxy support
import websocket  # WebSocket client
from websocket import create_connection

import pygame  # For Baymax face GUI
import sys

# Set SOCKS5 proxy (globally replaces socket implementation)
socket.socket = socks.socksocket

# OpenAI API
API_KEY = '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'

# WebSocket server URL (real-time speech conversion interface)
WS_URL = 'wss://api.openai.com/v1/realtime?model=gpt-4o-mini-realtime-preview-2024-12-17'

# Audio stream parameter configuration
CHUNK_SIZE = 2048  # Size of each processed audio data chunk (bytes)
RATE = 24000  # Audio sampling rate (Hz)
FORMAT = pyaudio.paInt16  # Audio format (16-bit integer PCM)

# Global variable definitions

is_speaking = False  # Flag to indicate when assistant is speaking
VOLUME_THRESHOLD_DB = -35  # Minimum volume in dB to consider as speech
audio_buffer = bytearray()  # Stores received audio data (for speaker playback)
mic_queue = queue.Queue()  # Thread-safe queue for microphone data collection

stop_event = threading.Event()  # Thread stop event flag

mic_on_at = 0  # Microphone activation timestamp (for echo cancellation)
mic_active = None  # Current microphone status record
REENGAGE_DELAY_MS = 500  # Microphone re-engagement delay time (milliseconds)


def draw_baymax_face(screen, is_speaking):
    """Draw Baymax's face with changing eye color when speaking."""
    screen.fill((235, 235, 235))  # White background

    # Eyes
    eye_color = (0, 0, 0) if not is_speaking else (0, 100, 200)  # Black or Blue
    pygame.draw.circle(screen, eye_color, (200, 200), 30)  # Left eye
    pygame.draw.circle(screen, eye_color, (400, 200), 30)  # Right eye

    # Line between eyes
    pygame.draw.line(screen, eye_color, (230, 200), (370, 200), 10)

    pygame.display.flip()


def baymax_face_loop(stop_event):
    """Run the Baymax face animation in its own thread."""
    global is_speaking

    pygame.init()
    screen = pygame.display.set_mode((600, 400))
    pygame.display.set_caption("Baymax AI")

    clock = pygame.time.Clock()
    while not stop_event.is_set():
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                stop_event.set()
                pygame.quit()
                sys.exit()

        draw_baymax_face(screen, is_speaking)
        clock.tick(30)


def read_txt_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        return content
    except FileNotFoundError:
        print(f"Error: File {file_path} not found")
        return None
    except Exception as e:
        print(f"Error reading file: {e}")
        return None

# Clears audio buffer could be commented out when neede

# def clear_audio_buffer():
#     global audio_buffer
#     audio_buffer = bytearray()
#     print('* Audio buffer cleared')


# def stop_audio_playback():
#     global is_playing
#     is_playing = False
#     print('* Audio playback stopped')


def mic_callback(in_data, frame_count, time_info, status):
    global mic_on_at, mic_active

    if mic_active != True:
        print(':) Microphone activated')
        mic_active = True

    mic_queue.put(in_data)

    if time.time() > mic_on_at:
        if mic_active != True:
            print(':) Microphone activated')
            mic_active = True
        mic_queue.put(in_data)
    else:
        if mic_active != False:
            print('Womp, Womp Microphone muted')
            mic_active = False

    return (None, pyaudio.paContinue)


def send_mic_audio_to_websocket(ws):
    try:
        while not stop_event.is_set():
            if not mic_queue.empty():
                mic_chunk = mic_queue.get()
                encoded_chunk = base64.b64encode(mic_chunk).decode('utf-8')
                message = json.dumps({
                    'type': 'input_audio_buffer.append',
                    'audio': encoded_chunk
                })
                try:
                    ws.send(message)
                except Exception as e:
                    print(f'Error sending microphone audio: {e}')
    except Exception as e:
        print(f'Microphone data sending thread exception: {e}')
    finally:
        print('Microphone data sending thread exited')


def speaker_callback(in_data, frame_count, time_info, status):
    global audio_buffer, mic_on_at, is_speaking

    bytes_needed = frame_count * 2
    current_buffer_size = len(audio_buffer)

    if current_buffer_size >= bytes_needed:
        audio_chunk = bytes(audio_buffer[:bytes_needed])
        audio_buffer = audio_buffer[bytes_needed:]
        mic_on_at = time.time() + REENGAGE_DELAY_MS / 1000
        is_speaking = True
    else:
        audio_chunk = bytes(audio_buffer) + b'\x00' * (bytes_needed - current_buffer_size)
        audio_buffer.clear()
        is_speaking = False

    return (audio_chunk, pyaudio.paContinue)


def receive_audio_from_websocket(ws):
    global audio_buffer

    try:
        while not stop_event.is_set():
            info = None
            try:
                message = ws.recv()
                if not message:
                    print('⚙️ Received empty message (connection may be closed)')
                    continue

                message = json.loads(message)
                info = message
                event_type = message['type']
                print(f'⚡️ Received WebSocket event: {event_type}')

                if event_type == 'session.created':
                    send_fc_session_update(ws)
                    # Make Baymax introduce himself automatically
                    intro_message = json.dumps({
                        "type": "response.create",
                        "response": {
                            "instructions": "Hello, I am Baymax, your personal healthcare companion."
                        }
                    })
                    ws.send(intro_message)

                elif event_type == 'response.audio.delta':
                    audio_content = base64.b64decode(message['delta'])
                    audio_buffer.extend(audio_content)
                    print(f' Received {len(audio_content)} bytes audio, total buffer size: {len(audio_buffer)}')

                elif event_type == 'input_audio_buffer.speech_started':
                    print(' Speech start detected, clearing buffer and stopping playback')
                    clear_audio_buffer()
                    stop_audio_playback()

                elif event_type == 'response.audio.done':
                    is_speaking = False
                    print(' AI speech ended')

                elif event_type == 'response.audio_transcript.delta':
                    delta = message['delta']
                    print(f' Received text: {delta}')
                elif event_type == 'response.audio_transcript.done':
                    transcript = message['transcript']
                    print(f' Received text: {transcript}')
                elif event_type == 'conversation.item.input_audio_transcription.delta':
                    delta = message['delta']
                    print(f' Input content: {delta}')
                else:
                    print(f'⚡️ Received WebSocket message: {message}')

            except Exception as e:
                print(f'Error receiving audio data: {e}')
                print(f'Error receiving audio data: {info}')
    except Exception as e:
        print(f'Audio receiving thread exception: {e}')
    finally:
        print('Audio receiving thread exited')


def send_fc_session_update(ws):
    session_config = {
        "type": "session.update",
        "session": {
            "instructions": (
                "You are a friendly AI assistant. "
                "You will provide patient and professional answers to users' questions."
            ),
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.5,
                "prefix_padding_ms": 300,
                "silence_duration_ms": 500
            },
            "voice": "alloy",
            "temperature": 1,
            "max_response_output_tokens": 4096,
            "modalities": ["text", "audio"],
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "input_audio_transcription": {
                "model": "whisper-1"
            }
        }
    }

    try:
        ws.send(json.dumps(session_config))
        print("Session configuration update sent")
    except Exception as e:
        print(f"Failed to send session configuration: {e}")


def create_connection_with_ipv4(*args, **kwargs):
    original_getaddrinfo = socket.getaddrinfo

    def getaddrinfo_ipv4(host, port, family=socket.AF_INET, *args):
        return original_getaddrinfo(host, port, socket.AF_INET, *args)

    socket.getaddrinfo = getaddrinfo_ipv4
    try:
        return websocket.create_connection(*args, **kwargs)
    finally:
        socket.getaddrinfo = original_getaddrinfo


def connect_to_openai():
    ws = None
    try:
        ws = create_connection_with_ipv4(
            WS_URL,
            header=[
                f'Authorization: Bearer {API_KEY}',
                'OpenAI-Beta: realtime=v1'
            ],
            sslopt={"cert_reqs": ssl.CERT_NONE}
        )

        print('Successfully connected to OpenAI WebSocket, Yipee!')

        receive_thread = threading.Thread(target=receive_audio_from_websocket, args=(ws,))
        receive_thread.start()

        mic_thread = threading.Thread(target=send_mic_audio_to_websocket, args=(ws,))
        mic_thread.start()

        while not stop_event.is_set():
            time.sleep(0.1)

        print('Sending WebSocket close frame...')
        ws.send_close()

        receive_thread.join()
        mic_thread.join()

        print('WebSocket connection closed, threads terminated')
    except Exception as e:
        print(f'Failed to connect to OpenAI: {e}')
    finally:
        if ws is not None:
            try:
                ws.close()
                print('WebSocket connection closed')
            except Exception as e:
                print(f'Error closing WebSocket connection: {e}')


def main():
    p = pyaudio.PyAudio()

    mic_stream = p.open(
        format=FORMAT,
        channels=1,
        rate=RATE,
        input=True,
        stream_callback=mic_callback,
        frames_per_buffer=int(CHUNK_SIZE)
    )

    speaker_stream = p.open(
        format=FORMAT,
        channels=1,
        rate=RATE,
        output=True,
        stream_callback=speaker_callback,
        frames_per_buffer=CHUNK_SIZE*4
    )

    try:
        mic_stream.start_stream()
        speaker_stream.start_stream()

        # Start Baymax face animation
        face_thread = threading.Thread(target=baymax_face_loop, args=(stop_event,))
        face_thread.start()

        connect_to_openai()

        while mic_stream.is_active() and speaker_stream.is_active():
            time.sleep(0.1)

    except KeyboardInterrupt:
        print('Gracefully shutting down...')
        stop_event.set()

    finally:
        mic_stream.stop_stream()
        mic_stream.close()
        speaker_stream.stop_stream()
        speaker_stream.close()

        p.terminate()
        stop_event.set()
        print('Audio streams stopped, resources released. Program exiting')


if __name__ == '__main__':
    main()
