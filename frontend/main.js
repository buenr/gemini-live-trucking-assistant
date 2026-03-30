// --- Main Application Logic ---

const statusDiv = document.getElementById("status");
const authSection = document.getElementById("auth-section");
const appSection = document.getElementById("app-section");
const sessionEndSection = document.getElementById("session-end-section");
const restartBtn = document.getElementById("restartBtn");
const micBtn = document.getElementById("micBtn");
const cameraBtn = document.getElementById("cameraBtn");
const screenBtn = document.getElementById("screenBtn");
const disconnectBtn = document.getElementById("disconnectBtn");
const textInput = document.getElementById("textInput");
const sendBtn = document.getElementById("sendBtn");
const videoPreview = document.getElementById("video-preview");
const videoPlaceholder = document.getElementById("video-placeholder");
const connectBtn = document.getElementById("connectBtn");
const chatLog = document.getElementById("chat-log");
const quickActionButtons = document.querySelectorAll(".qa-btn");
const sessionIndicator = document.getElementById("session-indicator");
const sessionLabel = document.getElementById("session-label");
const toastContainer = document.getElementById("toast-container");
const driverDataGrid = document.getElementById("driver-data-grid");
const driverLastUpdate = document.getElementById("driver-last-update");

let currentGeminiMessageDiv = null;
let currentUserMessageDiv = null;
let micActive = false;
let cameraActive = false;
let screenActive = false;
let lastUpdatedField = "";

const DRIVER_DATA_FIELDS = [
  ["driver_id", "Driver ID"],
  ["name", "Name"],
  ["truck_number", "Truck #"],
  ["fleet", "Fleet"],
  ["hours_left_today", "Drive Hours Left"],
  ["load_id", "Load ID"],
  ["status", "Status"],
  ["current_location", "Current Location"],
  ["next_stop", "Next Stop"],
  ["eta_iso", "ETA"],
  ["last_check_call", "Last Check Call"],
  ["hometime_request_id", "Hometime Request ID"],
  ["hometime_status", "Hometime Status"],
  ["hometime_range", "Hometime Range"],
  ["hometime_location", "Hometime Location"],
];

const driverDataState = Object.fromEntries(
  DRIVER_DATA_FIELDS.map(([key]) => [key, "—"])
);

const WRITE_TOOLS = new Set([
  "update_eta",
  "update_load_status",
  "submit_hometime_request",
]);

const TOOL_LABELS = {
  update_eta: "ETA Updated",
  update_load_status: "Load Status Updated",
  submit_hometime_request: "Hometime Request Submitted",
  get_route_info: "Route Retrieved",
  get_pay_info: "Pay Info Retrieved",
  get_hours_compliance_summary: "Hours Retrieved",
  get_settlement_breakdown: "Settlement Retrieved",
  get_trip_execution_status: "Trip Status Retrieved",
  get_driver_snapshot: "Snapshot Retrieved",
  get_fuel_stops: "Fuel Stops Retrieved",
  get_hometime_status: "Hometime Status Retrieved",
  can_make_appointment: "Appointment Check Done",
  get_change_log: "Change Log Retrieved",
};

// --- Toast System ---
function showToast(message, type = "info") {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  toastContainer.appendChild(toast);
  setTimeout(() => {
    if (toast.parentNode) toast.parentNode.removeChild(toast);
  }, 3500);
}

// --- Status Helpers ---
function setStatus(text, cls) {
  statusDiv.textContent = text;
  statusDiv.className = `status ${cls}`;
}

function setSessionLive(live) {
  if (live) {
    sessionIndicator.className = "session-indicator live";
    sessionLabel.textContent = "Live";
  } else {
    sessionIndicator.className = "session-indicator off";
    sessionLabel.textContent = "Offline";
  }
}

function renderDriverData() {
  driverDataGrid.innerHTML = "";
  DRIVER_DATA_FIELDS.forEach(([key, label]) => {
    const item = document.createElement("div");
    item.className = `driver-data-item${lastUpdatedField === key ? " updated" : ""}`;
    const labelSpan = document.createElement("span");
    labelSpan.className = "label";
    labelSpan.textContent = label;
    const valueSpan = document.createElement("span");
    valueSpan.className = "value";
    valueSpan.textContent = formatDriverValue(driverDataState[key]);
    item.appendChild(labelSpan);
    item.appendChild(valueSpan);
    driverDataGrid.appendChild(item);
  });
}

