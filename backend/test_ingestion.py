import requests
from datetime import datetime

url = "http://localhost:8081/api/v1/context/browser"
payload = {
    "captured_at": datetime.now().isoformat(),
    "browser_app": "TestAgent",
    "active_tab_url": "https://google.com",
    "active_tab_title": "Google Search",
    "active_tab_domain": "google.com",
    "tab_count": 1,
    "open_domains": ["google.com"]
}

try:
    response = requests.post(url, json=payload, timeout=10)
    print(f"POST Status: {response.status_code}")
    print(f"POST Response: {response.text}")
    
    # Now verify it exists
    day = datetime.now().strftime("%Y-%m-%d")
    get_url = f"http://localhost:8081/api/v1/context/browser/{day}"
    response_get = requests.get(get_url, timeout=10)
    print(f"GET Status: {response_get.status_code}")
    data = response_get.json()
    found = any(item["browser_app"] == "TestAgent" for item in data)
    print(f"New data found in GET: {found}")
except Exception as e:
    print(f"Error: {e}")
