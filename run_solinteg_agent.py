# run_solinteg_agent.py
import asyncio
import os
import random
import json
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters # Core MCP library
from mcp.client.stdio import stdio_client         # For stdio connections
from datetime import datetime, timedelta # For history data prompts
from typing import List

# The adapter library
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_core.tools import Tool # For type hinting

from langgraph.prebuilt import create_react_agent
from langchain_google_genai import ChatGoogleGenerativeAI # For Gemini
# from langchain_openai import ChatOpenAI # Or your preferred LLM, e.g., ChatGoogleGenerativeAI

# --- IMPORTANT CONFIGURATION ---
# Load environment variables from .env file first
load_dotenv()

# 1. Set GOOGLE_API_KEY as an environment variable (now loaded from .env if present)
#    e.g., export OPENAI_API_KEY="sk-..." or GOOGLE_API_KEY="..."

# 2. Provide the ABSOLUTE PATH to your Solinteg MCP server script
#    __file__ refers to the location of *this* run_solinteg_agent.py script
#    Adjust if solinteg_mcp_server.py is elsewhere
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SOLINTEG_SERVER_SCRIPT_PATH = os.path.join(SCRIPT_DIR, "solinteg_mcp_server.py")
# --- END CONFIGURATION ---


async def main():
    # Ensure your .env file (for SOLINTEG_BASE_URL etc.) is in the same directory as
    # solinteg_mcp_server.py or that the server script can find it.
    print(f"Attempting to start MCP server: {SOLINTEG_SERVER_SCRIPT_PATH}")
    if not os.path.exists(SOLINTEG_SERVER_SCRIPT_PATH):
        print(f"ERROR: Solinteg server script not found at {SOLINTEG_SERVER_SCRIPT_PATH}")
        print("Please update SOLINTEG_SERVER_SCRIPT_PATH with the correct absolute path.")
        return

    # Initialize your chosen LLM
    # GOOGLE_API_KEY should now be loaded from .env if it was set there
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        print("ERROR: GOOGLE_API_KEY not found in environment variables or .env file.")
        print("Please ensure it is set for Gemini models.")
        return
    
    try:
        model_name = "gemini-2.0-flash"
        print(f"Using LLM: {model_name} (GOOGLE_API_KEY found)")
        llm = ChatGoogleGenerativeAI(model=model_name)
    except Exception as e:
        print(f"Error initializing LLM. Ensure GOOGLE_API_KEY is set and model name is correct: {e}")
        return

    server_params = StdioServerParameters(
        command="python",
        args=[SOLINTEG_SERVER_SCRIPT_PATH],
    )

    async with stdio_client(server_params) as (read, write):
        session = ClientSession(read, write)
        session.default_timeout_ms = 120000  # Increased to 120 seconds

        async with session:
            await session.initialize()
            print("MCP session initialized with Solinteg server.")

            all_device_sns = []
            selected_device_sns = []
            devices_json_file = "all_devices.json"
            raw_device_list_from_file_or_tool = []
            tools_from_mcp: List[Tool] = [] # Ensure it's defined and typed

            # --- Step 1: Check for existing device list or fetch if needed ---
            if os.path.exists(devices_json_file) and os.path.getsize(devices_json_file) > 0:
                print(f"\n--- Step 1: Found existing device list: {devices_json_file}. Loading... ---")
                try:
                    with open(devices_json_file, 'r') as f:
                        loaded_data = json.load(f)
                    
                    processed_loaded_data = []
                    if isinstance(loaded_data, list):
                        for item in loaded_data:
                            if isinstance(item, str):
                                try:
                                    # If item is a string, try to parse it as JSON
                                    processed_loaded_data.append(json.loads(item))
                                except json.JSONDecodeError:
                                    print(f"Warning: Could not decode string item in JSON to dict: {item[:100]}...")
                                    # Optionally skip or handle error
                            elif isinstance(item, dict):
                                processed_loaded_data.append(item)
                            else:
                                print(f"Warning: Unexpected item type in JSON list: {type(item)}")
                        
                        raw_device_list_from_file_or_tool = processed_loaded_data
                        print(f"Successfully processed {len(raw_device_list_from_file_or_tool)} devices from JSON.")
                        if not raw_device_list_from_file_or_tool and loaded_data: # If processing failed for all
                             print(f"Warning: All items in {devices_json_file} were problematic. Will attempt to fetch.")
                             if os.path.exists(devices_json_file): os.remove(devices_json_file) # Remove problematic file
                             raw_device_list_from_file_or_tool = [] # Ensure it's empty to trigger fetch

                    else:
                        print(f"Warning: {devices_json_file} does not contain a list. Will attempt to fetch.")
                        if os.path.exists(devices_json_file): os.remove(devices_json_file) # Remove invalid file
                
                except json.JSONDecodeError:
                    print(f"Warning: {devices_json_file} is not valid JSON. Will attempt to fetch.")
                    if os.path.exists(devices_json_file): os.remove(devices_json_file) # Remove invalid file
                except Exception as e:
                    print(f"Error reading {devices_json_file}: {e}. Will attempt to fetch.")
                    if os.path.exists(devices_json_file): os.remove(devices_json_file)
            
            if not raw_device_list_from_file_or_tool: # If JSON didn't exist or was invalid/empty or processing failed
                print(f"\n--- Step 1a: {devices_json_file} not found or empty/invalid. Fetching all linked devices via MCP tool (server-side caching active)... ---")
                try:
                    # Ensure tools_from_mcp is loaded before trying to use list_devices_tool
                    if 'tools_from_mcp' not in locals() or not tools_from_mcp:
                         print("Loading MCP tools for device fetch...")
                         tools_from_mcp = await load_mcp_tools(session)
                         if not tools_from_mcp:
                             print("No tools loaded from MCP server. Cannot fetch devices.")
                             return
                         print(f"Loaded {len(tools_from_mcp)} tools from Solinteg MCP server.")

                    list_devices_tool_name = "list_linked_devices"
                    list_devices_tool = next((t for t in tools_from_mcp if t.name == list_devices_tool_name), None)

                    if list_devices_tool:
                        print(f"Directly invoking tool: '{list_devices_tool.name}'...")
                        tool_output = await list_devices_tool.arun({}) 
                        if isinstance(tool_output, list):
                            # Ensure tool_output contains dicts, not strings of dicts
                            processed_tool_output = []
                            for item in tool_output:
                                if isinstance(item, dict):
                                    processed_tool_output.append(item)
                                elif isinstance(item, str): # Should not happen if tool behaves
                                    try:
                                        processed_tool_output.append(json.loads(item))
                                    except json.JSONDecodeError:
                                         print(f"Warning: Tool output item string not JSON: {item[:100]}")
                                else:
                                    print(f"Warning: Tool output item not dict or str: {type(item)}")
                            
                            raw_device_list_from_file_or_tool = processed_tool_output
                            print(f"Successfully fetched {len(raw_device_list_from_file_or_tool)} devices from tool.")
                        else:
                            print(f"Tool '{list_devices_tool.name}' did not return a list. Output: {type(tool_output)}")
                    else:
                        print(f"ERROR: Tool '{list_devices_tool_name}' not found. Cannot fetch devices.")
                        return 
                except Exception as e:
                    print(f"Error during tool loading or device fetch: {e}")
                    import traceback
                    traceback.print_exc()
                    return 

            # --- Step 2: Process device list and Select Random Devices ---
            if raw_device_list_from_file_or_tool:
                all_smart_device_sns = []
                all_normal_device_sns = []
                for device_info in raw_device_list_from_file_or_tool:
                    if isinstance(device_info, dict):
                        sn = device_info.get('deviceSn')
                        if sn:
                            if 'M' in sn:
                                all_smart_device_sns.append(sn)
                            else:
                                all_normal_device_sns.append(sn)
                
                print(f"\n--- Step 2a: Found {len(all_normal_device_sns)} normal devices and {len(all_smart_device_sns)} smart devices. ---")

                selected_normal_devices = []
                if all_normal_device_sns:
                    num_to_select_normal = min(8, len(all_normal_device_sns))
                    selected_normal_devices = random.sample(all_normal_device_sns, num_to_select_normal)
                    print(f"--- Step 2b: Randomly selected {len(selected_normal_devices)} normal devices: {selected_normal_devices} ---")
                else:
                    print("No normal device SNs found to select from.")

                selected_smart_devices = []
                if all_smart_device_sns:
                    num_to_select_smart = min(8, len(all_smart_device_sns))
                    selected_smart_devices = random.sample(all_smart_device_sns, num_to_select_smart)
                    print(f"--- Step 2c: Randomly selected {len(selected_smart_devices)} smart devices: {selected_smart_devices} ---")
                else:
                    print("No smart device SNs found to select from.")
                
                selected_device_sns = selected_normal_devices + selected_smart_devices
                if selected_device_sns:
                    print(f"--- Step 2d: Total {len(selected_device_sns)} devices selected for processing. ---")
                else:
                    print("No devices selected overall.")
            else:
                print(f"\n--- Step 2: No device data available from JSON or tool. Cannot select devices. ---")

            # --- Step 3: Direct tool invocation for selected devices (Python loop) ---
            if selected_device_sns:
                print(f"\n--- Step 3: Directly invoking tools for {len(selected_device_sns)} selected devices (No LLM calls in this loop) ---")
                
                # Ensure tools are loaded if we came from cache path
                if not tools_from_mcp:
                    print("Loading MCP tools for direct invocation...")
                    tools_from_mcp = await load_mcp_tools(session)
                    if not tools_from_mcp:
                        print("Failed to load MCP tools. Cannot proceed."); return
                    print(f"Successfully loaded {len(tools_from_mcp)} tools.")

                # Find the specific tools we need
                realtime_data_tool = next((t for t in tools_from_mcp if t.name == "get_device_realtime_data"), None)
                config_data_tool = next((t for t in tools_from_mcp if t.name == "get_device_config_data"), None)
                # history_data_tool = next((t for t in tools_from_mcp if t.name == "get_device_history_data"), None) 
                # history_config_tool = next((t for t in tools_from_mcp if t.name == "get_device_history_config_data"), None)

                smart_realtime_data_tool = next((t for t in tools_from_mcp if t.name == "get_smart_device_realtime_data"), None)
                smart_config_data_tool = next((t for t in tools_from_mcp if t.name == "get_smart_device_config_data"), None)

                if not realtime_data_tool:
                    print("ERROR: 'get_device_realtime_data' tool (for normal devices) not found!")
                if not config_data_tool:
                    print("ERROR: 'get_device_config_data' tool (for normal devices) not found!")
                if not smart_realtime_data_tool:
                    print("ERROR: 'get_smart_device_realtime_data' tool (for smart devices) not found!")
                if not smart_config_data_tool:
                    print("ERROR: 'get_smart_device_config_data' tool (for smart devices) not found!")

                for i, sn in enumerate(selected_device_sns):
                    print(f"\n--- Processing device {i+1}/{len(selected_device_sns)}: {sn} ---")
                    
                    is_smart_device = 'M' in sn

                    if is_smart_device:
                        # Use Smart Device Tools
                        if smart_realtime_data_tool:
                            print(f"Fetching real-time data for SMART device {sn}...")
                            try:
                                rt_data = await smart_realtime_data_tool.arun({"deviceSn": sn})
                                print(f"Real-time data for SMART {sn}: {json.dumps(rt_data, indent=2) if rt_data else 'No data'}")
                            except Exception as e:
                                print(f"Error fetching real-time data for SMART {sn}: {e}")
                        
                        if smart_config_data_tool:
                            print(f"Fetching configuration data for SMART device {sn}...")
                            try:
                                cfg_data = await smart_config_data_tool.arun({"deviceSn": sn})
                                print(f"Configuration data for SMART {sn}: {json.dumps(cfg_data, indent=2) if cfg_data else 'No data'}")
                            except Exception as e:
                                print(f"Error fetching configuration data for SMART {sn}: {e}")
                    else:
                        # Use Normal Device Tools
                        if realtime_data_tool:
                            print(f"Fetching real-time data for NORMAL device {sn}...")
                            try:
                                # Tool arguments are typically passed as a dictionary
                                # The MCP adapter handles the Context argument internally.
                                rt_data = await realtime_data_tool.arun({"deviceSn": sn})
                                print(f"Real-time data for NORMAL {sn}: {json.dumps(rt_data, indent=2) if rt_data else 'No data'}")
                            except Exception as e:
                                print(f"Error fetching real-time data for NORMAL {sn}: {e}")
                                # import traceback; traceback.print_exc() # For detailed debugging
                        
                        if config_data_tool:
                            print(f"Fetching configuration data for NORMAL device {sn}...")
                            try:
                                cfg_data = await config_data_tool.arun({"deviceSn": sn})
                                print(f"Configuration data for NORMAL {sn}: {json.dumps(cfg_data, indent=2) if cfg_data else 'No data'}")
                            except Exception as e:
                                print(f"Error fetching configuration data for NORMAL {sn}: {e}")
                                # import traceback; traceback.print_exc() # For detailed debugging
                    
                    # Add calls for history_data_tool and history_config_tool if needed, with proper args
                    # Example for history (requires start/end time logic):
                    # if history_data_tool:
                    #     end_time_dt = datetime.utcnow()
                    #     start_time_dt = end_time_dt - timedelta(hours=1)
                    #     time_format = "%Y-%m-%d %H:%M:%S"
                    #     start_str = start_time_dt.strftime(time_format)
                    #     end_str = end_time_dt.strftime(time_format)
                    #     print(f"Fetching history data for {sn} from {start_str} to {end_str}...")
                    #     try:
                    #         hist_data = await history_data_tool.arun({"deviceSn": sn, "startTime": start_str, "endTime": end_str})
                    #         print(f"History data for {sn}: {json.dumps(hist_data, indent=2) if hist_data else 'No data'}")
                    #     except Exception as e:
                    #         print(f"Error fetching history data for {sn}: {e}")

            else:
                print("\n--- No devices selected. Skipping direct tool invocation loop. ---")

            # --- Optional: LLM Agent for more complex, non-repetitive tasks ---
            # You can still have an LLM agent for other types of prompts if needed.
            # This section is now separate from the repetitive device data fetching.
            # Example:
            # print("\n--- Optional LLM Agent Task Example ---")
            # try:
            #     if not tools_from_mcp: # Ensure tools are loaded
            #         print("Loading MCP tools for the agent...")
            #         tools_from_mcp = await load_mcp_tools(session)
            #         if not tools_from_mcp: print("Failed to load MCP tools for agent."); return
            #     agent_executor = create_react_agent(llm, tools_from_mcp)
            #     print("Langchain ReAct agent created for optional tasks.")
            #     complex_prompt = "Compare the number of linked devices with the number of devices available by topic 'your_topic_here' if that tool exists."
            #     from langchain_core.messages import HumanMessage
            #     agent_response = await agent_executor.ainvoke({"messages": [HumanMessage(content=complex_prompt)]})
            #     output = agent_response.get('output', agent_response.get('result', str(agent_response)))
            #     print(f"Response to complex prompt: {output}")
            # except Exception as e:
            #     print(f"Error during optional LLM agent task: {e}")

async def cleanup_mcp_server():
    # This is a conceptual cleanup. The stdio_client context manager should handle
    # process termination when it exits.
    # If you were managing mcp_process globally like in the previous manual example:
    # from langchain_mcp_client_manual import stop_mcp_process # (if you had that)
    # stop_mcp_process()
    print("Cleanup: MCP server process should be stopped by stdio_client context manager.")


if __name__ == "__main__":
    main_task = None
    try:
        main_task = asyncio.run(main()) # Store the task if asyncio.run returns one
    except KeyboardInterrupt:
        print("\nUser interrupted. Exiting.")
    except Exception as e:
        print(f"Unhandled exception in main: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("Script finished.")
        # Ensure cleanup_mcp_server is an async function called with asyncio.run or await
        # if main_task and hasattr(main_task, 'cancel'):
        # try:
        # main_task.cancel()
        # except RuntimeError: # Handle cases where event loop might be closed
        # pass
        asyncio.run(cleanup_mcp_server()) # Call the async cleanup function