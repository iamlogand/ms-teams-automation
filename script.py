import collections
import io
import msvcrt
import os
import queue
import re
import requests
import sounddevice
import soundfile
import speech_recognition
import threading
import time
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
from selenium import webdriver
from selenium.webdriver.common.by import By
from typing import List

# Load environment variables
load_dotenv()

# Constants
CHROME_DRIVER_PATH = "C:\\Program Files\\chromedriver-win64\\chromedriver.exe"
MICROPHONE_NAME = "Microphone Array"
VIRTUAL_MICROPHONE_NAME = "CABLE Output"
VIRTUAL_SPEAKER_NAME = "CABLE Input"
VIRTUAL_SPEAKER_INDEX = 12  # Find via `print(sounddevice.query_devices())`
CHUNK_SIZE = 1024
EL_API_KEY = os.getenv("EL_API_KEY")
VOICE_ID = os.getenv("VOICE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LOGS_PATH = ".\\logs.txt"
USERNAME = "Logan"
CONTEXT = """Logan is a software engineer that works at a company called AutoRek.
This conversation is an ongoing Microsoft Teams work call."""


class AudioChunk:
    def __init__(self, id, audio, timestamp):
        self.id = id
        self.audio = audio
        self.timestamp = timestamp


class TranscriptionChunk:
    def __init__(self, text, timestamp, type):
        self.text = text
        self.timestamp = timestamp
        self.type = type


def click_button(xpath):
    try:
        button = chrome_driver.find_element(By.XPATH, xpath)
        button.click()
    except:
        return False
    return True


def set_audio_device(chrome_driver, audio_device_name):
    if chrome_driver is None:
        return

    device_locator = f"//*[contains(text(), '{audio_device_name}')]"
    setting_locator = f"//*[contains(text(), 'Audio settings')]"
    more_locator = "//button[@id='callingButtons-showMoreBtn']"

    device_clicked = False
    while not device_clicked:
        device_clicked = click_button(device_locator)
        if not device_clicked:
            settings_clicked = click_button(setting_locator)
            if not settings_clicked:
                click_button(more_locator)

    button = chrome_driver.find_element(
        By.XPATH, f"//*[contains(text(), '{audio_device_name}')]")
    button.click()


def fetch_audio(text_to_speak):
    tts_url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream"
    headers = {
        "Accept": "application/json",
        "xi-api-key": EL_API_KEY
    }
    data = {
        "text": text_to_speak,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.8,
            "style": 0.0,
            "use_speaker_boost": True
        }
    }
    response = requests.post(tts_url, headers=headers, json=data, stream=True)
    if response.ok:
        audio_data = bytearray()
        for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
            audio_data.extend(chunk)
        return audio_data
    else:
        print(response.text)
        return None


def play_audio(audio_data):
    # Find output device
    devices = sounddevice.query_devices()
    for index, device in enumerate(devices):
        if device['name'] == VIRTUAL_SPEAKER_NAME:
            virtual_speaker_index = index
            break

    # Play audio
    with io.BytesIO(audio_data) as audio_stream:
        data, samplerate = soundfile.read(audio_stream)
        sounddevice.play(data, samplerate, device=virtual_speaker_index)
        sounddevice.wait()


def speak(text_to_speak, chrome_driver):
    # Switch to virtual microphone
    set_audio_device(chrome_driver, VIRTUAL_MICROPHONE_NAME)

    # Fetch audio
    print("Speaking:", text_to_speak)
    audio_data = fetch_audio(text_to_speak)

    if audio_data is not None:
        play_audio(audio_data)
        print("Done speaking")
    else:
        print("Failed to fetch audio.")

    # Switch to microphone
    set_audio_device(chrome_driver, MICROPHONE_NAME)


def recorder(audio_queue, message_queue):
    with speech_recognition.Microphone() as source:
        recognizer = speech_recognition.Recognizer()
        recognizer.pause_threshold = 0.5

        id = 0
        while True:
            try:
                message_queue.put(f".. Started recording chunk {id}")
                audio = recognizer.listen(
                    source, timeout=5, phrase_time_limit=30)
                message_queue.put(
                    f".. Finished recording chunk {id}: success")
                audio_chunk = AudioChunk(id, audio, datetime.now())
                audio_queue.put(audio_chunk)
            except speech_recognition.WaitTimeoutError:
                message_queue.put(
                    f".. Finished recording chunk {id}: error")

            id += 1


