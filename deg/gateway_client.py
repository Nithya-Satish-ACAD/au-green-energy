# deg/gateway_client.py
import requests
import uuid
from datetime import datetime
import json

def build_search_payload(time_window: str, quantity_kwh: float = 10.0) -> dict:
    from datetime import datetime
    import uuid

    # Split time window like "2025-09-04 00:00-06:00"
    # date_part, hour_range = time_window.strip().split(" ")
    parts = time_window.strip().split(" ")
    date_part = parts[0]
    hour_range = parts[1] if len(parts) > 1 else "00:00-01:00"  # fallback
    # start_hour, end_hour = hour_range.split("-")
    start_hour, end_hour = hour_range.split("-")
    end_hour = end_hour.strip().replace('"', '').replace(',', '')
    # Ensure hours are in HH:MM format
    if len(start_hour.split(":")) == 1:
        start_hour += ":00"
    if len(end_hour.split(":")) == 1:
        end_hour += ":00"

    # Add ":00" to make HH:MM:SS
    start = f"{date_part}T{start_hour}"
    end = f"{date_part}T{end_hour}"

    now = datetime.utcnow().isoformat() + "Z"
    txn_id = str(uuid.uuid4())

    return {
        "context": {
            "domain": "energy",
            "action": "search",
            "location": {
                "country": {"name": "India", "code": "IND"},
                "city": {"name": "Lucknow", "code": "std:522"}
            },
            "version": "1.1.0",
            "bap_id": "p2pTrading-bap.com",
            "bap_uri": "https://api.p2pTrading-bap.com/pilot/bap/energy/v1",
            "transaction_id": txn_id,
            "message_id": txn_id,
            "timestamp": now
        },
        "message": {
            "intent": {
                "item": {
                    "descriptor": {"code": "energy"},
                    "quantity": {
                        "selected": {
                            "measure": {"value": str(quantity_kwh), "unit": "kWH"}
                        }
                    }
                },
                "fulfillment": {
                    "agent": {
                        "organization": {
                            "descriptor": {"name": "UPPCL"}
                        }
                    },
                    "stops": [{
                        "type": "end",
                        "location": {"address": "der://uppcl.meter/98765456"},
                        "time": {
                            "range": {
                                "start": start,
                                "end": end
                            }
                        }
                    }]
                }
            }
        }
    }

def post_search(payload: dict, gateway_url: str = "http://localhost:4030/search"):
    print("🔍 Final JSON Payload:\n", json.dumps(payload, indent=2))
    response = requests.post(gateway_url, json=payload)
    try:
        return response.status_code, response.json()
    except requests.exceptions.JSONDecodeError:
        return response.status_code, response.text


def load_on_search_payload(path="deg/on_search_payload.json"):
    with open(path, 'r') as f:
        return json.load(f)

    

def post_on_search(payload: dict, gateway_url: str = "http://localhost:4030/on_search"):
    response = requests.post(gateway_url, json=payload)

    try:
        return response.status_code, response.json()
    except requests.exceptions.JSONDecodeError:
        print("\n⚠️ Response was not JSON. Raw response:")
        print(response.text)
        return response.status_code, response.text