function formatDriverValue(value) {
  if (value === undefined || value === null || value === "") return "—";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  return String(value);
}

function applyDriverDataChanges(changes = {}, lastField = "", updateLabel = "") {
  Object.entries(changes).forEach(([key, value]) => {
    if (key in driverDataState) {
      driverDataState[key] = value;
    }
  });
  lastUpdatedField = lastField;
  if (updateLabel) {
    driverLastUpdate.textContent = `Last update: ${updateLabel}`;
  }
  renderDriverData();
}

function applyToolResultToDriverData(toolName, result) {
  if (!result || typeof result !== "object") return;

  if (toolName === "get_driver_snapshot") {
    applyDriverDataChanges(
      {
        ...(result.driver || {}),
        ...(result.route || {}),
      },
      "",
      "snapshot loaded"
    );
    return;
  }

  if (toolName === "get_route_info") {
    applyDriverDataChanges(
      {
        load_id: result.load_id,
        status: result.status,
        current_location: result.current_location,
        next_stop: result.next_stop,
        eta_iso: result.eta_iso,
      },
      "",
      "route info refreshed"
    );
    return;
  }

  if (toolName === "get_hours_compliance_summary") {
    applyDriverDataChanges(
      {
        hours_left_today: result.drive_hours_left,
      },
      "hours_left_today",
      "hours updated"
    );
    return;
  }

  if (toolName === "update_eta") {
    applyDriverDataChanges(
      {
        eta_iso: result.updated_eta_iso,
        next_stop: result.next_stop,
        last_check_call: result.change_log?.changes?.["route.last_check_call"]?.after,
      },
      "eta_iso",
      result.updated_at || "ETA updated"
    );
    return;
  }

  if (toolName === "update_load_status") {
    applyDriverDataChanges(
      {
        status: result.check_call?.status,
        current_location: result.check_call?.location,
        last_check_call: result.check_call?.note,
      },
      "status",
      result.check_call?.timestamp || "load status updated"
    );
    return;
  }

  if (toolName === "submit_hometime_request") {
    const req = result.request || {};
    applyDriverDataChanges(
      {
        hometime_request_id: req.request_id,
        hometime_status: req.status,
        hometime_range: req.start_date && req.end_date ? `${req.start_date} to ${req.end_date}` : undefined,
        hometime_location: req.location,
      },
      "hometime_status",
      req.submitted_at || "hometime submitted"
    );
    return;
  }

  if (toolName === "get_hometime_status") {
    const req = result.request || {};
    applyDriverDataChanges(
      {
        hometime_request_id: req.request_id,
        hometime_status: req.status,
        hometime_range: req.start_date && req.end_date ? `${req.start_date} to ${req.end_date}` : undefined,
        hometime_location: req.location,
      },
      "hometime_status",
      "hometime status refreshed"
    );
  }
}

async function loadInitialDriverData() {
  try {
    const res = await fetch("/api/driver-data");
    if (!res.ok) return;
    const payload = await res.json();
    applyDriverDataChanges(
      {
        ...(payload.driver || {}),
        ...(payload.route || {}),
        hours_left_today: payload.hours?.drive_hours_left,
        hometime_request_id: payload.hometime?.request_id,
        hometime_status: payload.hometime?.status,
        hometime_range:
          payload.hometime?.start_date && payload.hometime?.end_date
            ? `${payload.hometime.start_date} to ${payload.hometime.end_date}`
            : undefined,
        hometime_location: payload.hometime?.location,
      },
      "",
      "initial load"
    );
  } catch (e) {
    console.error("Could not load driver data", e);
  }
}

