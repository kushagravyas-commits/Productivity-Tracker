import os
import sys
import time
import json
import requests
from datetime import datetime

# DaVinci Resolve Python API requires these imports and setup
# The module is usually installed with Resolve or found in specific paths
def get_resolve():
    try:
        import DaVinciResolveScript as bmd
        return bmd.scriptapp("Resolve")
    except ImportError:
        # Check standard installation paths for Windows
        paths = [
            r"C:\Program Files\Blackmagic Design\DaVinci Resolve\Developer\Scripting\Modules",
            r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules"
        ]
        for p in paths:
            if p not in sys.path:
                sys.path.append(p)
        try:
            import DaVinciResolveScript as bmd
            return bmd.scriptapp("Resolve")
        except ImportError:
            return None

def main():
    API_URL = "http://127.0.0.1:8000/api/v1/context/app"
    POLL_INTERVAL = 5 # seconds
    
    print("Starting DaVinci Resolve Productivity Tracker...")
    
    while True:
        try:
            resolve = get_resolve()
            if not resolve:
                # Resolve not running or API not enabled in preferences
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
                    "captured_at": datetime.now().isoformat()
                }
                
                try:
                    res = requests.post(API_URL, json=payload, timeout=5)
                    if res.status_code != 200:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Agent error: {res.status_code}")
                except requests.RequestException:
                    pass # Background agent might be down
                    
            time.sleep(POLL_INTERVAL)
        except Exception as e:
            print(f"Error in DaVinci tracker: {e}")
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
