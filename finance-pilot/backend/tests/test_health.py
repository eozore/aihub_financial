import requests

url = "https://finance-backend-930725375338.us-central1.run.app"

try:
    print(f"Checking {url}...")
    response = requests.get(url)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")
    
    if response.status_code == 200:
        print("SUCCESS: Service is reachable!")
    else:
        print("FAILURE: Service returned non-200 code.")
except Exception as e:
    print(f"ERROR: {e}")
