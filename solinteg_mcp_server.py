import asyncio
import os
import httpx
import time
import logging
import json
from typing import Any, Dict, List, Optional, Tuple
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass

from dotenv import load_dotenv
from pydantic import BaseModel, Field # Optional: For better data structuring

from mcp.server.fastmcp import FastMCP, Context

# --- Configuration & Setup ---

load_dotenv() # Load variables from .env file

# Configure standard logging
logging.basicConfig(
    level=logging.INFO, # Adjust level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    # stream=sys.stderr # Default is stderr, which is good
)
log = logging.getLogger(__name__) # Get a logger instance

# Pydantic models (Optional but recommended for clarity and validation)
class DeviceInfo(BaseModel):
    deviceSn: str
    deviceName: Optional[str] = None
    modelType: Optional[str] = None
    soc: Optional[float] = None
    uploadTime: Optional[str] = None

class SetParameterResult(BaseModel):
    success: bool
    message: str
    recordId: Optional[str] = None
    finalValue: Optional[str] = None

class CommandCheckResult(BaseModel):
    success: bool
    controlResult: Optional[bool] = None
    currentValue: Optional[str] = None
    errorMessage: Optional[str] = None

class FirmwareInfo(BaseModel):
    fileName: str
    fileUrl: str
    firmwareType: str
    hardVersion: str
    upgradeVersion: str

class AvailableFirmware(BaseModel):
    deviceSN: str
    runType: str
    beforeVersion: str
    afterVersion: str
    firmwareReqs: List[FirmwareInfo]

class UpgradeProgress(BaseModel):
    progress: str
    status: str # e.g., "BURNING", "SUCCESS", "FAILED"

# --- Lifespan Management & State ---

@dataclass
class ServerContext:
    """Holds server-wide state accessible via lifespan context"""
    http_client: httpx.AsyncClient
    solinteg_token: Optional[str] = None
    token_expiry_time: float = 0.0
    base_url: str = Field(default_factory=lambda: os.getenv("SOLINTEG_BASE_URL", ""))
    auth_account: str = Field(default_factory=lambda: os.getenv("SOLINTEG_AUTH_ACCOUNT", ""))
    auth_password: str = Field(default_factory=lambda: os.getenv("SOLINTEG_AUTH_PASSWORD", ""))

    # --- Server-side cache for linked_devices ---
    linked_devices_cache: Optional[List[Dict[str, Any]]] = None # In-memory cache
    linked_devices_cache_timestamp: float = 0.0
    linked_devices_cache_ttl_seconds: int = 30 * 24 * 3600 # 1 month TTL
    linked_devices_cache_file_path: str = "server_device_cache.json"

    # --- Remove Caching and Background Task State ---
    # linked_devices_cache: Optional[List[Dict[str, Any]]] = None
    # cache_timestamp: float = 0.0
    # refresh_tasks: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    # is_refreshing: bool = False

async def _login(client: httpx.AsyncClient, base_url: str, account: str, password: str) -> Optional[str]:
    """Logs into Solinteg API and returns the token."""
    login_url = f"{base_url}/loginv2/auth"
    payload = {"authAccount": account, "authPassword": password}
    try:
        log.info(f"Attempting login to {login_url}...")
        response = await client.post(login_url, json=payload, timeout=20.0)
        response.raise_for_status()
        data = response.json()
        if data.get("successful") and data.get("errorCode") == 0:
            log.info("Login successful.")
            return data.get("body")
        else:
            err_code = data.get('errorCode')
            err_info = data.get('info')
            log.error(f"Login failed: errorCode={err_code}, info={err_info}")
            return None
    except httpx.HTTPStatusError as e:
        log.error(f"Login HTTP Error: {e.response.status_code} - {e.response.text}", exc_info=True)
        return None
    except Exception as e:
        log.error(f"Login Exception: {e}", exc_info=True)
        return None

