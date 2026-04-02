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
const videoPreview = document.getElementById("video-preview");
const videoPlaceholder = document.getElementById("video-placeholder");
const connectBtn = document.getElementById("connectBtn");
const chatLog = document.getElementById("chat-log");
const sessionIndicator = document.getElementById("session-indicator");
const sessionLabel = document.getElementById("session-label");
const toastContainer = document.getElementById("toast-container");
const driverLastUpdate = document.getElementById("driver-last-update");
const driverDataContent = document.getElementById("driver-data-content");
const vadPresetSelect = document.getElementById("vadPreset");
const micLevelMeter = document.getElementById("micLevelMeter");
const micLevelFill = document.getElementById("micLevelFill");

let currentGeminiMessageDiv = null;
let currentUserMessageDiv = null;
let micActive = false;
let cameraActive = false;
let screenActive = false;
let lastUpdatedField = "";
let dispatchMessagesState = [];
let dispatchUnreadCount = 0;
let outboundTeamMessagesState = { driver_leader: [], csr: [] };
let assignedTeamContactsState = {
  driver_leader: { name: "", code: "", phone: "" },
  csr: { name: "", code: "", phone: "" },
};

const DRIVER_DATA_SECTIONS = [
  {
    title: "Driver & Truck",
    fields: [
      ["driver_id", "Driver ID"],
      ["name", "Name"],
      ["truck_number", "Truck #"],
      ["fleet", "Fleet"],
    ],
  },
  {
    title: "Active Load & Route",
    fields: [
      ["load_id", "Load ID"],
      ["status", "Status"],
      ["shipper", "Shipper / Pickup"],
      ["receiver", "Receiver / Delivery"],
      ["current_location", "Current Location"],
      ["next_stop", "Next Stop"],
      ["appointment_window", "Delivery Appointment Window"],
      ["last_check_call", "Last Check Call"],
    ],
  },
  {
    title: "ETA & Trip Progress",
    fields: [
      ["eta_iso", "ETA"],
      ["eta_confidence_minutes", "ETA Confidence (min)"],
      ["remaining_miles", "Remaining Miles"],
      ["can_make_appointment", "On Schedule"],
    ],
  },
  {
    title: "Hours of Service (HOS)",
    fields: [
      ["drive_hours_left", "Drive Hours Left"],
      ["on_duty_window_left", "On-Duty Left"],
      ["cycle_hours_left", "Cycle Left"],
      ["next_break_due_minutes", "Next Break (min)"],
      ["hours_violation_risk", "Violation Risk"],
      ["estimated_legal_stop", "Suggested Legal Stop"],
      ["hours_appointment_risk", "Hours vs Appt Risk"],
    ],
  },
  {
    title: "Pay & Settlement",
    fields: [
      ["miles_paid", "Miles Paid"],
      ["dispatched_miles", "Dispatched Miles"],
      ["rate_per_mile_usd", "Rate/Mile"],
      ["base_pay_usd", "Base Pay"],
      ["accessorials_usd", "Accessorials"],
      ["deductions_usd", "Deductions"],
      ["estimated_net_usd", "Estimated Net"],
      ["last_settlement_status", "Settlement Status"],
      ["next_settlement_date", "Next Pay Date"],
    ],
  },
  {
    title: "Hometime",
    fields: [
      ["hometime_request_id", "Request ID"],
      ["hometime_status", "Status"],
      ["hometime_range", "Date Range"],
      ["hometime_location", "Location"],
    ],
  },
  {
    title: "Contacts & escalation",
    fields: [
      ["contact_dl_phone", "Driver Leader phone"],
      ["contact_csr_phone", "CSR phone"],
      ["contact_departments_summary", "Company / dept lines"],
    ],
  },
];

const driverDataState = Object.fromEntries(
  DRIVER_DATA_SECTIONS.flatMap((s) => s.fields).map(([key]) => [key, "—"])
);

const WRITE_TOOLS = new Set([
  "update_eta",
  "update_load_status",
  "submit_hometime_request",
  "send_message_to_driver_leader",
  "send_message_to_csr",
]);

