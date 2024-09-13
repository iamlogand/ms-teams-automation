from selenium import webdriver
from selenium.webdriver.common.by import By
import subprocess

CHROME_DRIVER_PATH = "C:\\Program Files\\chromedriver-win64\\chromedriver.exe"
VLC_PATH = "C:\\Program Files\\VideoLAN\\VLC\\vlc.exe"
MICROPHONE_NAME = "Microphone Array"

chrome_options = webdriver.ChromeOptions()
chrome_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=chrome_options)

while True:
    print()
    command_text = input("Command: ")
    if command_text == "play":
        # Switch to virtual cable output
        button = driver.find_element(By.XPATH, "//*[contains(text(), 'CABLE Output')]")
        button.click()

        # Play audio
        subprocess.run([VLC_PATH, ".\\recording.m4a", "vlc://quit"])
        
        # Switch to microphone input
        button = driver.find_element(By.XPATH, f"//*[contains(text(), '{MICROPHONE_NAME}')]")
        button.click()

    if command_text == "exit":
        break