def logger(message_queue):
    while True:
        message = message_queue.get()
        if message is None:
            break
        time_now = time.strftime(r"%Y-%m-%d %H:%M:%S", time.localtime())
        with open(LOGS_PATH, "a") as file:
            file.write(f"{time_now} {message}\n")


def transcriber(audio_queue, transcription_queue, message_queue):
    recognizer = speech_recognition.Recognizer()

    while True:
        audio_chunk: AudioChunk = audio_queue.get()
        if audio_chunk is None:
            time.sleep(0.1)
            continue

        message_queue.put(f".... Started transcribing chunk {audio_chunk.id}")

        message_prefix = f"Finished transcribing chunk {audio_chunk.id}:"
        recognized_speech = ""
        try:
            recognized_speech = recognizer.recognize_google(audio_chunk.audio)
            transcription_chunk = TranscriptionChunk(
                recognized_speech, audio_chunk.timestamp, "others")
            transcription_queue.put(transcription_chunk)
            message_queue.put(f'.... {message_prefix} "{recognized_speech}"')
        except speech_recognition.UnknownValueError:
            message_queue.put(f".... {message_prefix} not understood")
        except speech_recognition.RequestError as e:
            message_queue.put(f".... {message_prefix} error")


def generate_speech(openai_client, annotated_transcript, user_command_text):

    # Build messages
    messages = []
    if annotated_transcript:
        formatted_transcript = "\n".join(
            [f"{chunk.timestamp} {chunk.type}: {chunk.text}" for chunk in annotated_transcript])
        messages.append({
            "role": "user",
            "content": f"""Here's a transcript of the conversation up until:\n{formatted_transcript}"""
        })
    messages.append({"role": "user", "content": CONTEXT})
    messages.append({
        "role": "user",
        "content": f"""You must take the role of {USERNAME}, a participant in the conversation.
Respond with only the words {USERNAME} would say, no more.
Your response must not include any additional information like timestamps or usernames."""
    })
    user_command_text = user_command_text.strip()
    hint = f" (hint: {user_command_text})" if user_command_text else ""
    messages.append({
        "role": "user",
        "content": f"What does {USERNAME} say next? {hint}"
    })

    # Generate completion
    completion = openai_client.chat.completions.create(
        model="gpt-4o-mini", messages=messages
    )
    return completion.choices[0].message.content


def process_command(
    openai_client,
    chrome_driver,
    transcription_queue,
    annotated_transcript: List[TranscriptionChunk]
):
    user_command = input(">>> ")

    # Move items from transcription queue to main queue
    while not transcription_queue.empty():
        annotated_transcript.append(transcription_queue.get())

    # If command starts with "s/", speak the rest of the command
    if user_command.startswith("s/"):
        text_to_speak = user_command[2:]
        transcription_chunk = TranscriptionChunk(
            text_to_speak, datetime.now(), "Logan")
        annotated_transcript.append(transcription_chunk)
        speak(text_to_speak, chrome_driver)
        return

    # If command starts with "g/", generate some text based on the command and speak it
    if user_command.startswith("g/"):
        user_command_text = user_command[2:]
        text_to_speak = generate_speech(
            openai_client, annotated_transcript, user_command_text)
        transcription_chunk = TranscriptionChunk(
            text_to_speak, datetime.now(), "Logan")
        annotated_transcript.append(transcription_chunk)
        speak(text_to_speak, chrome_driver)
        return


# Connect to browser
chrome_options = webdriver.ChromeOptions()
chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
chrome_driver = webdriver.Chrome(options=chrome_options)

# Create queues
audio_queue = queue.Queue()
message_queue = queue.Queue()
transcription_queue = queue.Queue()

# Create annotated transcript
annotated_transcript = []

# Create a file lock
file_lock = threading.Lock()

# Create empty logs file
with open(LOGS_PATH, "w") as file:
    pass

# Create OpenAI client
openai_client = OpenAI()
openai_client.api_key = os.getenv("OPENAI_API_KEY")

# Create and start threads for recording, recognition, logging, and transcription processing
logger_thread = threading.Thread(
    target=logger, args=(message_queue,))
logger_thread.start()

recorder_thread = threading.Thread(
    target=recorder, args=(audio_queue, message_queue))
recorder_thread.start()

transcriber_thread = threading.Thread(
    target=transcriber, args=(audio_queue, transcription_queue, message_queue))
transcriber_thread.start()

# Main loop
while True:
    process_command(
        openai_client, chrome_driver, transcription_queue, annotated_transcript)
