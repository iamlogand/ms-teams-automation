# MS Teams Automation

A Python script for Windows that can play sounds in MS Teams through a virtual audio cable.

Required software:
- Python
- Chrome
- Chrome Driver
- VLC Media Player
- VB-Cable

Setup:
1. Create a Python virtual environment and install packages from requirements.txt
1. Customize constants, if needed, in script.py
1. Create a .env file and add the following environment variables:
   - VOICE_ID (your ElevenLabs voice ID)
   - EL_API_KEY (your ElevenLabs API key)
   - OPENAI_API_KEY (your OpenAI API key)
1. Start Chrome with a custom debugging port using a command like this:
   ```
   "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
   ```
1. In that Chrome tab, go to https://teams.microsoft.com/v2/ and join a call
1. Ensure that live captions are on
1. Start the python script

Usage:
1. Once you see ">>>", press enter to make the script respond to the conversation.
1. Optionally, before pressing enter, type some text to give the script an indication of what to say.
