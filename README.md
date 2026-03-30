# Gemini Live Truck Driver Assistant

A real-time, voice-first trucking copilot built with FastAPI, Gemini Live, and vanilla JavaScript. It supports dispatch and driver workflows like route/ETA updates, hours-of-service checks, pay/settlement visibility, hometime requests, and check-call status updates.

## Quick Start

### 1. Configure environment

Create `.env` in the project root:

```env
GEMINI_API_KEY=your_api_key_here
# Optional
MODEL=gemini-3.1-flash-live-preview
PORT=8000
```

### 2. Install dependencies and run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

### 3. Open the app

Visit [http://localhost:8000](http://localhost:8000).

## Latest Trucking Assistant Functionality

- Voice copilot flow tuned for in-cab operations with short, practical responses.
- Live multimodal session support (audio input/output plus camera/screen frames).
- Tool-grounded trucking workflows:
  - `get_driver_snapshot`, `get_route_info`, `get_trip_execution_status`
  - `get_hours_compliance_summary`, `can_make_appointment`
  - `get_pay_info`, `get_settlement_breakdown`
  - `update_eta`, `update_load_status`
  - `submit_hometime_request`, `get_hometime_status`
  - `get_fuel_stops`, `get_change_log`
- Mutating operations (`update_eta`, `update_load_status`, `submit_hometime_request`) are audit-logged via `CHANGE_LOG`.
- Simulated route/hours/pay progression over time for realistic demo interactions.
- Quick-action prompts in UI for route, pay, hours, ETA, hometime, and trip status.
- Driver snapshot API endpoint: `GET /api/driver-data`.

## Project Structure

```text
/
├── main.py              # FastAPI app, Gemini tool declarations/mapping, WebSocket endpoint
├── gemini_live.py       # Gemini Live session manager (audio/video/text + tool call handling)
├── driver_tools.py      # Trucking domain state, simulation, tool implementations, audit log
├── requirements.txt
└── frontend/
    ├── index.html
    ├── style.css
    ├── main.js
    ├── gemini-client.js
    ├── media-handler.js
    └── pcm-processor.js
```