@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[ServerContext]:
    """Manage application lifecycle: HTTP client and initial auth token."""
    state = ServerContext(
        http_client=httpx.AsyncClient(timeout=30.0),
        base_url=os.getenv("SOLINTEG_BASE_URL"),
        auth_account=os.getenv("SOLINTEG_AUTH_ACCOUNT"),
        auth_password=os.getenv("SOLINTEG_AUTH_PASSWORD"),
    )

    # Try to load device list from JSON cache on startup
    try:
        if os.path.exists(state.linked_devices_cache_file_path):
            with open(state.linked_devices_cache_file_path, 'r') as f:
                file_cache_data = json.load(f)
            cached_timestamp = file_cache_data.get("timestamp", 0)
            cached_devices = file_cache_data.get("devices")

            if cached_devices is not None and \
               (time.time() < cached_timestamp + state.linked_devices_cache_ttl_seconds):
                state.linked_devices_cache = cached_devices
                state.linked_devices_cache_timestamp = cached_timestamp
                log.info(f"Successfully loaded {len(cached_devices)} devices from JSON cache into memory on startup.")
            else:
                log.info("JSON cache on startup was stale or invalid, will fetch on first request.")
        else:
            log.info(f"JSON cache file '{state.linked_devices_cache_file_path}' not found on startup. Will create on first fetch.")
    except Exception as e:
        log.error(f"Error loading JSON cache on startup: {e}", exc_info=True)

    if not all([state.base_url, state.auth_account, state.auth_password]):
        log.critical("Error: SOLINTEG environment variables not set!")
        # In a real app, might raise an exception or handle differently
        # For now, proceed but expect failures
    else:
        # Initial login attempt
        log.info("Attempting initial login during startup...")
        state.solinteg_token = await _login(state.http_client, state.base_url, state.auth_account, state.auth_password)
        if state.solinteg_token:
            state.token_expiry_time = time.time() + 3000 # Assume ~50 min validity for safety
            log.info("Initial login successful.")
        else:
            log.warning("Initial login failed. Will retry on first request.")

    try:
        yield state # Provide state to MCP context
    finally:
        log.info("Closing HTTP client...")
        await state.http_client.aclose()
        log.info("Server shutdown complete.")

# --- MCP Server Definition ---

mcp = FastMCP(
    "SolintegOpenAPI_V2",
    version="0.2.0",
    lifespan=app_lifespan,
    description="MCP Server for interacting with the Solinteg OpenAPI for solar inverter monitoring and control."
)

# --- Helper for Authenticated Requests ---

async def _get_valid_token(state: ServerContext) -> Optional[str]:
    """Gets a valid token, logging in again if needed."""
    log.debug("Checking token validity...") # <-- DEBUG level log
    if not state.base_url or not state.auth_account or not state.auth_password:
         log.error("Cannot get token: Credentials or base URL missing.")
         return None

    if state.solinteg_token and time.time() < state.token_expiry_time:
        log.debug("Existing token is valid.") # <-- DEBUG level log
        return state.solinteg_token

    log.warning("Token expired or missing, attempting re-login...")
    state.solinteg_token = await _login(state.http_client, state.base_url, state.auth_account, state.auth_password)
    if state.solinteg_token:
        log.info("Re-login successful, new token obtained.") # <-- INFO level log
        state.token_expiry_time = time.time() + 3000 # Reset expiry
        return state.solinteg_token
    else:
        log.error("Re-login attempt failed.")
        return None

