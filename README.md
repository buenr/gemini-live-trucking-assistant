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
- **Log Access**: The `get_change_log` tool allows the assistant (and the user) to review precisely what changed and why.

### 📹 Multimodal Interactions
While primarily "voice-first," the assistant is fully multimodal:
- **Audio**: Low-latency 16kHz PCM streaming (Puck voice).
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
- **Intelligent Quick Actions**: Context-aware buttons that send targeted prompts to Gemini, optimized for common driver queries (Route, Pay, Hours).
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
- **Modality**: Configured for `AUDIO` response modality with the `Puck` prebuilt voice.
- **Turn Detection**: Uses `TURN_INCLUDES_ONLY_ACTIVITY` for natural, interruptible conversations.

