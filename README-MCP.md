# Solinteg MCP Server & Langchain Agent Example

This project provides a Model Context Protocol (MCP) server for interacting with the Solinteg OpenAPI v2.0 for solar inverter monitoring. It also includes an example Langchain agent that uses this MCP server to fetch device data.

The setup uses `uv` for fast Python package management and virtual environments.

## Prerequisites

*   **Python 3.10+**
*   **`uv` pipx installation:** `uv` is a fast Python package installer and resolver. Install it via pipx (recommended):
    ```bash
    pipx install uv
    ```
    If you don't have pipx, install it first (e.g., `pip install pipx`, then `pipx ensurepath`).
*   **Solinteg OpenAPI Account:** You will need valid credentials (account/email and password) for the Solinteg cloud platform that your devices are registered to.
*   **Google Gemini API Key:** The example agent (`run_solinteg_agent.py`) uses a Google Gemini model (e.g., `gemini-2.0-flash`). You will need a Google API key for this. You can add your own key to the `.env` file, or use the one potentially pre-configured if provided.

## Setup Instructions

1.  **Extract the Code:**
    Unzip the provided codebase zip file into a directory of your choice.

2.  **Create a Virtual Environment using `uv`:**
    Navigate to the project directory (where `solinteg_mcp_server.py` is located) in your terminal and run:
    ```bash
    uv venv
    ```
    This will create a virtual environment named `.venv` in your project directory.

3.  **Activate the Virtual Environment:**
    *   On macOS/Linux:
        ```bash
        source .venv/bin/activate
        ```
    *   On Windows (PowerShell):
        ```bash
        .venv\Scripts\Activate.ps1
        ```
    *   On Windows (CMD):
        ```bash
        .venv\Scripts\activate.bat
        ```
    Your terminal prompt should now indicate that you are in the `.venv` environment.

4.  **Install Dependencies using `uv`:**
    The required Python packages are listed in the included `requirements.txt` file.
    Install them using `uv`:
    ```bash
    uv pip install -r requirements.txt
    ```
    `uv` will resolve and install these packages very quickly.

5.  **Configure Environment Variables:**
    The MCP server and the Langchain agent rely on environment variables for API credentials and other configurations.
    An `.env` file should be included in the project directory.

    **Important:** Open the `.env` file and ensure it contains your Solinteg API details and confirm the Google API Key:
    ```env
    # .env file content (Example - REPLACE PLACEHOLDERS)

    # Solinteg API Configuration (for solinteg_mcp_server.py)
    SOLINTEG_BASE_URL=https://eu.solinteg-cloud.com/openapi/v2 
    # Or your region-specific base URL, e.g., https://us.solinteg-cloud.com/openapi/v2
    SOLINTEG_AUTH_ACCOUNT=your_solinteg_email@example.com
    SOLINTEG_AUTH_PASSWORD=your_solinteg_password

    # Google Gemini API Key (for run_solinteg_agent.py)
    # Replace with your own key if needed or use the one provided.
    GOOGLE_API_KEY=your_google_gemini_api_key_here
    ```
    *   **Replace placeholder values** (`your_solinteg_email@example.com`, `your_solinteg_password`, `your_google_gemini_api_key_here`) with your actual Solinteg credentials and your preferred Google Gemini API key.

## Running the MCP Server and Agent

You have two main ways to interact with the system:

### Option 1: Running the MCP Server Directly (for development/inspection)

You can run the `solinteg_mcp_server.py` directly to interact with its tools without the Langchain agent.

1.  **Ensure your virtual environment is activated.**
2.  **Run with MCP Dev Inspector:**
    The MCP CLI includes a development inspector tool.
    ```bash
    mcp dev solinteg_mcp_server.py
    ```
    This will start the server and open a web interface (usually at `http://localhost:8787`) where you can see and call the available MCP tools.

### Option 2: Running the Langchain Agent (`run_solinteg_agent.py`)

The `run_solinteg_agent.py` script demonstrates using the MCP server. It starts the server as a subprocess, connects to it, fetches/caches the device list, and directly invokes tools for a random subset of devices.

1.  **Ensure your virtual environment is activated.**
2.  **Ensure the `.env` file is correctly configured** with your credentials.
3.  **Check `SOLINTEG_SERVER_SCRIPT_PATH` in `run_solinteg_agent.py`:**
    The script assumes `solinteg_mcp_server.py` is in the same directory. If you move files around, you might need to adjust the `SOLINTEG_SERVER_SCRIPT_PATH` variable within `run_solinteg_agent.py` to be the correct *absolute path* to your server script.
4.  **Run the agent script:**
    ```bash
    python run_solinteg_agent.py
    ```

    **Expected Behavior of `run_solinteg_agent.py`:**
    *   **First Run:** It will attempt to fetch all devices via the `list_linked_devices` tool (this can be slow), save the results to `all_devices.json`, select up to 8 random devices, and then directly invoke `get_device_realtime_data` and `get_device_config_data` for each selected device using Python loops.
    *   **Subsequent Runs:** It will find `all_devices.json`, load the device list from the file (fast), select devices, and proceed with direct tool invocations, skipping the slow initial API call.

## Project Structure

```
your-project-directory/
├── .venv/                     # Virtual environment created by uv
├── solinteg_mcp_server.py     # The MCP server script
├── run_solinteg_agent.py      # The Langchain agent client script
├── requirements.txt           # Python dependencies
├── .env                       # Environment variables (API keys, credentials)
├── all_devices.json           # Cache file for device list (created by run_solinteg_agent.py)
└── README.md                  # This file
```
