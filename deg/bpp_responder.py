import json
import requests

def simulate_bpp_on_search():
    with open("deg/on_search_payload.json") as f:
        payload = json.load(f)

    print("\n📡 Sending /on_search response to DEG Gateway...")
    print("📝 Payload being sent:")
    print(json.dumps(payload, indent=2))
    headers = {
        "Content-Type": "application/json"
    }
    response = requests.post("http://localhost:4030/on_search", json=payload, headers=headers)

    # response = requests.post("http://localhost:4030/on_search", json=payload)

    try:
        response_data = response.json()
        print("✅ Gateway ACK:", json.dumps(response_data, indent=2))
    except requests.exceptions.JSONDecodeError:
        print("⚠️ Non-JSON response:", response.status_code)
        print(response.text)

if __name__ == "__main__":
    simulate_bpp_on_search()
