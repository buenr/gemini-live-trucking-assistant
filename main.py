"""FastAPI app for the in-cab trucking voice assistant.

Serves the frontend, exposes driver snapshot JSON at ``/api/driver-data``, and runs a
``/ws`` WebSocket that streams audio and optional camera frames to Gemini Live while
wiring trucking tool declarations to ``driver_tools``.
"""

import asyncio
import base64
import json
import logging
import os
import traceback

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from google.genai import types
from gemini_live import GeminiLive
from driver_tools import (
    get_driver_snapshot,
    get_outbound_team_messages,
    send_message_to_csr,
    send_message_to_driver_leader,
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


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return int(raw)


GEMINI_SESSION_MAX_RETRIES = _env_int("GEMINI_SESSION_MAX_RETRIES", 4)

CONTEXT_COMPRESSION_TRIGGER_TOKENS = _env_int("CONTEXT_COMPRESSION_TRIGGER_TOKENS", 50_000)
CONTEXT_SLIDING_TARGET_TOKENS = _env_int("CONTEXT_SLIDING_TARGET_TOKENS", 42_000)
LIVE_MAX_OUTPUT_TOKENS = _env_int("LIVE_MAX_OUTPUT_TOKENS", 768)

TRUCKING_TOOLS = [
    types.Tool(
        function_declarations=[
            {
                "name": "get_driver_snapshot",
                "description": (
                    "Get full operational context in one call: driver profile, route/load, trip execution and appointment feasibility, "
                    "HOS hours and suggested fuel stops, pay and settlement, hometime request status, dispatch messages, and "
                    "contacts (Driver Leader and CSR with name, code, and phone; plus Shop, Payroll, Licensing, Safety, Roadside department numbers for escalation). "
                    "Call this whenever the driver needs facts about route, hours, pay, messages, hometime, or who to call when you cannot answer—prefer a single call over multiple tools."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "appointment_time_iso": {
                            "type": "STRING",
                            "description": "Optional ISO timestamp for appointment feasibility vs ETA and drive hours.",
                        },
                        "fuel_stops_limit": {
                            "type": "INTEGER",
                            "description": "Max suggested fuel stops to include (default 3).",
                        },
                        "week": {
                            "type": "STRING",
                            "description": "Pay week, e.g. current or YYYY-WW (default current).",
                        },
                        "hometime_request_id": {
                            "type": "STRING",
                            "description": "Optional hometime request id; omit for latest request.",
                        },
                        "dispatch_unread_only": {
                            "type": "BOOLEAN",
                            "description": "If true, only unread dispatch messages are listed (default false).",
                        },
                        "dispatch_limit": {
                            "type": "INTEGER",
                            "description": "Max dispatch messages to return (default 10).",
                        },
                    },
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
                "name": "send_message_to_driver_leader",
                "description": (
                    "Send a note or dictated message to the driver's assigned Driver Leader. "
                    "Use when the driver asks to message their DL, escalate a non-safety issue, or leave an operational note. "
                    "The server attaches the assigned DL name and code automatically—do not ask the driver for them. "
                    "Populates notes/dictation, timestamp, driver id, load id, contact_name, contact_code, and context for the queue (demo: in-memory only)."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "required": ["notes_dictation"],
                    "properties": {
                        "notes_dictation": {
                            "type": "STRING",
                            "description": "Full text of the note or voice dictation to deliver.",
                        },
                        "driver_id": {
                            "type": "STRING",
                            "description": "Driver id; omit to use the active session driver.",
                        },
                        "load_id": {
                            "type": "STRING",
                            "description": "Load or trip reference; omit to use current load from snapshot.",
                        },
                        "subject": {
                            "type": "STRING",
                            "description": "Short subject line if the driver gave one.",
                        },
                    },
                },
            },
            {
                "name": "send_message_to_csr",
                "description": (
                    "Send a note or dictated message to the assigned CSR (customer service) about the load, appointment, or receiver. "
                    "Use for appointment changes, delivery issues, or customer-facing coordination—not the same as Driver Leader ops. "
                    "The server attaches the assigned CSR name and code automatically—do not ask the driver for them. "
                    "Populates notes/dictation, timestamp, driver id, load id, contact_name, contact_code, and context (demo: in-memory only)."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "required": ["notes_dictation"],
                    "properties": {
                        "notes_dictation": {
                            "type": "STRING",
                            "description": "Full text of the note or voice dictation for CSR.",
                        },
                        "driver_id": {
                            "type": "STRING",
                            "description": "Driver id; omit to use the active session driver.",
                        },
                        "load_id": {
                            "type": "STRING",
                            "description": "Load or trip reference; omit to use current load from snapshot.",
                        },
                        "subject": {
                            "type": "STRING",
                            "description": "Short subject line if the driver gave one.",
                        },
                    },
                },
            },
        ]
    )
]

TRUCKING_TOOL_MAPPING = {
    "get_driver_snapshot": get_driver_snapshot,
    "update_eta": update_eta,
    "update_load_status": update_load_status,
    "submit_hometime_request": submit_hometime_request,
    "send_message_to_driver_leader": send_message_to_driver_leader,
    "send_message_to_csr": send_message_to_csr,
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


@app.get("/api/driver-data")
async def driver_data():
    snap = get_driver_snapshot(fuel_stops_limit=1)
    sp = snap.get("stop_plan") or {}
    hours = sp.get("hours") or {}
    ht = snap.get("hometime") or {}
    pay = dict(snap.get("pay") or {})
    contacts = snap.get("contacts") or {}
    return {
        "success": True,
        "driver": snap.get("driver", {}),
        "route": snap.get("route", {}),
        "trip": snap.get("trip", {}),
        "appointment": snap.get("appointment", {}),
        "hours": hours,
        "pay": pay,
        "hometime": ht.get("request") if ht.get("success") else None,
        "dispatch": snap.get("dispatch") or {},
        "outbound_team_messages": get_outbound_team_messages(),
        "assigned_team_contacts": {
            "driver_leader": contacts.get("driver_leader", {}),
            "csr": contacts.get("csr", {}),
        },
        "operations_contacts": contacts,
    }


def _parse_session_start_payload(text: str) -> tuple[str | None, str] | None:
    """If text is a session_start control message, return (resume_handle, vad_preset)."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("type") != "session_start":
        return None
    handle = payload.get("resume_handle")
    if handle is not None and isinstance(handle, str) and handle.strip() == "":
        handle = None
    elif handle is not None and not isinstance(handle, str):
        handle = str(handle) if handle else None
    preset = payload.get("vad_preset") or "normal"
    if not isinstance(preset, str):
        preset = "normal"
    return (handle, preset.strip().lower())


async def _try_process_image_frame(text: str, video_input_queue: asyncio.Queue) -> bool:
    """If *text* is a JSON image/camera/screen frame, decode and enqueue it.

    Returns True when the frame was consumed (valid or rejected as oversized),
    False when `text` is not an image frame.
    """
    try:
        payload = json.loads(text)
        if isinstance(payload, dict) and payload.get("type") in (
            "image", "camera_frame", "screen_frame",
        ):
            raw = payload.get("data", "")
            if len(raw) > 2_000_000:
                logger.warning("Oversized image payload rejected")
                return True
            await video_input_queue.put(base64.b64decode(raw))
            return True
    except (json.JSONDecodeError, KeyError):
        pass
    return False


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for Gemini Live."""
    await websocket.accept()

    logger.info("WebSocket connection accepted")

    audio_input_queue = asyncio.Queue()
    video_input_queue = asyncio.Queue()

    resume_handle: str | None = None
    vad_preset = "normal"

    first = await websocket.receive()
    if first["type"] == "websocket.disconnect":
        logger.info("WebSocket disconnected during handshake")
        return

    if first.get("text"):
        parsed = _parse_session_start_payload(first["text"])
        if parsed is not None:
            resume_handle, vad_preset = parsed
            logger.info("Session start: vad_preset=%s resume=%s", vad_preset, bool(resume_handle))
        elif not await _try_process_image_frame(first["text"], video_input_queue):
            logger.debug("Ignoring non-control text WebSocket frame (voice-only mode)")
    elif first.get("bytes"):
        await audio_input_queue.put(first["bytes"])

    last_resume_handle = resume_handle

    async def audio_output_callback(data):
        await websocket.send_bytes(data)

    gemini_client = GeminiLive(
        api_key=GEMINI_API_KEY,
        model=MODEL,
        input_sample_rate=16000,
        tools=TRUCKING_TOOLS,
        tool_mapping=TRUCKING_TOOL_MAPPING,
        context_trigger_tokens=CONTEXT_COMPRESSION_TRIGGER_TOKENS,
        context_target_tokens=CONTEXT_SLIDING_TARGET_TOKENS,
        max_output_tokens=LIVE_MAX_OUTPUT_TOKENS,
    )

    async def receive_from_client():
        try:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    raise WebSocketDisconnect(
                        message.get("code", 1000), message.get("reason", "")
                    )

                if message.get("bytes"):
                    await audio_input_queue.put(message["bytes"])
                elif message.get("text"):
                    if not await _try_process_image_frame(message["text"], video_input_queue):
                        logger.debug("Ignoring text WebSocket frame (voice-only mode)")
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")
        except Exception as e:
            logger.error(f"Error receiving from client: {e}")

    receive_task = asyncio.create_task(receive_from_client())

    async def run_session():
        nonlocal last_resume_handle
        attempt = 0
        last_error: str | None = None
        while attempt < GEMINI_SESSION_MAX_RETRIES:
            attempt += 1
            last_error = None
            try:
                async for event in gemini_client.start_session(
                    audio_input_queue=audio_input_queue,
                    video_input_queue=video_input_queue,
                    audio_output_callback=audio_output_callback,
                    session_resume_handle=last_resume_handle,
                    vad_preset=vad_preset,
                ):
                    if event is None:
                        break
                    if isinstance(event, dict):
                        if event.get("type") == "session_resumption" and event.get("new_handle"):
                            last_resume_handle = event["new_handle"]
                        try:
                            await websocket.send_json(event)
                        except Exception as send_exc:
                            logger.warning("Could not forward event to client: %s", send_exc)
                    if isinstance(event, dict) and event.get("type") == "error":
                        last_error = event.get("error")
                        break
                if last_error:
                    logger.warning("Gemini session ended with error event: %s", last_error)
                break
            except Exception as e:

                last_error = f"{type(e).__name__}: {e}"
                logger.error(
                    "Gemini session attempt %s/%s failed: %s\n%s",
                    attempt,
                    GEMINI_SESSION_MAX_RETRIES,
                    last_error,
                    traceback.format_exc(),
                )
                if attempt >= GEMINI_SESSION_MAX_RETRIES:
                    try:
                        await websocket.send_json(
                            {"type": "error", "error": last_error, "fatal": True}
                        )
                    except Exception:
                        pass
                    break
                await asyncio.sleep(min(2**attempt, 12))
            except asyncio.CancelledError:
                logger.info("Gemini session task cancelled")
                break

    try:
        await run_session()
    except asyncio.CancelledError:
        logger.info("WebSocket session task cancelled")
    except Exception as e:
        logger.error(f"Error in Gemini session: {type(e).__name__}: {e}\n{traceback.format_exc()}")
    finally:
        receive_task.cancel()
        try:
            await websocket.close()
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="localhost", port=port)
