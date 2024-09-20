import os
import re
import requests
import sounddevice
import soundfile
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By

# Load environment variables
load_dotenv()

# constants
CHROME_DRIVER_PATH = "C:\\Program Files\\chromedriver-win64\\chromedriver.exe"
VIRTUAL_CABLE_NAME = "CABLE Output"
MICROPHONE_NAME = "Microphone Array"
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


def set_audio_input_device(audio_device_name):
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
    # Switch to virtual cable output as input
    set_audio_input_device(VIRTUAL_CABLE_NAME)

    # Fetch audio if not already cached
    file_path = get_audio_file_path(text_to_speak)
    if not os.path.isfile(file_path):
        fetch_audio(text_to_speak, file_path)

    # Play audio
    play_audio(file_path)

    # Switch to microphone input
    set_audio_input_device(MICROPHONE_NAME)


# Connect to browser
chrome_options = webdriver.ChromeOptions()
chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
chrome_driver = webdriver.Chrome(options=chrome_options)

# Main loop
while True:
    input_text = input(">>> ")
    speak(input_text)