async def _make_request(
    ctx: Context, # MCP Context to access lifespan state
    method: str,
    endpoint: str,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    specific_timeout: float = 70.0 # Default specific timeout for potentially long calls
) -> Tuple[Optional[Any], Optional[str]]: # Return type can be Dict or List
    """Makes an authenticated request to the Solinteg API."""
    log.info(f"_make_request called for: {method} {endpoint} with params {params}")
    state: ServerContext = ctx.request_context.lifespan_context

    log.info("Attempting to get valid token...") # <-- Log before get_valid_token
    token = await _get_valid_token(state)
    log.info(f"_get_valid_token returned: {'Token obtained' if token else 'No token'}") # <-- Log after get_valid_token

    if not token:
        log.error(f"Authentication failed or token unavailable for {method} {endpoint}")
        return None, "Authentication failed or token unavailable."

    headers = {"token": token}
    url = f"{state.base_url}{endpoint}"

    try:
        log.info(f"Attempting HTTP request: {method} {url}")
        response = await state.http_client.request(
            method, url, headers=headers, params=params, json=json_body, timeout=specific_timeout
        )
        log.info(f"HTTP request completed for {method} {url}. Status: {response.status_code}")

        response.raise_for_status() # Raise exception for 4xx/5xx errors
        data = response.json()

        if data.get("successful") and data.get("errorCode") == 0:
            return data.get("body"), None
        else:
            error_message = f"API Error (errorCode={data.get('errorCode')}): {data.get('info')}"
            log.warning(error_message)
            return None, error_message

    except httpx.HTTPStatusError as e:
        error_text = e.response.text
        try: # Try to parse error response as JSON for more details
            error_details = e.response.json()
            error_text = f"{error_details.get('info', e.response.text)} (errorCode={error_details.get('errorCode')})"
        except:
            pass # Keep original text if not JSON
        error_message = f"HTTP Error: {e.response.status_code} for {method} {url}. Response: {error_text}"
        log.error(error_message)
        return None, error_message
    except Exception as e:
        error_message = f"Request Exception for {method} {url}: {e}"
        log.error(error_message, exc_info=True)
        return None, error_message

async def _check_command_result(ctx: Context, record_id: str, setting_code: str, poll_interval: float = 2.0, timeout: float = 30.0) -> CommandCheckResult:
    """Polls the checkControlResult endpoint."""
    start_time = time.time()
    state: ServerContext = ctx.request_context.lifespan_context
    params = {"recordId": record_id}

    while time.time() - start_time < timeout:
        await asyncio.sleep(poll_interval)
        log.info(f"Checking command result for recordId {record_id}...")
        body, error = await _make_request(ctx, "GET", "/cmd/checkControlResult", params=params)

        if error:
            log.warning(f"Error checking status for {record_id}: {error}")
            return CommandCheckResult(success=False, errorMessage=f"Error checking status: {error}")
        if not body:
             log.warning(f"Empty body received while checking status for {record_id}.")
             return CommandCheckResult(success=False, errorMessage="Empty body received while checking status.")

        # Check structure based on Postman example: body contains a dict where key is settingCode
        if setting_code in body:
             result_data = body[setting_code]
             control_result = result_data.get("controlResult")
             current_value = result_data.get("currentValue")
             if control_result is True:
                 log.info(f"Command {record_id} ({setting_code}) successful. Current value: {current_value}")
                 return CommandCheckResult(success=True, controlResult=True, currentValue=current_value)
             elif control_result is False:
                 # API might return false if still processing or if failed, need clarification
                 # Assuming false means failure for now
                 log.warning(f"Command {record_id} ({setting_code}) reported failure by API.")
                 return CommandCheckResult(success=False, controlResult=False, currentValue=current_value, errorMessage="Command failed according to API.")
             else:
                 # Still processing or unknown state
                 log.info(f"Command {record_id} ({setting_code}) status pending...")
        else:
             # Fallback for simpler check endpoints like timearray/battery/check returning just boolean
             if isinstance(body, bool):
                if body is True:
                     log.info(f"Command {record_id} ({setting_code}) successful (boolean check).")
                     return CommandCheckResult(success=True, controlResult=True)
                else:
                     # Assuming false means failure here too
                     log.warning(f"Command {record_id} ({setting_code}) failed (boolean check).")
                     return CommandCheckResult(success=False, controlResult=False, errorMessage="Command failed (boolean check).")

             log.warning(f"Command {record_id} status check response format unexpected or still pending: {body}")

    log.error(f"Command {record_id} ({setting_code}) timed out after {timeout}s.")
    return CommandCheckResult(success=False, errorMessage="Timeout waiting for command completion.")

# --- MCP Tools (v2.0 API) ---

