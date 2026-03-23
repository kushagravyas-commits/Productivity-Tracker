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

def register_device(machine_guid):
    """Register this Mac with the backend as an unassigned device."""
    url = f"{API_BASE_URL.rstrip('/')}/api/v1/register"
    payload = {
        "machine_guid": machine_guid,
        "os_type": "macos"
    }
    
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
                    "role": data.get("role", "employee")
                }))
                print("Registration successful!")
                return True
        except Exception as e:
            print(f"Registration attempt {attempt+1} failed: {e}")
            time.sleep(3)
    return False

def main():
    machine_guid = get_mac_uuid()
    
    # Try to register if not already registered
    if not CONFIG_PATH.exists():
        register_device(machine_guid)
    
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