const TOOL_LABELS = {
  update_eta: "ETA Updated",
  update_load_status: "Load Status Updated",
  submit_hometime_request: "Hometime Request Submitted",
  get_driver_snapshot: "Driver Snapshot Retrieved",
  send_message_to_driver_leader: "Message queued to Driver Leader",
  send_message_to_csr: "Message queued to CSR",
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

function applyDispatchPayload(dispatch = {}) {
  const msgs = dispatch.messages;
  dispatchMessagesState = Array.isArray(msgs) ? msgs : [];
  dispatchUnreadCount =
    typeof dispatch.unread_count === "number" ? dispatch.unread_count : 0;
}

function applyOutboundTeamPayload(raw) {
  if (!raw || typeof raw !== "object") {
    outboundTeamMessagesState = { driver_leader: [], csr: [] };
    return;
  }
  const dl = Array.isArray(raw.driver_leader) ? raw.driver_leader : [];
  const csr = Array.isArray(raw.csr) ? raw.csr : [];
  outboundTeamMessagesState = {
    driver_leader: [...dl].reverse(),
    csr: [...csr].reverse(),
  };
}

function applyAssignedTeamContacts(raw) {
  if (!raw || typeof raw !== "object") return;
  const pick = (o) => ({
    name: typeof o?.name === "string" ? o.name : "",
    code: typeof o?.code === "string" ? o.code : "",
    phone: typeof o?.phone === "string" ? o.phone : "",
  });
  assignedTeamContactsState = {
    driver_leader: pick(raw.driver_leader),
    csr: pick(raw.csr),
  };
}

function prependOutboundTeamMessage(entry) {
  if (!entry || typeof entry !== "object") return;
  const r = entry.recipient === "csr" ? "csr" : "driver_leader";
  const arr = outboundTeamMessagesState[r];
  if (entry.message_id && arr.some((x) => x.message_id === entry.message_id)) return;
  arr.unshift(entry);
}

function renderDispatchSection(container) {
  const sectionDiv = document.createElement("div");
  sectionDiv.className = "driver-data-section driver-data-section--dispatch";

  const titleDiv = document.createElement("div");
  titleDiv.className = "section-title";
  titleDiv.textContent = "Dispatch Messages";
  sectionDiv.appendChild(titleDiv);

  const meta = document.createElement("div");
  meta.className = "dispatch-meta";
  meta.textContent =
    dispatchUnreadCount > 0
      ? `${dispatchUnreadCount} unread`
      : dispatchMessagesState.length
        ? "All messages read"
        : "No messages";
  sectionDiv.appendChild(meta);

  if (!dispatchMessagesState.length) {
    const empty = document.createElement("p");
    empty.className = "dispatch-empty";
    empty.textContent = "No fleet messages on file.";
    sectionDiv.appendChild(empty);
    container.appendChild(sectionDiv);
    return;
  }

  const list = document.createElement("div");
  list.className = "dispatch-messages-list";
  dispatchMessagesState.forEach((m) => {
    const card = document.createElement("article");
    card.className = `dispatch-message${m.read ? "" : " unread"}`;

    const head = document.createElement("div");
    head.className = "dispatch-message-head";

    const from = document.createElement("span");
    from.className = "dispatch-message-from";
    from.textContent = m.from || "—";

    const pri = document.createElement("span");
    pri.className = `dispatch-priority dispatch-priority--${(m.priority || "normal").toLowerCase()}`;
    pri.textContent = (m.priority || "normal").toUpperCase();

    head.appendChild(from);
    head.appendChild(pri);

    const subj = document.createElement("div");
    subj.className = "dispatch-message-subject";
    subj.textContent = m.subject || "(no subject)";

    const body = document.createElement("div");
    body.className = "dispatch-message-body";
    body.textContent = m.body || "";

    const foot = document.createElement("div");
    foot.className = "dispatch-message-foot";
    foot.textContent = m.sent_at ? String(m.sent_at) : "";

    card.appendChild(head);
    card.appendChild(subj);
    card.appendChild(body);
    card.appendChild(foot);
    list.appendChild(card);
  });

  sectionDiv.appendChild(list);
  container.appendChild(sectionDiv);
}

function formatOutboundContactCaption(m, recipientKey) {
  const c = m?.contact_name
    ? { name: m.contact_name, code: m.contact_code || "", phone: "" }
    : assignedTeamContactsState[recipientKey];
  if (!c?.name) return "";
  let s = c.code ? `${c.name} (${c.code})` : c.name;
  if (c.phone && String(c.phone).trim()) {
    s += ` · ${c.phone}`;
  }
  return s;
}

function outboundContactCells(m, recipientKey) {
  const fb = assignedTeamContactsState[recipientKey] || {};
  const nameRaw = [m.contact_name, fb.name].find(
    (x) => x != null && String(x).trim() !== ""
  );
  const codeRaw = [m.contact_code, fb.code].find(
    (x) => x != null && String(x).trim() !== ""
  );
  return {
    name: nameRaw != null ? String(nameRaw).trim() : "—",
    code: codeRaw != null ? String(codeRaw).trim() : "—",
  };
}

const OUTBOUND_TABLE_HEADERS = [
  "Message ID",
  "Status",
  "Contact name",
  "Contact code",
  "Subject",
  "Notes / dictation",
  "Timestamp",
  "Driver ID",
  "Load ID",
  "Location",
];

function renderOutboundSubsection(container, title, recipientKey) {
  const messages = outboundTeamMessagesState[recipientKey] || [];
  const wrap = document.createElement("div");
  wrap.className = "outbound-subsection";

  const h = document.createElement("div");
  h.className = "outbound-subsection-title";
  h.textContent = title;
  wrap.appendChild(h);

  const capText = formatOutboundContactCaption(messages[0], recipientKey);
  if (capText) {
    const cap = document.createElement("div");
    cap.className = "outbound-subsection-caption";
    cap.textContent = `Default assignee: ${capText}`;
    wrap.appendChild(cap);
  }

  if (!messages.length) {
    const empty = document.createElement("p");
    empty.className = "dispatch-empty";
    empty.textContent = "No messages sent yet.";
    wrap.appendChild(empty);
    container.appendChild(wrap);
    return;
  }

  const scroll = document.createElement("div");
  scroll.className = "outbound-table-wrap";
  scroll.setAttribute("role", "region");
  scroll.setAttribute(
    "aria-label",
    `${title} outbound messages`
  );

  const table = document.createElement("table");
  table.className = "outbound-table";

  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  OUTBOUND_TABLE_HEADERS.forEach((label) => {
    const th = document.createElement("th");
    th.scope = "col";
    th.textContent = label;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  messages.forEach((m) => {
    const tr = document.createElement("tr");
    const { name: contactName, code: contactCode } = outboundContactCells(
      m,
      recipientKey
    );

    const tdId = document.createElement("td");
    tdId.className = "outbound-cell-mono";
    tdId.textContent = m.message_id || "—";
    tr.appendChild(tdId);

    const tdStatus = document.createElement("td");
    const statusPill = document.createElement("span");
    statusPill.className = "outbound-status-pill";
    statusPill.textContent = (m.status || "queued").toUpperCase();
    tdStatus.appendChild(statusPill);
    tr.appendChild(tdStatus);

    const tdCName = document.createElement("td");
    tdCName.textContent = contactName;
    tr.appendChild(tdCName);

    const tdCCode = document.createElement("td");
    tdCCode.className = "outbound-cell-mono";
    tdCCode.textContent = contactCode;
    tr.appendChild(tdCCode);

    const tdSubj = document.createElement("td");
    tdSubj.className = "outbound-cell-subject";
    tdSubj.textContent = m.subject || "—";
    tr.appendChild(tdSubj);

    const tdNotes = document.createElement("td");
    tdNotes.className = "outbound-cell-notes";
    tdNotes.textContent = m.notes_dictation || "";
    tr.appendChild(tdNotes);

    const tdTs = document.createElement("td");
    tdTs.className = "outbound-cell-mono outbound-cell-nowrap";
    tdTs.textContent = m.timestamp ? String(m.timestamp) : "—";
    tr.appendChild(tdTs);

    const tdDriver = document.createElement("td");
    tdDriver.className = "outbound-cell-mono";
    tdDriver.textContent = m.driver_id || "—";
    tr.appendChild(tdDriver);

    const tdLoad = document.createElement("td");
    tdLoad.className = "outbound-cell-mono";
    tdLoad.textContent = m.load_id || "—";
    tr.appendChild(tdLoad);

    const tdLoc = document.createElement("td");
    tdLoc.textContent = m.current_location || "—";
    tr.appendChild(tdLoc);

    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  scroll.appendChild(table);
  wrap.appendChild(scroll);
  container.appendChild(wrap);
}

function renderOutboundTeamSection(container) {
  const sectionDiv = document.createElement("div");
  sectionDiv.className = "driver-data-section driver-data-section--outbound";

  const titleDiv = document.createElement("div");
  titleDiv.className = "section-title";
  titleDiv.textContent = "Your messages (DL & CSR)";
  sectionDiv.appendChild(titleDiv);

  const intro = document.createElement("div");
  intro.className = "outbound-section-intro";
  intro.textContent =
    "Notes you sent to your Driver Leader or CSR from the copilot (demo: queued in session).";
  sectionDiv.appendChild(intro);

  renderOutboundSubsection(sectionDiv, "Driver Leader", "driver_leader");
  renderOutboundSubsection(sectionDiv, "CSR", "csr");

  container.appendChild(sectionDiv);
}

function renderDriverData() {
  driverDataContent.innerHTML = "";

  DRIVER_DATA_SECTIONS.forEach((section, index) => {
    const sectionDiv = document.createElement("div");
    sectionDiv.className = "driver-data-section";

    const titleDiv = document.createElement("div");
    titleDiv.className = "section-title";
    titleDiv.textContent = section.title;
    sectionDiv.appendChild(titleDiv);

    const gridDiv = document.createElement("div");
    gridDiv.className = "driver-data-grid";

    section.fields.forEach(([key, label]) => {
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
      gridDiv.appendChild(item);
    });

    sectionDiv.appendChild(gridDiv);
    driverDataContent.appendChild(sectionDiv);

    if (index === 1) {
      renderDispatchSection(driverDataContent);
      renderOutboundTeamSection(driverDataContent);
    }
  });
}

function formatDriverValue(value) {
  if (value === undefined || value === null || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  return String(value);
}

function flattenTripAppointment(trip = {}, appointment = {}) {
  return {
    eta_confidence_minutes: trip.eta_confidence_minutes,
    can_make_appointment: appointment.can_make_appointment,
  };
}

function flattenHoursSummary(h = {}) {
  return {
    drive_hours_left: h.drive_hours_left,
    on_duty_window_left: h.on_duty_window_left,
    cycle_hours_left: h.cycle_hours_left,
    next_break_due_minutes: h.next_break_due_minutes,
    hours_violation_risk: h.violation_risk,
    estimated_legal_stop: h.estimated_legal_stop,
    hours_appointment_risk: h.appointment_risk,
  };
}

function flattenOperationsContacts(c = {}) {
  const dl = c.driver_leader || {};
  const csr = c.csr || {};
  const depts = Array.isArray(c.departments) ? c.departments : [];
  const summary = depts
    .map((d) => `${d.department || "—"}: ${d.phone || "—"}`)
    .join("; ");
  return {
    contact_dl_phone: dl.phone && String(dl.phone).trim() ? String(dl.phone) : undefined,
    contact_csr_phone: csr.phone && String(csr.phone).trim() ? String(csr.phone) : undefined,
    contact_departments_summary: summary || undefined,
  };
}

function flattenPaySummary(p = {}) {
  return {
    miles_paid: p.miles_paid,
    dispatched_miles: p.dispatched_miles,
    rate_per_mile_usd: p.rate_per_mile_usd,
    base_pay_usd: p.base_pay_usd,
    accessorials_usd: p.accessorials_usd,
    deductions_usd: p.deductions_usd,
    estimated_net_usd: p.estimated_net_usd,
    last_settlement_status: p.last_settlement_status,
    next_settlement_date: p.next_settlement_date,
  };
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
    const sp = result.stop_plan || {};
    const h = sp.hours || {};
    const pay = result.pay || {};
    const ht = result.hometime || {};
    const contacts = result.contacts || {};
    if (contacts.driver_leader || contacts.csr) {
      applyAssignedTeamContacts({
        driver_leader: contacts.driver_leader,
        csr: contacts.csr,
      });
    }
    const merged = {
      ...(result.driver || {}),
      ...(result.route || {}),
      ...flattenTripAppointment(result.trip || {}, result.appointment || {}),
      ...flattenHoursSummary(h),
      ...flattenPaySummary(pay),
      ...flattenOperationsContacts(contacts),
    };
    if (ht.success && ht.request) {
      const req = ht.request;
      merged.hometime_request_id = req.request_id;
      merged.hometime_status = req.status;
      merged.hometime_range =
        req.start_date && req.end_date ? `${req.start_date} to ${req.end_date}` : undefined;
      merged.hometime_location = req.location;
    }
    applyDispatchPayload(result.dispatch || {});
    applyDriverDataChanges(merged, "drive_hours_left", "snapshot refreshed");
    return;
  }

  if (toolName === "send_message_to_driver_leader" || toolName === "send_message_to_csr") {
    const qm = result.queued_message;
    if (qm) {
      prependOutboundTeamMessage(qm);
      renderDriverData();
    }
    return;
  }

  if (toolName === "update_eta") {
    applyDriverDataChanges(
      {
        eta_iso: result.updated_eta_iso,
        next_stop: result.next_stop,
        last_check_call: result.last_check_call,
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

}

async function loadInitialDriverData() {
  try {
    const res = await fetch("/api/driver-data");
    if (!res.ok) return;
    const payload = await res.json();
    applyDispatchPayload(payload.dispatch || {});
    applyOutboundTeamPayload(payload.outbound_team_messages);
    applyAssignedTeamContacts(payload.assigned_team_contacts);
    applyDriverDataChanges(
      {
        ...(payload.driver || {}),
        ...(payload.route || {}),
        ...flattenTripAppointment(payload.trip || {}, payload.appointment || {}),
        ...flattenHoursSummary(payload.hours || {}),
        ...flattenPaySummary(payload.pay || {}),
        ...flattenOperationsContacts(payload.operations_contacts || {}),
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
  onOpen: (info = {}) => {
    setStatus("Connected", "connected");
    setSessionLive(true);
    authSection.classList.add("hidden");
    appSection.classList.remove("hidden");
    sessionEndSection.classList.add("hidden");
    loadInitialDriverData();

    if (info.resumed) {
      showToast("Connection restored — session resumed.", "info");
    }

    void startMicStreaming();
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
  onClose: (e, meta = {}) => {
    console.log("WS Closed:", e, meta);
    if (meta.willReconnect) {
      setStatus(
        `Reconnecting (${meta.attempt})…`,
        "connecting"
      );
      setSessionLive(false);
      return;
    }
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

function appendSystemMessage(text) {
  const el = document.createElement("div");
  el.className = "message system-msg";
  el.textContent = text;
  chatLog.appendChild(el);
  scrollChat();
  return el;
}

function handleJsonMessage(msg) {
  clearChatEmpty();

  if (msg.type === "session_resumption" && msg.new_handle) {
    geminiClient.setResumeHandle(msg.new_handle);
    return;
  }

  if (msg.type === "interrupted") {
    mediaHandler.stopAudioPlayback();
    if (currentGeminiMessageDiv) {
      currentGeminiMessageDiv.classList.add("interrupted-partial");
      const marker = document.createElement("span");
      marker.className = "interrupt-marker";
      marker.textContent = " · interrupted";
      currentGeminiMessageDiv.appendChild(marker);
    }
    appendSystemMessage("You interrupted — Copilot stopped speaking. Listening for you.");
    currentGeminiMessageDiv = null;
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
    const res = msg.result;
    if (res && typeof res === "object" && res.success === false) {
      const detail = res.message || res.error_code || res.detail || "Tool failed";
      showToast(`${label}: ${detail}`, "error");
    } else {
      applyToolResultToDriverData(msg.name, res);
      if (WRITE_TOOLS.has(msg.name)) {
        showToast(label, "info");
      }
    }
  } else if (msg.type === "error") {
    showToast("Session error: " + (msg.error || "unknown"), "error");
    if (msg.fatal) {
      geminiClient.clearResumeHandle();
    }
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

let micLevelRaf = null;
let pendingMicLevel = 0;

function updateMicLevel(level01) {
  pendingMicLevel = Math.max(0, Math.min(1, level01));
  if (micLevelRaf != null) return;
  micLevelRaf = requestAnimationFrame(() => {
    micLevelRaf = null;
    const v = pendingMicLevel;
    if (micLevelFill) {
      micLevelFill.style.width = `${Math.round(v * 100)}%`;
    }
    if (micLevelMeter) {
      micLevelMeter.setAttribute("aria-valuenow", String(Math.round(v * 100)));
    }
  });
}

function setMicUi(on) {
  micActive = on;
  micBtn.dataset.active = on ? "true" : "false";
  micBtn.querySelector(".ctrl-label").textContent = on ? "Mic On" : "Mic Off";
  if (!on) {
    updateMicLevel(0);
  }
}

async function startMicStreaming() {
  if (micActive) return;
  try {
    await mediaHandler.startAudio(
      (data) => {
        if (geminiClient.isConnected()) {
          geminiClient.send(data);
        }
      },
      { onLevel: updateMicLevel }
    );
    setMicUi(true);
  } catch (e) {
    console.error("startMicStreaming:", e);
    showToast("Could not start microphone", "error");
  }
}

function stopMicStreaming() {
  if (!micActive) {
    updateMicLevel(0);
    return;
  }
  mediaHandler.stopAudio();
  setMicUi(false);
}

// --- Connect ---
if (vadPresetSelect) {
  vadPresetSelect.addEventListener("change", () => {
    geminiClient.setVadPreset(vadPresetSelect.value);
    showToast("Mic environment applies on your next connection.", "info");
  });
}

connectBtn.onclick = async () => {
  setStatus("Connecting...", "connecting");
  connectBtn.disabled = true;

  try {
    if (vadPresetSelect) {
      geminiClient.setVadPreset(vadPresetSelect.value);
    }
    await mediaHandler.initializeAudio();
    geminiClient.connect({ resume: false });
  } catch (error) {
    console.error("Connection error:", error);
    setStatus("Connection Failed", "error");
    connectBtn.disabled = false;
    showToast("Failed to connect: " + error.message, "error");
  }
};

// --- Disconnect ---
disconnectBtn.onclick = () => {
  geminiClient.clearResumeHandle();
  geminiClient.disconnect();
};

// --- Mic ---
micBtn.onclick = async () => {
  if (micActive) {
    stopMicStreaming();
  } else {
    await startMicStreaming();
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

// --- Session Lifecycle ---
function resetUI() {
  geminiClient.clearResumeHandle();
  authSection.classList.remove("hidden");
  appSection.classList.add("hidden");
  sessionEndSection.classList.add("hidden");

  mediaHandler.stopAudio();
  mediaHandler.stopVideo(videoPreview);
  videoPlaceholder.classList.remove("hidden");

  setMicUi(false);
  cameraActive = false;
  screenActive = false;
  cameraBtn.dataset.active = "false";
  screenBtn.dataset.active = "false";
  cameraBtn.querySelector(".ctrl-label").textContent = "Camera";
  screenBtn.querySelector(".ctrl-label").textContent = "Screen";

  currentGeminiMessageDiv = null;
  currentUserMessageDiv = null;
  lastUpdatedField = "";
  Object.keys(driverDataState).forEach((key) => {
    driverDataState[key] = "—";
  });
  dispatchMessagesState = [];
  dispatchUnreadCount = 0;
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
  setMicUi(false);
  cameraActive = false;
  screenActive = false;
  currentGeminiMessageDiv = null;
  currentUserMessageDiv = null;
}

restartBtn.onclick = () => {
  resetUI();
};

renderDriverData();
