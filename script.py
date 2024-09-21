import numpy
import os
import queue
import re
import requests
import sounddevice
import soundfile
import speech_recognition
import threading
import time
from dotenv import load_dotenv
from pynput import keyboard
from selenium import webdriver
from selenium.webdriver.common.by import By

# Load environment variables
load_dotenv()

# Constants
CHROME_DRIVER_PATH = "C:\\Program Files\\chromedriver-win64\\chromedriver.exe"
MICROPHONE_NAME = "Microphone Array"
VIRTUAL_MICROPHONE_NAME = "CABLE Output"
SPEAKER_NAME = "Headset"
VIRTUAL_SPEAKER_NAME = "CABLE Input"
CHUNK_SIZE = 1024
API_KEY = os.getenv("API_KEY")
VOICE_ID = os.getenv("VOICE_ID")


def click_button(xpath):
    try:
        button = chrome_driver.find_element(By.XPATH, xpath)
        button.click()
    except:
        return False
    return True


def set_audio_device(audio_device_name):
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


def get_audio_file_path(text_to_speak):
    file_name = re.sub(r'[?]', '_', text_to_speak)
    file_name = re.sub(r'[<>:"/\\|*]', '', file_name)
    return f".\\audio_cache\\{file_name}.mp3"


def fetch_audio(text_to_speak, output_file_path):
    tts_url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream"
    headers = {
        "Accept": "application/json",
        "xi-api-key": API_KEY
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
        with open(output_file_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                f.write(chunk)
    else:
        print(response.text)


def play_audio(file_path):
    data, samplerate = soundfile.read(file_path)
    sounddevice.play(data, samplerate)
    sounddevice.wait()


def speak(text_to_speak):
    # Switch to virtual cable microphone
    set_audio_device(VIRTUAL_MICROPHONE_NAME)

    # Fetch audio if not already cached
    file_path = get_audio_file_path(text_to_speak)
    if not os.path.isfile(file_path):
        fetch_audio(text_to_speak, file_path)

    # Play audio
    play_audio(file_path)

    # Switch to microphone
    set_audio_device(MICROPHONE_NAME)


def listen():
    def record_audio(audio_queue):
        recognizer = speech_recognition.Recognizer()
        with speech_recognition.Microphone() as source:
            index = 0
            while True:
                message_queue.put(f"== Recording chunk {index}")
                audio = recognizer.record(source, duration=2)
                audio_queue.put({"index": index, "audio": audio})
                index += 1

    def recognize_speech(audio_queue):
        recognizer = speech_recognition.Recognizer()
        buffer = []

        while True:
            if len(buffer) < 2:  # fill the buffer
                data = audio_queue.get()
                if data is None:
                    break
                buffer.append(data)
            else:  # slide the window forward
                buffer.pop(0)
                data = audio_queue.get()
                if data is None:
                    break
                buffer.append(data)

            # Combine the chunks in the buffer into one audio sample
            audio_sample = speech_recognition.AudioData(
                b''.join(chunk['audio'].frame_data for chunk in buffer), data['audio'].sample_rate, data['audio'].sample_width)

            # Print the range of chunks being recognized
            first_chunk_index = buffer[0]['index']
            last_chunk_index = buffer[-1]['index']
            message_prefix = f"Recognize chunks {
                first_chunk_index}-{last_chunk_index}:"

            try:
                recognized_speech = recognizer.recognize_google(audio_sample)
            except speech_recognition.UnknownValueError:
                message_queue.put(f"==== {message_prefix} [not understood]")
                continue
            except speech_recognition.RequestError as e:
                message_queue.put(f"==== {message_prefix} [error]")
                continue

            message_queue.put(f"==== {message_prefix} {recognized_speech}")
            with open("recognized_speech.txt", "a") as file:
                file.write(recognized_speech + "\n")

    def console_writer(message_queue):
        while True:
            message = message_queue.get()
            if message is None:
                break
            print(message)

    # Create a queue to hold audio chunks
    audio_queue = queue.Queue()
    message_queue = queue.Queue()

    # Create and start the recording and console writing threads
    recording_thread = threading.Thread(
        target=record_audio, args=(audio_queue,))
    recording_thread.start()

    console_writer_thread = threading.Thread(
        target=console_writer, args=(message_queue,))
    console_writer_thread.start()

    # Create and start a single recognition thread
    recognition_thread = threading.Thread(
        target=recognize_speech, args=(audio_queue,))
    recognition_thread.start()

    # Wait infinitely
    while True:
        time.sleep(1)


# Connect to browser
chrome_options = webdriver.ChromeOptions()
chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
chrome_driver = webdriver.Chrome(options=chrome_options)

listen()