@mcp.tool()
async def list_linked_devices(ctx: Context) -> List[Dict[str, Any]]:
    """
    Retrieves a list of all devices that have been on the cloud, 
    including their SN and last cloud access time.
    Corresponds to API: /wrapper/topic/getLinkedDevices
    WARNING: This call can be slow for accounts with many devices.
    This tool uses server-side caching (in-memory and JSON file) with a 1-month TTL.
    """
    log.info("Tool 'list_linked_devices' (v2.0) called.")
    state: ServerContext = ctx.request_context.lifespan_context
    current_time = time.time()

    # 1. Check in-memory cache
    if state.linked_devices_cache and \
       (current_time < state.linked_devices_cache_timestamp + state.linked_devices_cache_ttl_seconds):
        log.info("Returning in-memory cached list_linked_devices data.")
        return state.linked_devices_cache

    # 2. Check file cache if in-memory is stale or missing
    try:
        if os.path.exists(state.linked_devices_cache_file_path):
            with open(state.linked_devices_cache_file_path, 'r') as f:
                file_cache_data = json.load(f)
            cached_timestamp = file_cache_data.get("timestamp", 0)
            cached_devices = file_cache_data.get("devices")

            if cached_devices is not None and \
               (current_time < cached_timestamp + state.linked_devices_cache_ttl_seconds):
                log.info("Returning file-cached list_linked_devices data and updating in-memory cache.")
                state.linked_devices_cache = cached_devices
                state.linked_devices_cache_timestamp = cached_timestamp
                return state.linked_devices_cache
            else:
                log.info("JSON cache was stale or invalid.")
    except Exception as e:
        log.warning(f"Could not load or parse JSON cache file '{state.linked_devices_cache_file_path}': {e}")

    # 3. Fetch from API (all caches miss or expired)
    log.info("Fetching list_linked_devices from API (all caches miss or expired).")
    body, error = await _make_request(ctx, "GET", "/wrapper/topic/getLinkedDevices")
    
    if error:
        log.error(f"Error in 'list_linked_devices' API call: {error}")
        # If API fails, consider if stale data (even if beyond TTL) from file is acceptable.
        # For now, if we have ANY data in file_cache_devices (even if stale from above read attempt),
        # we could return it as a last resort if API fails. 
        # This part is tricky: do we prefer stale data over error?
        # Current logic: raises error to indicate fresh data retrieval failure if no valid cache hit before API call.
        raise ValueError(f"Error listing linked devices from API: {error}")

    if isinstance(body, list):
        fetched_devices = body
        fetch_timestamp = current_time

        # Update in-memory cache
        state.linked_devices_cache = fetched_devices
        state.linked_devices_cache_timestamp = fetch_timestamp

        # Update file cache
        data_to_save = {"timestamp": fetch_timestamp, "devices": fetched_devices}
        try:
            with open(state.linked_devices_cache_file_path, 'w') as f:
                json.dump(data_to_save, f, indent=4)
            log.info(f"Successfully saved {len(fetched_devices)} devices to JSON cache file '{state.linked_devices_cache_file_path}'.")
        except Exception as e:
            log.error(f"Error saving devices to JSON cache file: {e}", exc_info=True)
        
        log.info(f"Successfully fetched, cached in memory, and attempted to save to file {len(fetched_devices)} linked devices.")
        return fetched_devices
    else:
        log.error(f"Unexpected body type from getLinkedDevices: {type(body)}")
        raise ValueError("Unexpected data format from API for linked devices.")
    # Expected body is List[{"deviceSn": str, "lastUploadTime": str | None}]
    return body if isinstance(body, list) else []

@mcp.tool()
async def get_devices_by_topic(ctx: Context, topic: str) -> List[Dict[str, Any]]:
    """
    Obtain all devices under your account for a specific topic and their basic information.
    Corresponds to API: /wrapper/topic/getDeviceByTopic
    """
    log.info(f"Tool 'get_devices_by_topic' (v2.0) called for topic: {topic}")
    if not topic:
        raise ValueError("Topic parameter is required for get_devices_by_topic.")
    params = {"topic": topic}
    body, error = await _make_request(ctx, "GET", "/wrapper/topic/getDeviceByTopic", params=params)
    if error:
        log.error(f"Error in 'get_devices_by_topic' for topic {topic}: {error}")
        raise ValueError(f"Error getting devices for topic {topic}: {error}")
    # Expected body is List[{"deviceSn": str, "modelType": str, "firmwareVersion": str, "uploadTime": str | None}]
    return body if isinstance(body, list) else []

