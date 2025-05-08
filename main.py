# main.py
from agents.agent import EnergyAgent
from deg.gateway_client import build_search_payload, post_search, load_on_search_payload, post_on_search
import json
import re
import subprocess

# Step 1: Decide agent role and data path
role = "consumer"  # or "prosumer"
data_path = "data/consumption_data.csv" if role == "consumer" else "data/generation_data.csv"

# Step 2: Run the agent to get recommendation
agent = EnergyAgent(role=role, data_path=data_path)
response = agent.decide_energy_action()
print("\n🔍 LLM Agent Response:", response)

# Step 3: Extract time window from LLM output using regex
match = re.search(r'\["(.*?)"\]', response)
if not match:
    print("❌ Could not parse recommended time window from agent response.")
    exit()
time_window = match.group(1)
print("\n⏱️ Selected Time Window:", time_window)

# Step 4: Build DEG /search payload
payload = build_search_payload(time_window)
print("\n📦 Payload to DEG:")
print(json.dumps(payload, indent=2))

# Step 5: POST to DEG Gateway
status, reply = post_search(payload)
print("\n🌐 DEG Response:", status)
print(json.dumps(reply, indent=2) if isinstance(reply, dict) else reply)

print("\n🤖 Simulating BPP Agent to respond to /on_search...")

# Run the BPP simulation script
subprocess.run(["python", "deg/bpp_responder.py"])

# Step 6: Simulate Prosumer (Agent B) replying with /on_search
print("\n📡 Simulating BPP Agent Replying with /on_search...")

on_search_payload = load_on_search_payload()  # loads from on_search_payload.json
status, reply = post_on_search(on_search_payload)

print("\n✅ BPP /on_search Response:", status)
print(json.dumps(reply, indent=2) if isinstance(reply, dict) else reply)