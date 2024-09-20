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
    def record_audio(q):
        recognizer = speech_recognition.Recognizer()

        with speech_recognition.Microphone() as source:
            while listening:
                print("Recording...")
                # Record in 1-second chunks
                audio = recognizer.record(source, duration=1)
                q.put(audio)

    def recognize_chunk(recognizer, audio):
        try:
            start_time = time.time()
            recognized_speech = recognizer.recognize_google(audio)
            end_time = time.time()
            elapsed_time = round(end_time - start_time)
            duration = round(len(audio.frame_data) / audio.sample_rate)
            print(f"Recognized {duration}s of speech in {elapsed_time}s: {recognized_speech}")
            with open("recognized_speech.txt", "a") as file:
                file.write(recognized_speech + "\n")
        except speech_recognition.UnknownValueError:
            print("Could not understand the audio")
        except speech_recognition.RequestError as e:
            print("Could not request results; {0}".format(e))

    def recognize_speech(q):
        recognizer = speech_recognition.Recognizer()
        audio = None

        while listening:
            chunk = q.get()
            if chunk is None:
                break

            if audio is None:
                audio = chunk
            else:
                audio = speech_recognition.AudioData(
                    audio.frame_data + chunk.frame_data, audio.sample_rate, audio.sample_width)

            if len(audio.frame_data) >= audio.sample_rate * 10:
                recognize_chunk(recognizer, audio)
                audio = None

        if audio is not None:
            recognize_chunk(recognizer, audio)

    # Switch to virtual cable speaker
    set_audio_device(VIRTUAL_SPEAKER_NAME)

    listening = True

    def on_press(key):
        nonlocal listening
        try:
            if key == keyboard.Key.backspace:
                print("Stopping recording...")
                listening = False
        except AttributeError:
            pass

    keyboard_listener = keyboard.Listener(on_press=on_press)
    keyboard_listener.start()

    # Create a queue to hold audio chunks
    q = queue.Queue()

    # Create and start the recording thread
    recording_thread = threading.Thread(target=record_audio, args=(q,))
    recording_thread.start()

    # Create and start the recognition thread
    recognition_thread = threading.Thread(target=recognize_speech, args=(q,))
    recognition_thread.start()

    while listening:
        time.sleep(1)

    # Stop the threads
    q.put(None)
    recording_thread.join()
    recognition_thread.join()

    keyboard_listener.stop()

    # Switch to virtual cable speaker
    set_audio_device(SPEAKER_NAME)


# Connect to browser
chrome_options = webdriver.ChromeOptions()
chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
chrome_driver = webdriver.Chrome(options=chrome_options)

# Main loop
while True:
    input_text = input(">>> ")
    if input_text == r"l":
        listen()
    else:
        speak(input_text)