@mcp.tool()
async def get_device_config_data(ctx: Context, deviceSn: str) -> Dict[str, Any]:
    """
    Fetches the current configuration parameters for a specific device SN.
    Corresponds to API: /wrapper/device/queryDeviceConfigData
    """
    log.info(f"Tool 'get_device_config_data' (v2.0) called for device: {deviceSn}")
    params = {"deviceSn": deviceSn}
    body, error = await _make_request(ctx, "GET", "/wrapper/device/queryDeviceConfigData", params=params)
    if error:
        log.error(f"Error in 'get_device_config_data' for {deviceSn}: {error}")
        raise ValueError(f"Failed to get config data for {deviceSn}: {error}")
    return body if isinstance(body, dict) else {}

@mcp.tool()
async def get_device_history_config_data(ctx: Context, deviceSn: str, startTime: str, endTime: str) -> List[Dict[str, Any]]:
    """
    Fetches historical configuration data for a device within a specified time range.
    Time format for startTime and endTime: 'YYYY-MM-DD HH:MM:SS'.
    The time difference cannot exceed 24 hours. End time must be greater than start time.
    Timezone conversion may be required based on device's actual timezone.
    Corresponds to API: /wrapper/device/queryHistoryDeviceConfigData
    """
    log.info(f"Tool 'get_device_history_config_data' (v2.0) for {deviceSn} from {startTime} to {endTime}")
    params = {"deviceSn": deviceSn, "startTime": startTime, "endTime": endTime}
    # Potentially shorter timeout might be fine for this specific call if it's typically faster
    body, error = await _make_request(ctx, "GET", "/wrapper/device/queryHistoryDeviceConfigData", params=params, specific_timeout=30.0)
    if error:
        log.error(f"Error in 'get_device_history_config_data' for {deviceSn}: {error}")
        raise ValueError(f"Failed to get history config data for {deviceSn}: {error}")
    return body if isinstance(body, list) else []

@mcp.tool()
async def get_device_realtime_data(ctx: Context, deviceSn: str) -> Dict[str, Any]:
    """
    Fetches the latest realtime operational data for a specific device SN.
    Corresponds to API: /wrapper/device/queryDeviceRealtimeData
    """
    log.info(f"Tool 'get_device_realtime_data' (v2.0) called for device: {deviceSn}")
    params = {"deviceSn": deviceSn}
    body, error = await _make_request(ctx, "GET", "/wrapper/device/queryDeviceRealtimeData", params=params)
    if error:
        log.error(f"Error in 'get_device_realtime_data' for {deviceSn}: {error}")
        raise ValueError(f"Failed to get realtime data for {deviceSn}: {error}")
    return body if isinstance(body, dict) else {}

@mcp.tool()
async def get_device_history_data(ctx: Context, deviceSn: str, startTime: str, endTime: str) -> List[Dict[str, Any]]:
    """
    Fetches historical operational data points for a device within a specified time range.
    Time format for startTime and endTime: 'YYYY-MM-DD HH:MM:SS' (0 timezone).
    Timezone conversion may be required. Max 24-hour range. End time > start time.
    Corresponds to API: /wrapper/history/query
    """
    log.info(f"Tool 'get_device_history_data' (v2.0) for {deviceSn} from {startTime} to {endTime}")
    params = {"deviceSn": deviceSn, "startTime": startTime, "endTime": endTime}
    # Potentially shorter timeout
    body, error = await _make_request(ctx, "GET", "/wrapper/history/query", params=params, specific_timeout=30.0)
    if error:
        log.error(f"Error in 'get_device_history_data' for {deviceSn}: {error}")
        raise ValueError(f"Failed to get history data for {deviceSn}: {error}")
    return body if isinstance(body, list) else []

# --- Smart Device Tools (v2.0 API - Note: these do NOT use /wrapper prefix) ---

