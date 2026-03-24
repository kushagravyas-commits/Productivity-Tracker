import os
import json
import sys
import time
import subprocess
import uuid
import requests
import psutil
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Production paths: Store in ~/Library/Application Support/TrackFlow
HOME = Path.home()
APPDATA_PATH = HOME / "Library" / "Application Support" / "TrackFlow"
APPDATA_PATH.mkdir(parents=True, exist_ok=True)

# Fix stdout/stderr for PyInstaller --noconsole mode
if getattr(sys, "frozen", False):
    _log_path = APPDATA_PATH / "agent.log"
    _log_file = open(_log_path, "a", encoding="utf-8", buffering=1)
    sys.stdout = _log_file
    sys.stderr = _log_file

# Load configuration
_env_candidates = [Path(".env"), Path("../.env"), Path("../backend/.env")]
if getattr(sys, "frozen", False):
    _env_candidates.insert(0, Path(sys._MEIPASS) / ".env")
for path in _env_candidates:
    if path.exists():
        load_dotenv(path)
        break

API_BASE_URL = os.getenv("TRACKER_API_BASE_URL", "http://127.0.0.1:8080")
CONFIG_PATH = APPDATA_PATH / "agent_config.json"
REGISTRATION_TOKEN = os.getenv("TRACKER_REGISTRATION_TOKEN")

def get_mac_uuid():
    """Get unique hardware UUID for macOS."""
    try:
        cmd = "ioreg -rd1 -c IOPlatformExpertDevice | awk '/IOPlatformUUID/ { split($0, line, \"\\\"\"); printf(\"%s\", line[4]); }'"
        uuid_str = subprocess.check_output(cmd, shell=True).decode().strip()
        if uuid_str: return uuid_str
    except:
        pass
    return str(uuid.getnode())

def get_active_window_info():
    """Use AppleScript to get the frontmost application and its window title."""
    script = '''
    global frontApp, frontAppName, windowTitle
    set windowTitle to ""
    tell application "System Events"
        set frontApp to first application process whose frontmost is true
        set frontAppName to name of frontApp
        tell frontApp
            if exists (window 1) then
                set windowTitle to name of window 1
            end if
        end tell
    end tell
    return frontAppName & "|||" & windowTitle
    '''
    try:
        out = subprocess.check_output(['osascript', '-e', script], stderr=subprocess.STDOUT).decode('utf-8').strip()
        if "|||" in out:
            app_name, window_title = out.split("|||", 1)
            return app_name, window_title
    except subprocess.CalledProcessError as e:
        if "not allowed assistive access" in str(e.output):
            return "Accessibility-Restricted", "Please grant permissions"
        return "Unknown", ""
    except:
        return "Unknown", ""

def _osascript(prompt: str) -> str:
    try:
        return subprocess.check_output(["osascript", "-e", prompt], stderr=subprocess.DEVNULL).decode("utf-8").strip()
    except Exception:
        return ""


def mac_choice_dialog() -> str:
    script = '''
    set userChoice to button returned of (display dialog "How would you like to register this device?" buttons {"Register Without Token", "I Have a Token"} default button "Register Without Token" with title "TrackFlow Agent Setup")
    return userChoice
    '''
    return _osascript(script)


def mac_text_input(title: str, prompt: str, default: str = "") -> str | None:
    default_escaped = default.replace('"', '\\"')
    prompt_escaped = prompt.replace('"', '\\"')
    title_escaped = title.replace('"', '\\"')
    script = f'''
    try
        set userInput to text returned of (display dialog "{prompt_escaped}" default answer "{default_escaped}" with title "{title_escaped}")
        return userInput
    on error number -128
        return "__CANCELLED__"
    end try
    '''
    value = _osascript(script)
    if value == "__CANCELLED__":
        return None
    return value


def show_mac_registration_dialog(machine_guid: str) -> None:
    choice = mac_choice_dialog()
    if choice == "I Have a Token":
        token = mac_text_input("TrackFlow Setup", "Paste your registration token:")
        if token and token.strip():
            ok = perform_registration(machine_guid, token=token.strip())
            if ok:
                return
    # Fallback or explicit tokenless flow
    name = mac_text_input("TrackFlow Setup", "Enter your full name:")
    email = mac_text_input("TrackFlow Setup", "Enter your email address:")
    perform_registration(machine_guid, full_name=(name or None), email=(email or None))


def perform_registration(machine_guid: str, token: str | None = None, full_name: str | None = None, email: str | None = None) -> bool:
    """Register or re-register this Mac with backend and persist local config."""
    url = f"{API_BASE_URL.rstrip('/')}/api/v1/register"
    payload = {
        "machine_guid": machine_guid,
        "os_type": "macos",
        "registration_token": token or REGISTRATION_TOKEN,
    }
    if full_name:
        payload["full_name"] = full_name
    if email:
        payload["email"] = email

    # Retry 5 times since the server might still be booting up
    for attempt in range(5):
        try:
            print(f"Registering device (Attempt {attempt+1}/5): {machine_guid}")
            resp = requests.post(url, json=payload, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                # Cache config
                CONFIG_PATH.write_text(json.dumps({
                    "machine_guid": machine_guid,
                    "api_base_url": API_BASE_URL,
                    "role": data.get("role", "employee"),
                }))
                if data.get("assigned_user"):
                    print(f"Registration successful. Assigned to {data['assigned_user']}")
                    return True
                print("Registration successful. Waiting for admin assignment.")
                return False
        except Exception as e:
            print(f"Registration attempt {attempt+1} failed: {e}")
            time.sleep(3)
    return False

def main():
    machine_guid = get_mac_uuid()

    # Match Windows behavior: always re-register on startup.
    # If still unassigned, prompt user for token/tokenless registration.
    is_assigned = perform_registration(machine_guid)
    if not is_assigned:
        show_mac_registration_dialog(machine_guid)
    
    print("Starting activity tracking...")
    last_app, last_title = get_active_window_info()
    start_time = datetime.utcnow()
    
    headers = {"X-Machine-GUID": machine_guid}
    
    while True:
        try:
            time.sleep(5) # Poll every 5 seconds
            current_app, current_title = get_active_window_info()
            
            # If app or title changed, or 60 seconds passed, finish this segment
            now = datetime.utcnow()
            duration = (now - start_time).total_seconds()
            
            if (current_app != last_app or current_title != last_title or duration > 60) and duration > 1:
                # Send the completed segment to events
                payload = {
                    "started_at": start_time.isoformat() + "Z",
                    "ended_at": now.isoformat() + "Z",
                    "app_name": last_app,
                    "window_title": last_title,
                    "source": "macos_agent"
                }
                try:
                    requests.post(f"{API_BASE_URL}/api/v1/events", json=payload, headers=headers, timeout=5)
                    print(f"Logged segment: {last_app} ({int(duration)}s)")
                except Exception as e:
                    print(f"Failed to log segment: {e}")
                
                # Reset for new segment
                last_app, last_title = current_app, current_title
                start_time = now
            
        except Exception as e:
            print(f"Tracking error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
