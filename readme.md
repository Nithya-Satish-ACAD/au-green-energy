# au-green-energy

This repository contains the implementation of a decentralized peer-to-peer energy trading simulation using the Beckn Protocol and the Distributed Energy Gateway (DEG) framework, powered by Agentic AI agents for dynamic decision-making and grid support.

## 📦 Project Components

- **BAP (Consumer Agent):** Sends `/search` requests to discover available prosumers.
- **BPP (Prosumer Agent):** Responds with `/on_search` including energy offers.
- **DEG Gateway:** Locally hosted gateway facilitating Beckn-compliant message flow.
- **Agent Simulation Framework:** Built using LangChain to support intelligent agent behavior.
- **MCP (Model Context Protocol):** To be integrated for secure and structured inter-agent communication.
- **Grid Agent (Upcoming):** Will use MCP to fetch DER states and issue control signals.

## ✅ Current Status

- [x] Local network is set up
- [x] DEG Gateway is up and running
- [x] Consumer agent (BAP) implemented
- [x] Prosumer agent (BPP) implemented
- [x] Prompts for agents finalized
- [x] BAP can send `/search` requests
- [x] BPP can respond with `/on_search` offers
- [x] All requests pass successfully through the DEG Gateway

## 🐞 Known Issue

Currently, BAP and BPP responses are being redirected to a login page. This seems to be due to unregistered or unauthenticated agents in the local registry. We're awaiting clarification and support from the Beckn team during the open hour today (8:00 PM).

## 🔜 Next Steps

- [ ] Complete BAP/BPP registration on local Beckn registry
- [ ] Integrate MCP server into agent workflow
- [ ] Finalize Grid Agent with DER monitoring and control
- [ ] Enable voltage regulation and reverse flow mitigation

## 🛠️ Tech Stack

- Python 3.13+
- Beckn Protocol (DEG Sandbox schema)
- LangChain
- JSON-based payload interactions
- Local-only deployment (no cloud dependencies)

## 📂 Structure

```bash
agentic_energy_simulation/
├── agents/                 # LLM agent logic
├── data/                   # Sample energy data
├── deg/                    # DEG schema and payload templates
├── utils/                  # Utility functions
├── main.py                 # Entry point for testing
├── gateway_client.py       # DEG client simulation
├── bpp_responder.py        # BPP response logic
├── requirements.txt
└── README.md
