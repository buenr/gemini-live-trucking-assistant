class GeminiClient {
  constructor(config) {
    this.websocket = null;
    this.onOpen = config.onOpen;
    this.onMessage = config.onMessage;
    this.onClose = config.onClose;
    this.onError = config.onError;
    this._reconnectAttempts = 0;
    this._maxReconnect = 0;
  }

  connect() {
    if (this.websocket && this.websocket.readyState <= WebSocket.OPEN) {
      return;
    }
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    this.websocket = new WebSocket(wsUrl);
    this.websocket.binaryType = "arraybuffer";

    this.websocket.onopen = () => {
      this._reconnectAttempts = 0;
      if (this.onOpen) this.onOpen();
    };

    this.websocket.onmessage = (event) => {
      if (this.onMessage) this.onMessage(event);
    };

    this.websocket.onclose = (event) => {
      if (this.onClose) this.onClose(event);
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

  sendText(text) {
    this.send(text);
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
    if (this.websocket) {
      this.websocket.close();
      this.websocket = null;
    }
  }

  isConnected() {
    return this.websocket && this.websocket.readyState === WebSocket.OPEN;
  }
}
