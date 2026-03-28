import asyncio
import base64
import json
import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from google.genai import types
from gemini_live import GeminiLive
from driver_tools import (
    can_make_appointment,
    get_change_log,
    get_driver_snapshot,
    get_fuel_stops,
    get_hours_compliance_summary,
    get_hometime_status,
    get_pay_info,
    get_settlement_breakdown,
    get_trip_execution_status,
    get_route_info,
    submit_hometime_request,
    update_eta,
    update_load_status,
)

# Load environment variables
load_dotenv()

# Configure logging - DEBUG for our modules, INFO for everything else
logging.basicConfig(level=logging.INFO)
logging.getLogger("gemini_live").setLevel(logging.DEBUG)
logging.getLogger(__name__).setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)

# Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("MODEL", "gemini-3.1-flash-live-preview")

TRUCKING_TOOLS = [
    types.Tool(
        function_declarations=[
            {
                "name": "get_driver_snapshot",
                "description": "Get a high-level summary of current driver, load, and route status.",
                "parameters": {"type": "OBJECT", "properties": {}},
            },
            {
                "name": "get_route_info",
                "description": "Retrieve current route, ETA, miles remaining, next stop, and load status.",
                "parameters": {"type": "OBJECT", "properties": {}},
            },
            {
                "name": "get_hours_compliance_summary",
                "description": "Get core hours/compliance values: drive left, duty window left, cycle left, break due, and risk flags.",
                "parameters": {"type": "OBJECT", "properties": {}},
            },
            {
                "name": "can_make_appointment",
                "description": "Check if current ETA and hours allow making an appointment time.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "appointment_time_iso": {
                            "type": "STRING",
                            "description": "Optional ISO timestamp for appointment target.",
                        }
                    },
                },
            },
            {
                "name": "get_settlement_breakdown",
                "description": "Get settlement details including miles variance, accessorials, deductions, and settlement status.",
                "parameters": {"type": "OBJECT", "properties": {}},
            },
            {
                "name": "get_trip_execution_status",
                "description": "Get route execution snapshot: ETA confidence, appointment risk, delay history, and check-call status.",
                "parameters": {"type": "OBJECT", "properties": {}},
            },
            {
                "name": "get_change_log",
                "description": "Retrieve recent audit logs for mutating driver data updates.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {"limit": {"type": "INTEGER", "description": "How many logs to return"}},
                },
            },
            {
                "name": "update_eta",
                "description": "Update the driver's ETA for dispatch/check-call workflows.",
                "parameters": {
                    "type": "OBJECT",
                    "required": ["new_eta_iso"],
                    "properties": {
                        "new_eta_iso": {
                            "type": "STRING",
                            "description": "New ETA in ISO format, e.g. 2026-03-28T20:15:00",
                        },
                        "reason": {"type": "STRING"},
                        "stop_name": {"type": "STRING"},
                    },
                },
            },
            {
                "name": "update_load_status",
                "description": "Submit a check-call/load status update like in_transit, arrived, delivered, delayed.",
                "parameters": {
                    "type": "OBJECT",
                    "required": ["status"],
                    "properties": {
                        "status": {"type": "STRING"},
                        "location": {"type": "STRING"},
                        "note": {"type": "STRING"},
                    },
                },
            },
            {
                "name": "get_pay_info",
                "description": "Retrieve pay and settlement summary for the current or specified week.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "week": {"type": "STRING", "description": "Use values like current or YYYY-WW"}
                    },
                },
            },
            {
                "name": "submit_hometime_request",
                "description": "Submit a hometime request with date range and requested location.",
                "parameters": {
                    "type": "OBJECT",
                    "required": ["start_date", "end_date", "location"],
                    "properties": {
                        "start_date": {"type": "STRING", "description": "ISO date, e.g. 2026-04-10"},
                        "end_date": {"type": "STRING", "description": "ISO date, e.g. 2026-04-14"},
                        "location": {"type": "STRING"},
                        "notes": {"type": "STRING"},
                    },
                },
            },
            {
                "name": "get_hometime_status",
                "description": "Get status for a hometime request by id, or latest request if no id is provided.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {"request_id": {"type": "STRING"}},
                },
            },
            {
                "name": "get_fuel_stops",
                "description": "Get nearby or upcoming fuel stop suggestions on current route.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {"limit": {"type": "INTEGER", "description": "How many stops to return"}},
                },
            },
        ]
    )
]

TRUCKING_TOOL_MAPPING = {
    "get_driver_snapshot": get_driver_snapshot,
    "get_route_info": get_route_info,
    "update_eta": update_eta,
    "update_load_status": update_load_status,
    "get_pay_info": get_pay_info,
    "submit_hometime_request": submit_hometime_request,
    "get_hometime_status": get_hometime_status,
    "get_fuel_stops": get_fuel_stops,
    "get_change_log": get_change_log,
    "get_hours_compliance_summary": get_hours_compliance_summary,
    "can_make_appointment": can_make_appointment,
    "get_settlement_breakdown": get_settlement_breakdown,
    "get_trip_execution_status": get_trip_execution_status,
}

# Initialize FastAPI
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files
app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/")
async def root():
    return FileResponse("frontend/index.html")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for Gemini Live."""
    await websocket.accept()

    logger.info("WebSocket connection accepted")

    audio_input_queue = asyncio.Queue()
    video_input_queue = asyncio.Queue()
    text_input_queue = asyncio.Queue()

    async def audio_output_callback(data):
        await websocket.send_bytes(data)

    async def audio_interrupt_callback():
        # The event queue handles the JSON message, but we might want to do something else here
        pass

    gemini_client = GeminiLive(
        api_key=GEMINI_API_KEY,
        model=MODEL,
        input_sample_rate=16000,
        tools=TRUCKING_TOOLS,
        tool_mapping=TRUCKING_TOOL_MAPPING,
    )

    async def receive_from_client():
        try:
            while True:
                message = await websocket.receive()

                if message.get("bytes"):
                    await audio_input_queue.put(message["bytes"])
                elif message.get("text"):
                    text = message["text"]
                    try:
                        payload = json.loads(text)
                        if isinstance(payload, dict) and payload.get("type") in (
                            "image", "camera_frame", "screen_frame"
                        ):
                            raw = payload.get("data", "")
                            if len(raw) > 2_000_000:
                                logger.warning("Oversized image payload rejected")
                                continue
                            image_data = base64.b64decode(raw)
                            await video_input_queue.put(image_data)
                            continue
                    except (json.JSONDecodeError, KeyError):
                        pass

                    await text_input_queue.put(text)
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")
        except Exception as e:
            logger.error(f"Error receiving from client: {e}")

    receive_task = asyncio.create_task(receive_from_client())

    async def run_session():
        async for event in gemini_client.start_session(
            audio_input_queue=audio_input_queue,
            video_input_queue=video_input_queue,
            text_input_queue=text_input_queue,
            audio_output_callback=audio_output_callback,
            audio_interrupt_callback=audio_interrupt_callback,
        ):
            if event:
                # Forward events (transcriptions, etc) to client
                await websocket.send_json(event)

    try:
        await run_session()
    except Exception as e:
        import traceback
        logger.error(f"Error in Gemini session: {type(e).__name__}: {e}\n{traceback.format_exc()}")
    finally:
        receive_task.cancel()
        # Ensure websocket is closed if not already
        try:
            await websocket.close()
        except:
            pass


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="localhost", port=port)