@mcp.tool()
async def get_smart_device_config_data(ctx: Context, deviceSn: str) -> Dict[str, Any]:
    """
    Fetches configuration data for a specific Smart Device SN.
    Corresponds to API: /device/querySmartDeviceConfigData (No /wrapper prefix)
    """
    log.info(f"Tool 'get_smart_device_config_data' (v2.0) for smart device: {deviceSn}")
    params = {"deviceSn": deviceSn}
    # Note: Endpoint does not start with /wrapper/
    body, error = await _make_request(ctx, "GET", "/device/querySmartDeviceConfigData", params=params)
    if error:
        log.error(f"Error in 'get_smart_device_config_data' for {deviceSn}: {error}")
        raise ValueError(f"Failed to get smart device config data for {deviceSn}: {error}")
    return body if isinstance(body, dict) else {}

@mcp.tool()
async def get_smart_device_history_config_data(ctx: Context, deviceSn: str, startTime: str, endTime: str) -> List[Dict[str, Any]]:
    """
    Fetches historical configuration data for a Smart Device within a specified time range.
    Time format for startTime and endTime: 'YYYY-MM-DD HH:MM:SS'. Max 24-hour range.
    Corresponds to API: /device/queryHistorySmartDeviceConfigData (No /wrapper prefix)
    """
    log.info(f"Tool 'get_smart_device_history_config_data' (v2.0) for {deviceSn} from {startTime} to {endTime}")
    params = {"deviceSn": deviceSn, "startTime": startTime, "endTime": endTime}
    # Note: Endpoint does not start with /wrapper/
    body, error = await _make_request(ctx, "GET", "/device/queryHistorySmartDeviceConfigData", params=params, specific_timeout=30.0)
    if error:
        log.error(f"Error in 'get_smart_device_history_config_data' for {deviceSn}: {error}")
        raise ValueError(f"Failed to get smart device history config data for {deviceSn}: {error}")
    return body if isinstance(body, list) else []

@mcp.tool()
async def get_smart_device_realtime_data(ctx: Context, deviceSn: str) -> Dict[str, Any]:
    """
    Fetches the latest realtime data for a specific Smart Device SN.
    Corresponds to API: /device/querySmartDeviceRealtimeData (No /wrapper prefix)
    """
    log.info(f"Tool 'get_smart_device_realtime_data' (v2.0) for smart device: {deviceSn}")
    params = {"deviceSn": deviceSn}
    # Note: Endpoint does not start with /wrapper/
    body, error = await _make_request(ctx, "GET", "/device/querySmartDeviceRealtimeData", params=params)
    if error:
        log.error(f"Error in 'get_smart_device_realtime_data' for {deviceSn}: {error}")
        raise ValueError(f"Failed to get smart device realtime data for {deviceSn}: {error}")
    return body if isinstance(body, dict) else {}

@mcp.tool()
async def get_smart_device_history_data(ctx: Context, deviceSn: str, startTime: str, endTime: str) -> List[Dict[str, Any]]:
    """
    Fetches historical data for a Smart Device within a specified time range.
    Time format for startTime and endTime: 'YYYY-MM-DD HH:MM:SS'. Max 24-hour range.
    Corresponds to API: /history/querySmartDevice (No /wrapper prefix)
    """
    log.info(f"Tool 'get_smart_device_history_data' (v2.0) for {deviceSn} from {startTime} to {endTime}")
    params = {"deviceSn": deviceSn, "startTime": startTime, "endTime": endTime}
    # Note: Endpoint does not start with /wrapper/
    body, error = await _make_request(ctx, "GET", "/history/querySmartDevice", params=params, specific_timeout=30.0)
    if error:
        log.error(f"Error in 'get_smart_device_history_data' for {deviceSn}: {error}")
        raise ValueError(f"Failed to get smart device history data for {deviceSn}: {error}")
    return body if isinstance(body, list) else []

# --- Main Execution ---
if __name__ == "__main__":
    log.info("Starting SolintegOpenAPI_V2 MCP server...")
    # For local development, runs the server over stdio
    # Use 'mcp dev solinteg_mcp_server.py' to run with Inspector
    # Use 'mcp install solinteg_mcp_server.py' for Claude Desktop
    try:
        mcp.run(transport="stdio")
    except Exception as e:
        log.critical(f"Server failed to run: {e}", exc_info=True)
        raise # Re-raise the exception