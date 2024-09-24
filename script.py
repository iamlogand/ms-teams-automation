import io
import os
import queue
import requests
import sounddevice
import soundfile
import threading
import time
from datetime import datetime
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
VIRTUAL_SPEAKER_NAME = "CABLE Input (VB-Audio Virtual Cable)"
VIRTUAL_SPEAKER_INDEX = 12  # Find via `print(sounddevice.query_devices())`
CHUNK_SIZE = 1024
EL_API_KEY = os.getenv("EL_API_KEY")
VOICE_ID = os.getenv("VOICE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LOGS_PATH = ".\\logs.txt"
USERNAME = "Logan Davidson"
CONTEXT = """Logan is a software engineer that works at a company called AutoRek.
This conversation is an ongoing Microsoft Teams work call."""


class TranscriptItem:
    def __init__(self, timestamp, speaker, content):
        self.timestamp = timestamp
        self.speaker = speaker
        self.content = content


class TranscriptManager:
    def __init__(self):
        self.transcript = {}
        self.lock = threading.Lock()

    def write_item(self, id, timestamp, speaker, content):
        """
        Create a new transcript item or update content of an existing one.
        """
        with self.lock:
            if id not in self.transcript.keys():
                new_item = TranscriptItem(timestamp, speaker, content)
                self.transcript[id] = new_item
                return "Created"
            elif self.transcript[id].content != content:
                existing_item = self.transcript[id]
                existing_item.content = content
                return "Updated"

    def read_items(self):
        """
        Return a list of all transcript items.
        """
        with self.lock:
            return list(self.transcript.values())


def click_button(xpath):
    try:
        button = chrome_driver.find_element(By.XPATH, xpath)
        button.click()
    except:
        return False
    return True


def set_audio_device(chrome_driver, audio_device_name):
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


def logger(message_queue):
    while True:
        message = message_queue.get()
        if message is None:
            break
        time_now = time.strftime(r"%Y-%m-%d %H:%M:%S:", time.localtime())
        with open(LOGS_PATH, "a") as file:
            file.write(f"{time_now} {message}\n")


def transcriber(chrome_driver, transcript_manager, message_queue):
    captions_wrapper_locator = f"//div[@data-tid='closed-caption-v2-wrapper']"
    caption_locator = f"//div[@data-tid='closed-caption-message-content']"
    caption_header_locator = f".//div[contains(@class, 'ui-chat__messageheader')]"
    caption_content_locator = f".//div[contains(@class, 'ui-chat__messagecontent')]"

    while True:
        try:
            captions = chrome_driver.find_element(
                By.XPATH, captions_wrapper_locator).find_elements(By.XPATH, caption_locator)[-10:]
            for caption in captions:
                caption_id = caption.find_element(
                    By.XPATH, "./div[1]").get_attribute("id")
                caption_header = caption.find_element(
                    By.XPATH, caption_header_locator).text
                caption_content = caption.find_element(
                    By.XPATH, caption_content_locator).text
                timestamp = datetime.now()
                result = transcript_manager.write_item(
                    caption_id, timestamp, caption_header, caption_content)
                if result:
                    message_queue.put(f"{result} transcript item: {
                                      caption_header}: {caption_content}")
        except:
            time.sleep(1)


def generate_speech(
    openai_client,
    transcript_manager: TranscriptManager,
    user_command_text
):
    # Get transcript
    annotated_transcript = transcript_manager.read_items()

    # Build messages
    messages = []
    if len(annotated_transcript) > 0:
        formatted_transcript = "\n".join(
            [f"{item.timestamp} {item.speaker}: {item.content}" for item in annotated_transcript])
        messages.append({
            "role": "user",
            "content": f"""Here's a live transcript of the conversation up until now:\n{formatted_transcript}"""
        })
    messages.append({"role": "user", "content": CONTEXT})
    messages.append({
        "role": "user",
        "content": f"""You must take on the role of {USERNAME}, a participant in the conversation.
Respond with only the words {USERNAME} would say, no more.
Your response must not be prefixed with any additional information like timestamps or your name."""
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
    transcript_manager: TranscriptManager
):
    user_command = input(">>> ")

    # If command starts with "s/", speak the rest of the command
    if user_command.startswith("s/"):
        text_to_speak = user_command[2:]
        speak(text_to_speak, chrome_driver)
        return

    # Otherwise", generate some text based on the command and speak it

    user_command_text = user_command[2:]
    text_to_speak = generate_speech(
        openai_client, transcript_manager, user_command_text)
    speak(text_to_speak, chrome_driver)
    return


# Connect to browser
chrome_options = webdriver.ChromeOptions()
chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
chrome_driver = webdriver.Chrome(options=chrome_options)

# Create message queue and transcript manager
message_queue = queue.Queue()
transcript_manager = TranscriptManager()

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

transcriber_thread = threading.Thread(
    target=transcriber, args=(chrome_driver, transcript_manager, message_queue))
transcriber_thread.start()

# Main loop
while True:
    process_command(
        openai_client, chrome_driver, transcript_manager)
