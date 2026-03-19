import requests
from datetime import datetime

url = "http://localhost:8080/api/v1/context/editor"
payload = {
    "captured_at": datetime.now().isoformat(),
    "editor_app": "VS Code",
    "workspace": "Productivity-Tracker",
    "active_file": "main.py",
    "active_file_path": "/path/to/main.py",
    "language": "python",
    "open_files": ["main.py", "db.py"],
    "terminal_count": 1,
    "git_branch": "main",
    "debugger_active": False
}

try:
    response = requests.post(url, json=payload, timeout=20)
    print(f"POST Status: {response.status_code}")
    print(f"POST Response: {response.text}")
    
    # Now verify it exists
    day = datetime.now().strftime("%Y-%m-%d")
    get_url = f"http://localhost:8080/api/v1/context/editor/{day}"
    response_get = requests.get(get_url, timeout=20)
    print(f"GET Status: {response_get.status_code}")
    data = response_get.json()
    found = any(item["workspace"] == "Productivity-Tracker" for item in data)
    print(f"New Editor data found in GET: {found}")
except Exception as e:
    print(f"Error: {e}")