// --- MediaHandler + GeminiClient ---
const mediaHandler = new MediaHandler();
const geminiClient = new GeminiClient({
  onOpen: () => {
    setStatus("Connected", "connected");
    setSessionLive(true);
    authSection.classList.add("hidden");
    appSection.classList.remove("hidden");
    loadInitialDriverData();

    geminiClient.sendText(
      "System: Introduce yourself as a truck driver in-cab copilot. " +
      "Mention you can help with route, ETA, pay, hours, load status, and hometime. " +
      "Keep it to two sentences."
    );
  },
  onMessage: (event) => {
    if (typeof event.data === "string") {
      try {
        const msg = JSON.parse(event.data);
        handleJsonMessage(msg);
      } catch (e) {
        console.error("Parse error:", e);
      }
    } else {
      mediaHandler.playAudio(event.data);
    }
  },
  onClose: (e) => {
    console.log("WS Closed:", e);
    setStatus("Disconnected", "disconnected");
    setSessionLive(false);
    showSessionEnd();
  },
  onError: (e) => {
    console.error("WS Error:", e);
    setStatus("Connection Error", "error");
    setSessionLive(false);
    showToast("Connection error. Try reconnecting.", "error");
  },
});

function handleJsonMessage(msg) {
  clearChatEmpty();

  if (msg.type === "interrupted") {
    mediaHandler.stopAudioPlayback();
    currentGeminiMessageDiv = null;
    currentUserMessageDiv = null;
  } else if (msg.type === "turn_complete") {
    currentGeminiMessageDiv = null;
    currentUserMessageDiv = null;
  } else if (msg.type === "user") {
    if (currentUserMessageDiv) {
      currentUserMessageDiv.textContent += msg.text;
      scrollChat();
    } else {
      currentUserMessageDiv = appendMessage("user", msg.text);
    }
  } else if (msg.type === "gemini") {
    if (currentGeminiMessageDiv) {
      currentGeminiMessageDiv.textContent += msg.text;
      scrollChat();
    } else {
      currentGeminiMessageDiv = appendMessage("gemini", msg.text);
    }
  } else if (msg.type === "tool_call") {
    const label = TOOL_LABELS[msg.name] || msg.name;
    applyToolResultToDriverData(msg.name, msg.result);
    if (WRITE_TOOLS.has(msg.name)) {
      showToast(label, "info");
    }
  } else if (msg.type === "error") {
    showToast("Session error: " + (msg.error || "unknown"), "error");
  }
}

function clearChatEmpty() {
  const empty = chatLog.querySelector(".chat-empty");
  if (empty) empty.remove();
}

function appendMessage(type, text) {
  const msgDiv = document.createElement("div");
  msgDiv.className = `message ${type}`;
  msgDiv.textContent = text;
  chatLog.appendChild(msgDiv);
  scrollChat();
  return msgDiv;
}

function scrollChat() {
  chatLog.scrollTop = chatLog.scrollHeight;
}

// --- Connect ---
connectBtn.onclick = async () => {
  setStatus("Connecting...", "connecting");
  connectBtn.disabled = true;

  try {
    await mediaHandler.initializeAudio();
    geminiClient.connect();
  } catch (error) {
    console.error("Connection error:", error);
    setStatus("Connection Failed", "error");
    connectBtn.disabled = false;
    showToast("Failed to connect: " + error.message, "error");
  }
};

// --- Disconnect ---
disconnectBtn.onclick = () => {
  geminiClient.disconnect();
};

// --- Mic ---
micBtn.onclick = async () => {
  if (micActive) {
    mediaHandler.stopAudio();
    micActive = false;
    micBtn.dataset.active = "false";
    micBtn.querySelector(".ctrl-label").textContent = "Mic Off";
  } else {
    try {
      await mediaHandler.startAudio((data) => {
        if (geminiClient.isConnected()) {
          geminiClient.send(data);
        }
      });
      micActive = true;
      micBtn.dataset.active = "true";
      micBtn.querySelector(".ctrl-label").textContent = "Mic On";
    } catch (e) {
      showToast("Could not start microphone", "error");
    }
  }
};

// --- Camera ---
cameraBtn.onclick = async () => {
  if (cameraActive) {
    mediaHandler.stopVideo(videoPreview);
    cameraActive = false;
    cameraBtn.dataset.active = "false";
    cameraBtn.querySelector(".ctrl-label").textContent = "Camera";
    videoPlaceholder.classList.remove("hidden");
  } else {
    if (screenActive) {
      mediaHandler.stopVideo(videoPreview);
      screenActive = false;
      screenBtn.dataset.active = "false";
      screenBtn.querySelector(".ctrl-label").textContent = "Screen";
    }
    try {
      await mediaHandler.startVideo(videoPreview, (base64Data) => {
        if (geminiClient.isConnected()) {
          geminiClient.sendImage(base64Data);
        }
      });
      cameraActive = true;
      cameraBtn.dataset.active = "true";
      cameraBtn.querySelector(".ctrl-label").textContent = "Cam On";
      videoPlaceholder.classList.add("hidden");
    } catch (e) {
      showToast("Could not access camera", "error");
    }
  }
};

