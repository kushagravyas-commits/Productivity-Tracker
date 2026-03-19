import requests

url = "http://localhost:8080/api/v1/context/browser/2026-03-19?device_id=df64f36f-46a1-40b5-a3b4-294b8bf3988b"
try:
    response = requests.get(url, timeout=40)
    print(f"Status Code: {response.status_code}")
    print(f"Response Body: {response.text}")
except Exception as e:
    print(f"Error: {e}")
