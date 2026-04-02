# Gemini Live Truck Driver Assistant

A real-time, voice-first trucking copilot built with FastAPI, Gemini Live, and vanilla JavaScript. It supports complex dispatch and driver workflows including route/ETA updates, hours-of-service (HOS) compliance, pay/settlement visibility, hometime requests, and direct messaging to Driver Leaders or CSRs.

## 🚀 Quick Start

### 1. Configure environment

Create a `.env` file in the project root:

```env
GEMINI_API_KEY=your_api_key_here
# Optional settings
MODEL=gemini-3.1-flash-live-preview
PORT=8000
DRIVER_LEADER_PHONE=123-456-7890
```

### 2. Install dependencies and run

```bash
# Setup virtual environment
python3 -m venv .venv
# On Windows use: .venv\Scripts\activate
source .venv/bin/activate

# Install requirements
pip install -r requirements.txt

# Start the server
python3 main.py
```

### 3. Open the app

Visit [http://localhost:8000](http://localhost:8000).

---

## 🛠️ Technical Highlights

### 🚄 Optimized Session Handling
The system uses a robust WebSocket orchestration layer designed for the high-latency, intermittent connectivity often found on the road:
- **Clean Disconnects**: Gracefully handles browser closures and session pauses without server-side crashes.
- **Session Resumption**: Automatically retrieves and manages Gemini resumption handles, allowing the conversation to continue seamlessly after a brief drop.
- **Noise-Reduced Logging**: Optimized logging levels for production-like monitoring of session health.

### 📝 Immutable Audit Logging
The system maintains a high-fidelity audit trail of all mutating operations (`update_eta`, `update_load_status`, `submit_hometime_request`, `send_message_to_driver_leader`).
- **Snapshot Diffing**: Every change logs a "before" and "after" state for the modified fields.
- **Traceability**: Each log entry includes a unique `log_id`, ISO timestamp, and rich metadata (e.g., `load_id`, `reason`).

### 🧠 Consolidated "Snapshot" Intelligence
Instead of making multiple API calls, the assistant uses a powerful `get_driver_snapshot` tool that provides:
- **Unified Context**: Driver profile, route, HOS clocks, pay breakdown, and dispatch messages in one go.
- **HOS Compliance**: Calculates `violation_risk` and identifies if a break is due soon.
- **Feasibility Checking**: Predicts if delivery windows are at risk based on current drive time and location.
- **Contact Escalation**: Provides direct phone numbers for Driver Leaders, CSRs, and specialized departments (Safety, Payroll, Roadside).

---

## 🏗️ Project Structure

```text
/
├── main.py              # FastAPI app, Tool declarations, WebSocket orchestration
├── gemini_live.py       # Gemini Live session manager (Multimodal + Tool orchestration)
├── driver_tools.py      # Simulation engine, Trucking logic, Audit log, State persistence
├── tool_validation.py   # Strict schema validation for model-invoked tool arguments
├── requirements.txt
└── frontend/
    ├── index.html       # Ultra-clean driver dashboard
    ├── style.css        # Modern design: glassmorphism, responsive grid, animations
    ├── main.js          # Reactive UI logic & WebSocket handling
    ├── gemini-client.js # Specialized WebSocket wrapper for Gemini Live
    ├── media-handler.js # Web Audio API & MediaStream (Cam/Mic/Screen) manager
    └── pcm-processor.js # Real-time audio processing worklet
```

---

## 🛠️ Available Tools

The assistant is grounded in a mock trucking ERP/TMS system via the following toolset:

| Tool Name | Description | Key Parameters |
| :--- | :--- | :--- |
| `get_driver_snapshot` | Unified snapshot of ALL facts: route, hours, pay, messages, and escalation contacts. | `appointment_time_iso`, `dispatch_unread_only` |
| `update_eta` | Updates the load's ETA and records the reason in the audit log. | `new_eta_iso`, `reason`, `stop_name` |
| `update_load_status` | Submits check-calls (e.g., `in_transit`, `arrived`, `delivered`). | `status`, `location`, `note` |
| `submit_hometime_request`| Files a formal request for time off at a specific location. | `start_date`, `end_date`, `location` |
| `send_message_to_driver_leader` | Queues a dictated note or operational update to the assigned Driver Leader. | `notes_dictation`, `subject` |
| `send_message_to_csr` | Sends a customer-facing message regarding load/appointment details. | `notes_dictation`, `subject` |

### 📊 Data Points Available to Gemini

- **HOS Compliance**: 11hr (Drive), 14hr (On-Duty), and 70hr (Cycle) clocks; minutes until next required break.
- **Financials**: Dispatched vs. Paid miles variance, rate per mile, accessorials, and next settlement date.
- **Fuel & Parking**: Suggested stops based on route, including distance and parking availability.
- **Communication**: Threaded messages from Dispatch, Safety, and Payroll with priority levels.
- **Escalation**: Direct lines for Shop, Payroll, Licensing, Safety, and Roadside departments.

