const DEFAULT_TIMEOUT_MS = 60000;
const DEFAULT_MOTION_SERVER_WS_URL = "ws://127.0.0.1:8765/ws";

const pendingRequests = new Map();
let socket = null;
let socketUrl = "";

function defaultMotionServerEnabled() {
  const env = typeof import.meta !== "undefined" ? import.meta.env : null;
  if (env && typeof env === "object" && Object.hasOwn(env, "DEV")) {
    return Boolean(env.DEV);
  }
  return true;
}

export function motionServerEnabled({ enabled = defaultMotionServerEnabled() } = {}) {
  return Boolean(enabled);
}

function normalizeRequestId(value) {
  const id = String(value || "").trim();
  if (id) {
    return id;
  }
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `motion-server-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

function configuredMotionServerUrl({ enabled = motionServerEnabled() } = {}) {
  if (!motionServerEnabled({ enabled })) {
    return "";
  }
  const envUrl = typeof import.meta !== "undefined"
    ? String(import.meta.env?.EXPLORER_ROBOT_MOTION_WS_URL || "").trim()
    : "";
  if (envUrl) {
    return envUrl;
  }
  return DEFAULT_MOTION_SERVER_WS_URL;
}

export function motionServerUrl({ enabled = motionServerEnabled() } = {}) {
  if (!motionServerEnabled({ enabled })) {
    return "";
  }
  if (typeof window === "undefined") {
    return configuredMotionServerUrl({ enabled });
  }
  const queryUrl = new URL(window.location.href).searchParams.get("motionWs");
  return String(queryUrl || "").trim() || configuredMotionServerUrl({ enabled });
}

function rejectPendingRequests(message) {
  for (const [id, pending] of pendingRequests.entries()) {
    clearTimeout(pending.timer);
    pending.reject(new Error(message));
    pendingRequests.delete(id);
  }
}

function resetSocket(message = "Motion server connection closed.") {
  rejectPendingRequests(message);
  socket = null;
  socketUrl = "";
}

function ensureMotionServerSocket(url, WebSocketImpl) {
  if (!WebSocketImpl) {
    throw new Error("Motion server requires browser WebSocket support.");
  }
  if (socket && socketUrl === url && socket.readyState <= WebSocketImpl.OPEN) {
    return socket;
  }
  if (socket) {
    socket.close();
    resetSocket("Motion server connection changed.");
  }
  socket = new WebSocketImpl(url);
  socketUrl = url;
  socket.addEventListener("message", (event) => {
    let message;
    try {
      message = JSON.parse(String(event.data || ""));
    } catch {
      return;
    }
    const id = String(message?.id || "").trim();
    const pending = pendingRequests.get(id);
    if (!pending) {
      return;
    }
    pendingRequests.delete(id);
    clearTimeout(pending.timer);
    if (message?.ok === false) {
      pending.reject(new Error(String(message?.error?.message || "Motion server request failed.")));
      return;
    }
    pending.resolve(message?.result ?? {});
  });
  socket.addEventListener("close", () => resetSocket("Motion server connection closed."));
  socket.addEventListener("error", () => {
    if (socket?.readyState !== WebSocketImpl.OPEN) {
      resetSocket(`Could not connect to motion server at ${url}.`);
    }
  });
  return socket;
}

function sendWhenOpen(activeSocket, message, resolve, reject) {
  const openState = activeSocket.constructor?.OPEN ?? 1;
  if (activeSocket.readyState === openState) {
    activeSocket.send(message);
    resolve();
    return;
  }
  const handleOpen = () => {
    activeSocket.removeEventListener("open", handleOpen);
    activeSocket.send(message);
    resolve();
  };
  activeSocket.addEventListener("open", handleOpen);
}

export function motionServerAvailable({
  WebSocketImpl = globalThis.WebSocket,
  enabled = motionServerEnabled(),
} = {}) {
  return Boolean(enabled && WebSocketImpl);
}

export function checkMotionServerLive({
  timeoutMs = 1000,
  url = motionServerUrl(),
  WebSocketImpl = globalThis.WebSocket,
  enabled = motionServerEnabled(),
} = {}) {
  const safeTimeoutMs = Math.max(Number(timeoutMs) || 1000, 1);
  return new Promise((resolve) => {
    if (!enabled || !url || !WebSocketImpl) {
      resolve(false);
      return;
    }
    let settled = false;
    let activeSocket = null;
    let timer = 0;
    const settle = (isLive) => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timer);
      if (activeSocket && isLive) {
        activeSocket.close();
      }
      resolve(Boolean(isLive));
    };
    timer = setTimeout(() => settle(false), safeTimeoutMs);
    try {
      activeSocket = new WebSocketImpl(url);
    } catch {
      settle(false);
      return;
    }
    activeSocket.addEventListener("open", () => settle(true));
    activeSocket.addEventListener("error", () => settle(false));
    activeSocket.addEventListener("close", () => settle(false));
  });
}

export function requestMotionServer(type, payload, {
  timeoutMs = DEFAULT_TIMEOUT_MS,
  url = motionServerUrl(),
  WebSocketImpl = globalThis.WebSocket,
  enabled = motionServerEnabled(),
} = {}) {
  const id = normalizeRequestId(payload?.id);
  const safeTimeoutMs = Math.max(Number(timeoutMs) || DEFAULT_TIMEOUT_MS, 1);
  return new Promise((resolve, reject) => {
    if (!enabled || !url) {
      reject(new Error("Motion server connections are only available in local development."));
      return;
    }
    let activeSocket;
    try {
      activeSocket = ensureMotionServerSocket(url, WebSocketImpl);
    } catch (error) {
      reject(error);
      return;
    }
    const timer = setTimeout(() => {
      pendingRequests.delete(id);
      reject(new Error(`Motion server request ${id} timed out.`));
    }, safeTimeoutMs);
    pendingRequests.set(id, { resolve, reject, timer });
    const message = JSON.stringify({
      id,
      type,
      payload
    });
    sendWhenOpen(activeSocket, message, () => {}, (error) => {
      pendingRequests.delete(id);
      clearTimeout(timer);
      reject(error);
    });
  });
}

export function closeMotionServerConnection() {
  if (socket) {
    socket.close();
  }
  resetSocket("Motion server connection closed.");
}
