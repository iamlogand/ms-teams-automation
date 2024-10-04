import asyncio
import base64
import json
import os
import queue
import subprocess
import threading
import time
import websockets
from datetime import datetime
from dotenv import load_dotenv
from openai import AsyncOpenAI
from selenium import webdriver
from selenium.webdriver.common.by import By

# Load environment variables
load_dotenv()

# Constants
CHROME_DRIVER_PATH = "C:\\Program Files\\chromedriver-win64\\chromedriver.exe"
MICROPHONE_NAME = "Microphone Array"
VIRTUAL_MICROPHONE_NAME = "CABLE Output"
VIRTUAL_SPEAKER_NAME = "{afeab4bf-ab5d-4d43-bd5c-a81b237a6670}"
AUDIO_CHUNK_SIZE = 1024
EL_MAX_CONCURRENT_REQUESTS = 5
EL_API_KEY = os.getenv("EL_API_KEY")
VOICE_ID = os.getenv("VOICE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LOGS_PATH = ".\\logs.txt"
USERNAME = "Logan Davidson"
CONTEXT = """Logan is a software engineer that works at a company called AutoRek.
Logan is British and in his 20s, like most people in the team.
At AutoRek, things are usually informal, with none of the standard business talk.
Logan sometimes uses filler words, especially between sentences when thinking about what to say.
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
        Return a list of all transcript items ordered from oldest to newest.
        """
        with self.lock:
            items = list(self.transcript.values())
            items.sort(key=lambda x: x.timestamp)
            return items


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
                By.XPATH, captions_wrapper_locator).find_elements(By.XPATH, caption_locator)[-100:]
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
                    message_queue.put(
                        f"{result} transcript item: {caption_header}: {caption_content}")
        except:
            time.sleep(1)


async def text_chunker(chunks):
    """
    Split text into chunks, ensuring to not break sentences.
    """
    splitters = (
        ".", ",", "?", "!", ";", ":", "—", "-", "(", ")", "[", "]", "}", " ")
    buffer = ""

    async for text in chunks:
        if text is None or text == "":
            continue  # Skip None or empty values

        if buffer.endswith(splitters):
            yield buffer + " "
            buffer = text
        elif text.startswith(splitters):
            yield buffer + text[0] + " "
            buffer = text[1:]
        else:
            buffer += text

    if buffer:
        yield buffer + " "


async def stream(audio_stream):
    """
    Stream audio data using mpv player.
    """
    mpv_process = subprocess.Popen(
        [
            "C:\\Program Files (x86)\\mpv\\mpv.exe",
            "--no-cache",
            "--no-terminal",
            f"--audio-device=wasapi/{VIRTUAL_SPEAKER_NAME}", # when i add this line, it doesn't work
            "--",
            "fd://0"
        ],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    async for chunk in audio_stream:
        if chunk:
            mpv_process.stdin.write(chunk)
            mpv_process.stdin.flush()

    if mpv_process.stdin:
        mpv_process.stdin.close()
    mpv_process.wait()


async def text_to_speech_input_streaming(text_iterator):
    """
    Send text to ElevenLabs API and stream the returned audio.
    """
    uri = f"wss://api.elevenlabs.io/v1/text-to-speech/{
        VOICE_ID}/stream-input?model_id=eleven_turbo_v2_5"

    async with websockets.connect(uri) as websocket:
        await websocket.send(json.dumps({
            "text": " ",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
            "xi_api_key": EL_API_KEY,
        }))

        async def listen():
            """Listen to the websocket for audio data and stream it."""
            while True:
                try:
                    message = await websocket.recv()
                    data = json.loads(message)
                    if data.get("audio"):
                        yield base64.b64decode(data["audio"])
                    elif data.get('isFinal'):
                        break
                except websockets.exceptions.ConnectionClosed:
                    print("Connection closed")
                    break

        listen_task = asyncio.create_task(stream(listen()))

        async for text in text_chunker(text_iterator):
            await websocket.send(json.dumps({"text": text}))

        await websocket.send(json.dumps({"text": ""}))

        await listen_task


async def speak(openai_client, chrome_driver, transcript_manager, user_command):
    """Retrieve text from OpenAI and pass it to the text-to-speech function."""

    # Get transcript
    annotated_transcript = transcript_manager.read_items()[-10:]

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
    user_command = user_command.strip()
    hint = f" (hint: {user_command})" if user_command else ""
    messages.append({
        "role": "user",
        "content": f"What does {USERNAME} say next? {hint}"
    })

    # Generate completion
    response = await openai_client.chat.completions.create(model='gpt-4o-mini', messages=messages, stream=True)

    async def text_iterator():
        async for chunk in response:
            delta = chunk.choices[0].delta
            token = delta.content
            if token:
                print(token, end='', flush=True)
            yield token

    set_audio_device(chrome_driver, VIRTUAL_MICROPHONE_NAME)
    await text_to_speech_input_streaming(text_iterator())
    print()
    set_audio_device(chrome_driver, MICROPHONE_NAME)


async def process_command(openai_client, chrome_driver, transcript_manager):
    while True:
        user_command = input(">>> ")
        await speak(openai_client, chrome_driver, transcript_manager, user_command)


async def main(openai_client, chrome_driver, transcript_manager):
    # Start the command processing loop
    await process_command(openai_client, chrome_driver, transcript_manager)

if __name__ == "__main__":
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
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

    # Create and start threads for recording, recognition, logging, and transcription processing
    logger_thread = threading.Thread(target=logger, args=(message_queue,))
    logger_thread.start()

    transcriber_thread = threading.Thread(target=transcriber, args=(
        chrome_driver, transcript_manager, message_queue))
    transcriber_thread.start()

    # Create semaphore for limiting concurrent requests
    semaphore = threading.Semaphore(EL_MAX_CONCURRENT_REQUESTS)

    # Start the main asyncio loop
    asyncio.run(main(openai_client, chrome_driver, transcript_manager))
