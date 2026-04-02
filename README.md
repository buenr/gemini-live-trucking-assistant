# Gemini Live Truck Driver Assistant

A real-time, voice-first trucking copilot built with FastAPI, Gemini Live, and vanilla JavaScript. It supports complex dispatch and driver workflows including route/ETA updates, hours-of-service (HOS) compliance, pay/settlement visibility, hometime requests, and check-call status updates.

## 🚀 Quick Start

### 1. Configure environment

Create a `.env` file in the project root:

```env
GEMINI_API_KEY=your_api_key_here
# Optional settings
MODEL=gemini-3.1-flash-live-preview
PORT=8000
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

## 🛠️ Untold Technical Details

### 📝 Immutable Audit Logging (CHANGE_LOG)
The system maintains a high-fidelity audit trail of all mutating operations (`update_eta`, `update_load_status`, `submit_hometime_request`).
- **Snapshot Diffing**: Every change logs a "before" and "after" state for the modified fields.
- **Traceability**: Each log entry includes a unique `log_id`, ISO timestamp, tool call origin, and rich metadata (e.g., `load_id`, `reason`).

### 📹 Multimodal Interactions
While primarily "voice-first," the assistant is fully multimodal:
- **Audio**: Low-latency 16kHz PCM streaming (Zephyr voice).
- **Video/Camera**: Real-time frame analysis (JPEG blobs) allowing the assistant to "see" documents, road signs, or in-cab conditions.
- **Screen Share**: Native browser screen capture for collaborative troubleshooting or route review.

### 🧠 Domain-Specific Intelligence
The tools aren't just data accessors; they implement trucking business logic:
- **HOS Compliance**: `get_hours_compliance_summary` calculates `violation_risk` and identifies if a break is due within 30 minutes.
- **Feasibility Checking**: `can_make_appointment` uses current ETA and remaining drive hours to predict if a delivery window is at risk.
- **Smart Settlements**: `get_settlement_breakdown` calculates miles variance between dispatched and paid miles to flag potential pay discrepancies.

---

## 💻 Frontend Sophistication

The vanilla JS frontend (`frontend/`) is designed for modern, high-intensity cab use:
- **Reactive Data Dashboard**: A live grid that highlights specific fields (using CSS transitions) whenever they are updated by a tool call.
- **Voice-only interaction**: The driver speaks to the copilot; transcripts still appear in the chat panel for readability.
- **Bidirectional UI Sync**: The UI reflects background simulation changes automatically when the driver requests a snapshot.
- **Audio Leveling**: Visualizers and volume handling for seamless voice interaction.

---

## 🏗️ Project Structure

```text
/
├── main.py              # FastAPI app, Tool declarations, WebSocket orchestration
├── gemini_live.py       # Gemini Live session manager (Multimodal + Tool orchestration)
├── driver_tools.py      # Simulation engine, Trucking logic, Audit log, State persistence
├── requirements.txt
└── frontend/
    ├── index.html       # Ultra-clean driver dashboard
    ├── style.css        # Modern design: glassmorphism, responsive grid, animations
    ├── main.js          # Reactive UI logic & WebSocket handling
    ├── gemini-client.js # Specialized WebSocket wrapper for Gemini Live
    ├── media-handler.js # Web Audio API & MediaStream (Cam/Mic/Screen) manager
    └── pcm-processor.js # Real-time audio processing worklet
```

## ⚙️ Gemini Configuration

- **System Instruction**: Explicitly tuned for brevity and high-reliability tool-grounded responses in noisy in-cab environments.
- **Modality**: Configured for `AUDIO` response modality with the `Zephyr` prebuilt voice.
- **Turn Detection**: Uses `TURN_INCLUDES_ONLY_ACTIVITY` for natural, interruptible conversations.

---

## 🛠️ Available Tools & Data Points

The assistant is grounded in a mock trucking ERP/TMS system via the following toolset:

### 🔧 Tool Calls (Functions)

| Tool Name | Description | Key Parameters |
| :--- | :--- | :--- |
| `get_status` | Comprehensive snapshot of driver, route, and ETA feasibility. | `appointment_time_iso` (optional) |
| `get_stop_plan` | HOS compliance summary and suggested fuel stops with parking. | `limit` (default 3) |
| `get_pay_and_settlement` | Detailed breakdown of weekly earnings, miles variance, and deductions. | `week` (default "current") |
| `update_eta` | Updates the load's ETA and records the reason in the audit log. | `new_eta_iso`, `reason`, `stop_name` |
| `update_load_status` | Submits check-calls (e.g., `arrived`, `loaded`, `delivered`). | `status`, `location`, `note` |
| `submit_hometime_request`| Files a formal request for time off at a specific location. | `start_date`, `end_date`, `location` |
| `get_hometime_status` | Retrieves status for the latest or a specific hometime request. | `request_id` (optional) |
| `get_dispatch_messages` | Fetches fleet messages (Safety, Dispatch, Payroll) with priority. | `unread_only`, `limit` |

### 📊 Data Points Available

- **Driver Profile**: Name, ID, Truck Number, Fleet, and Daily Hours remaining.
- **Route & Load**: Origin/Destination, Shipper/Receiver, Current Location, Next Stop, and Appointment Windows.
- **Trip Execution**: Live ETA, remaining miles, estimated drive time, and "at risk" feasibility flags.
- **HOS Compliance**: 11hr (Drive), 14hr (On-Duty), and 70hr (Cycle) clocks; minutes until next required 30-min break.
- **Financials**: Dispatched vs. Paid miles variance, rate per mile, and accessorials (Detention, Layover, etc.).
- **Fuel & Parking**: Suggested stops based on route, including distance and parking availability (Low/Med/High).
- **Communication**: Threaded messages from Dispatch, Safety, and Payroll with priority levels.

