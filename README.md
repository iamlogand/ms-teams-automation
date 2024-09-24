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
1. Customize constants if needed in script.py
1. Start Chrome with a custom debugging port using a command like this:
   ```
   "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
   ```
1. In that Chrome tab, go to https://teams.microsoft.com/v2/ and join a call
1. Start the python script