// --- Screen Share ---
screenBtn.onclick = async () => {
  if (screenActive) {
    mediaHandler.stopVideo(videoPreview);
    screenActive = false;
    screenBtn.dataset.active = "false";
    screenBtn.querySelector(".ctrl-label").textContent = "Screen";
    videoPlaceholder.classList.remove("hidden");
  } else {
    if (cameraActive) {
      mediaHandler.stopVideo(videoPreview);
      cameraActive = false;
      cameraBtn.dataset.active = "false";
      cameraBtn.querySelector(".ctrl-label").textContent = "Camera";
    }
    try {
      await mediaHandler.startScreen(
        videoPreview,
        (base64Data) => {
          if (geminiClient.isConnected()) {
            geminiClient.sendImage(base64Data);
          }
        },
        () => {
          screenActive = false;
          screenBtn.dataset.active = "false";
          screenBtn.querySelector(".ctrl-label").textContent = "Screen";
          videoPlaceholder.classList.remove("hidden");
        }
      );
      screenActive = true;
      screenBtn.dataset.active = "true";
      screenBtn.querySelector(".ctrl-label").textContent = "Sharing";
      videoPlaceholder.classList.add("hidden");
    } catch (e) {
      showToast("Could not share screen", "error");
    }
  }
};

// --- Text Input ---
sendBtn.onclick = sendText;
textInput.onkeypress = (e) => {
  if (e.key === "Enter") sendText();
};

quickActionButtons.forEach((btn) => {
  btn.onclick = () => {
    const prompt = btn.dataset.prompt;
    if (prompt && geminiClient.isConnected()) {
      geminiClient.sendText(prompt);
      clearChatEmpty();
      appendMessage("user", prompt);
    } else if (!geminiClient.isConnected()) {
      showToast("Connect first to use quick actions", "warn");
    }
  };
});

function sendText() {
  const text = textInput.value.trim();
  if (text && geminiClient.isConnected()) {
    geminiClient.sendText(text);
    clearChatEmpty();
    appendMessage("user", text);
    textInput.value = "";
  }
}

// --- Session Lifecycle ---
function resetUI() {
  authSection.classList.remove("hidden");
  appSection.classList.add("hidden");
  sessionEndSection.classList.add("hidden");

  mediaHandler.stopAudio();
  mediaHandler.stopVideo(videoPreview);
  videoPlaceholder.classList.remove("hidden");

  micActive = false;
  cameraActive = false;
  screenActive = false;
  micBtn.dataset.active = "false";
  cameraBtn.dataset.active = "false";
  screenBtn.dataset.active = "false";
  micBtn.querySelector(".ctrl-label").textContent = "Mic Off";
  cameraBtn.querySelector(".ctrl-label").textContent = "Camera";
  screenBtn.querySelector(".ctrl-label").textContent = "Screen";

  currentGeminiMessageDiv = null;
  currentUserMessageDiv = null;
  lastUpdatedField = "";
  Object.keys(driverDataState).forEach((key) => {
    driverDataState[key] = "—";
  });
  driverLastUpdate.textContent = "No updates yet";
  renderDriverData();

  chatLog.innerHTML = '<div class="chat-empty">Voice transcript will appear here</div>';
  connectBtn.disabled = false;
  setStatus("Disconnected", "disconnected");
  setSessionLive(false);
}

function showSessionEnd() {
  appSection.classList.add("hidden");
  sessionEndSection.classList.remove("hidden");
  mediaHandler.stopAudio();
  mediaHandler.stopVideo(videoPreview);
  micActive = false;
  cameraActive = false;
  screenActive = false;
  currentGeminiMessageDiv = null;
  currentUserMessageDiv = null;
}

restartBtn.onclick = () => {
  resetUI();
};

renderDriverData();
