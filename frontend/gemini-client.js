const SESSION_HANDLE_KEY = "trucking_copilot_session_handle";

class GeminiClient {
  constructor(config) {
    this.onOpen = config.onOpen;
    this.onMessage = config.onMessage;
    this.onClose = config.onClose;
    this.onError = config.onError;
    this.onReconnecting = config.onReconnecting;
    this._reconnectAttempts = 0;
    this._maxReconnectAttempts = config.maxReconnectAttempts ?? 10;
    this._baseReconnectDelayMs = config.baseReconnectDelayMs ?? 800;
    this._reconnectTimer = null;
    this._intentionalDisconnect = false;
    this._pendingVadPreset = "normal";
    this._isResumeConnect = false;
  }

  getResumeHandle() {
    try {
      return sessionStorage.getItem(SESSION_HANDLE_KEY) || null;
    } catch {
      return null;
    }
  }

  setResumeHandle(handle) {
    if (!handle) return;
    try {
      sessionStorage.setItem(SESSION_HANDLE_KEY, handle);
    } catch (_) {}
  }

  clearResumeHandle() {
    try {
      sessionStorage.removeItem(SESSION_HANDLE_KEY);
    } catch (_) {}
  }

  setVadPreset(preset) {
    this._pendingVadPreset = (preset || "normal").toLowerCase();
  }

  getVadPreset() {
    return this._pendingVadPreset || "normal";
  }

  _sendSessionStart() {
    const payload = JSON.stringify({
      type: "session_start",
      resume_handle: this._isResumeConnect ? this.getResumeHandle() : null,
      vad_preset: this.getVadPreset(),
    });
    if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
      this.websocket.send(payload);
    }
  }

  connect(options = {}) {
    if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
      return;
    }
    this._intentionalDisconnect = false;
    this._isResumeConnect = Boolean(options.resume);

    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    this.websocket = new WebSocket(wsUrl);
    this.websocket.binaryType = "arraybuffer";

    this.websocket.onopen = () => {
      this._sendSessionStart();
      if (this._reconnectAttempts > 0) {
        this._reconnectAttempts = 0;
      }
      if (this.onOpen) this.onOpen({ resumed: this._isResumeConnect });
    };

    this.websocket.onmessage = (event) => {
      if (this.onMessage) this.onMessage(event);
    };

    this.websocket.onclose = (event) => {
      this.websocket = null;

      if (this._intentionalDisconnect) {
        if (this.onClose) this.onClose(event, { willReconnect: false });
        return;
      }
      if (this._reconnectAttempts >= this._maxReconnectAttempts) {
        if (this.onClose) this.onClose(event, { willReconnect: false });
        return;
      }

      this._reconnectAttempts += 1;
      const delay = Math.min(
        30000,
        this._baseReconnectDelayMs * Math.pow(2, this._reconnectAttempts - 1)
      );
      if (this.onReconnecting) {
        this.onReconnecting({
          attempt: this._reconnectAttempts,
          delayMs: delay,
          maxAttempts: this._maxReconnectAttempts,
        });
      }
      this._reconnectTimer = setTimeout(() => {
        this._reconnectTimer = null;
        this.connect({ resume: true });
      }, delay);
      if (this.onClose) {
        this.onClose(event, {
          willReconnect: true,
          attempt: this._reconnectAttempts,
          delayMs: delay,
        });
      }
    };

    this.websocket.onerror = (event) => {
      if (this.onError) this.onError(event);
    };
  }

  send(data) {
    if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
      this.websocket.send(data);
    }
  }

  sendImage(base64Data, mimeType = "image/jpeg", frameType = "image") {
    this.send(
      JSON.stringify({
        type: frameType,
        mime_type: mimeType,
        data: base64Data,
      })
    );
  }

  sendCameraFrame(base64Data, mimeType = "image/jpeg") {
    this.sendImage(base64Data, mimeType, "camera_frame");
  }

  sendScreenFrame(base64Data, mimeType = "image/jpeg") {
    this.sendImage(base64Data, mimeType, "screen_frame");
  }

  disconnect() {
    this._intentionalDisconnect = true;
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    this._reconnectAttempts = this._maxReconnectAttempts;
    if (this.websocket) {
      this.websocket.close();
      this.websocket = null;
    }
  }

  isConnected() {
    return this.websocket && this.websocket.readyState === WebSocket.OPEN;
  }
}
