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
from dotenv import load_dotenv
from openai import OpenAI
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
EL_API_KEY = os.getenv("EL_API_KEY")
VOICE_ID = os.getenv("VOICE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LOGS_PATH = ".\\logs.txt"
LATEST_TRANSCRIPT_PATH = ".\\transcript\\latest_transcript.txt"
HIGH_QUALITY_TRANSCRIPT_PATH = ".\\transcript\\high_quality_transcript.txt"


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


def read_file(file_path):
    with file_lock:
        with open(file_path, "r") as file:
            data = file.read()
    return data


def read_and_clear_file(file_path):
    with file_lock:
        with open(file_path, "r+") as file:
            data = file.read()
            file.seek(0)
            file.truncate()
    return data


def append_to_file(file_path, line):
    with file_lock:
        with open(file_path, "a") as file:
            file.write(line)


def audio_recorder(audio_queue, message_queue):
    recognizer = speech_recognition.Recognizer()
    with speech_recognition.Microphone() as source:
        index = 0
        while True:
            message_queue.put(f"== Recording chunk {index}")
            audio = recognizer.record(source, duration=2)
            audio_queue.put({"index": index, "audio": audio})
            index += 1


def logger(message_queue):
    while True:
        message = message_queue.get()
        if message is None:
            break
        time_now = time.strftime(r"%Y-%m-%d %H:%M:%S", time.localtime())
        with open(LOGS_PATH, "a") as file:
            file.write(f"{time_now}: {message}\n")


def speech_recognizer(audio_queue, message_queue):
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
        message_prefix = f"Recognized chunks {
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
        append_to_file(
            LATEST_TRANSCRIPT_PATH, f"chunk {last_chunk_index}: {recognized_speech}\n")


def transcription_manager(client):
    while True:
        time.sleep(20)

        latest_transcript = read_and_clear_file(LATEST_TRANSCRIPT_PATH)

        if len(latest_transcript) == 0:
            continue

        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "The user will provide you with a transcript made from overlapping chunks of audio. You need to process it into coherent text. Here's an example of what is expected:\n\nBefore we wrap up today's meeting, let's quickly go over the progress we've made on our current sprint and identify any blockers that might delay our delivery timeline.\n\nThis is a coherent sentence extracted from a conversation, and you need to generate similar coherent sentences from the provided transcript."
                },
                {
                    "role": "user",
                    "content": "Please transform this overlapping transcript into coherent text, focusing on content:\n\n" + latest_transcript
                }
            ]
        )
        transformed_dialog = completion.choices[0].message.content

        with open(HIGH_QUALITY_TRANSCRIPT_PATH, "a") as file:
            file.write(f"\n{transformed_dialog}")


def process_command(user_command):
    '''
    Process the user command and generate a LLM generated response.
    '''

    if len(user_command) == 0:
        user_command = "Respond"

    high_quality_transcript = read_file(HIGH_QUALITY_TRANSCRIPT_PATH)
    latest_transcript = read_file(LATEST_TRANSCRIPT_PATH)

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "I'm going to provide you with two transcripts for an ongoing conversation.\n1. The high quality transcript that was spoken earlier.\n2.The latest transcript that was spoken very recently, but has overlapping chunks of dialog and is less coherent."
            },
            {
                "role": "system",
                "content": "High quality transcript:\n\n" + high_quality_transcript
            },
            {
                "role": "system",
                "content": "Latest transcript:\n\n" + latest_transcript
            },
            {
                "role": "system",
                "content": "You must now step into the role of a human that is involved in the conversation. You must must respond as if you were a human in the conversation. You must provide a response that is coherent and relevant to the conversation. The user will secretly provide a command that may or may not help you understand how you should respond. Do not respond to the user as they are only guiding you, respond as if you were participating in the conversation."
            },
            {
                "role": "user",
                "content": user_command
            }
        ]
    )

    print(completion.choices[0].message.content)


# Connect to browser
chrome_options = webdriver.ChromeOptions()
chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
chrome_driver = webdriver.Chrome(options=chrome_options)

# Create a queue to hold audio chunks
audio_queue = queue.Queue()
message_queue = queue.Queue()

# Create a file lock
file_lock = threading.Lock()

# Create empty transcription files
with open(LOGS_PATH, "w") as file:
    pass
with open(LATEST_TRANSCRIPT_PATH, "w") as file:
    pass
with open(HIGH_QUALITY_TRANSCRIPT_PATH, "w") as file:
    pass

# Create OpenAI client
client = OpenAI()
client.api_key = os.getenv("OPENAI_API_KEY")

# Create and start threads for recording, recognition, logging, and transcription processing
audio_recorder_thread = threading.Thread(
    target=audio_recorder, args=(audio_queue, message_queue))
audio_recorder_thread.start()

speech_recognizer_thread = threading.Thread(
    target=speech_recognizer, args=(audio_queue, message_queue))
speech_recognizer_thread.start()

console_writer_thread = threading.Thread(
    target=logger, args=(message_queue,))
console_writer_thread.start()

transcription_manager_thread = threading.Thread(
    target=transcription_manager, args=(client,)
)
transcription_manager_thread.start()

# Wait infinitely
while True:
    user_command = input(">>> ")
    process_command(user_command)
