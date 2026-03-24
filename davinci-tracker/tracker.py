import os
import sys
import time
import json
import requests
from datetime import datetime, timezone

# DaVinci Resolve Python API requires these imports and setup
# The module is usually installed with Resolve or found in specific paths
def get_resolve():
    try:
        import DaVinciResolveScript as bmd
        return bmd.scriptapp("Resolve")
    except ImportError:
        # Check standard installation paths for Windows and macOS
        paths = [
            r"C:\Program Files\Blackmagic Design\DaVinci Resolve\Developer\Scripting\Modules",
            r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules",
            "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules",
            "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/Modules",
        ]
        for p in paths:
            if p not in sys.path:
                sys.path.append(p)
        try:
            import DaVinciResolveScript as bmd
            return bmd.scriptapp("Resolve")
        except ImportError:
            return None

def get_machine_guid() -> str:
    """Get stable machine GUID across platforms."""
    if sys.platform == "darwin":
        try:
            cmd = "ioreg -rd1 -c IOPlatformExpertDevice | awk '/IOPlatformUUID/ { split($0, line, \"\\\"\"); printf(\"%s\", line[4]); }'"
            out = os.popen(cmd).read().strip()
            if out:
                return out
        except:
            pass
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
        guid, _ = winreg.QueryValueEx(key, "MachineGuid")
        winreg.CloseKey(key)
        return str(guid)
    except:
        import uuid
        return str(uuid.getnode())

def main():
    API_URL = "http://127.0.0.1:8080/api/v1/context/app"
    POLL_INTERVAL = 5 # seconds
    
    print("Starting DaVinci Resolve Productivity Tracker...")
    machine_guid = get_machine_guid()
    print(f"Tracker machine GUID: {machine_guid}")
    print(f"Posting app context to: {API_URL}")
    headers = {
        "X-Machine-GUID": machine_guid,
        "Content-Type": "application/json"
    }
    
    while True:
        try:
            resolve = get_resolve()
            if not resolve:
                # Resolve not running or API not enabled in preferences
                print("Resolve API unavailable (check DaVinci scripting preference + installation paths)")
                time.sleep(POLL_INTERVAL * 2)
                continue
                
            project_manager = resolve.GetProjectManager()
            project = project_manager.GetCurrentProject()
            
            if project:
                project_name = project.GetName()
                timeline = project.GetCurrentTimeline()
                timeline_name = timeline.GetName() if timeline else "None"
                
                payload = {
                    "app_name": "DaVinci Resolve",
                    "active_file_name": project_name,
                    "active_file_path": f"Project: {project_name}", # Resolve projects are database entities
                    "active_sequence": timeline_name,
                    "captured_at": datetime.now(timezone.utc).isoformat()
                }
                
                try:
                    res = requests.post(API_URL, json=payload, headers=headers, timeout=5)
                    if res.status_code == 200:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] App context sent: project={project_name} timeline={timeline_name}")
                    else:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Agent error: {res.status_code} body={res.text[:200]}")
                except requests.RequestException as e:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Post failed: {e}")
                    
            time.sleep(POLL_INTERVAL)
        except Exception as e:
            print(f"Error in DaVinci tracker: {e}")
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
