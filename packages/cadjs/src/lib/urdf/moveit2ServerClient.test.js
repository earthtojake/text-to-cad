import assert from "node:assert/strict";
import test from "node:test";

import {
  checkMoveIt2ServerLive,
  closeMoveIt2ServerConnection,
  moveit2ServerAvailable,
  moveit2ServerEnabled,
  moveit2ServerUrl,
  requestMoveIt2Server,
} from "./moveit2ServerClient.js";

class FakeWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 3;

  static sockets = [];

  constructor(url) {
    this.url = url;
    this.readyState = FakeWebSocket.CONNECTING;
    this.listeners = new Map();
    this.sent = [];
    FakeWebSocket.sockets.push(this);
  }

  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) || [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }

  removeEventListener(type, listener) {
    const listeners = this.listeners.get(type) || [];
    this.listeners.set(type, listeners.filter((candidate) => candidate !== listener));
  }

  send(message) {
    this.sent.push(JSON.parse(message));
  }

  close() {
    this.readyState = FakeWebSocket.CLOSED;
    this.emit("close");
  }

  open() {
    this.readyState = FakeWebSocket.OPEN;
    this.emit("open");
  }

  respond(message) {
    this.emit("message", { data: JSON.stringify(message) });
  }

  emit(type, event = {}) {
    for (const listener of this.listeners.get(type) || []) {
      listener(event);
    }
  }
}

test.beforeEach(() => {
  FakeWebSocket.sockets = [];
  closeMoveIt2ServerConnection();
});

test.afterEach(() => {
  closeMoveIt2ServerConnection();
});

test("requestMoveIt2Server sends request IDs and resolves matching responses", async () => {
  const promise = requestMoveIt2Server("srdf.solvePose", {
    id: "req-1",
    file: "sample_robot.srdf",
  }, {
    url: "ws://moveit2.test/ws",
    WebSocketImpl: FakeWebSocket,
    timeoutMs: 1000,
  });

  assert.equal(FakeWebSocket.sockets.length, 1);
  const socket = FakeWebSocket.sockets[0];
  assert.equal(socket.url, "ws://moveit2.test/ws");
  socket.open();
  assert.deepEqual(socket.sent[0], {
    id: "req-1",
    type: "srdf.solvePose",
    protocolVersion: 1,
    payload: {
      id: "req-1",
      file: "sample_robot.srdf",
    },
  });
  socket.respond({
    id: "req-1",
    ok: true,
    result: {
      jointValuesByNameDeg: {
        joint_2: 42,
      },
    },
  });

  assert.deepEqual(await promise, {
    jointValuesByNameDeg: {
      joint_2: 42,
    },
  });
});

test("requestMoveIt2Server rejects server errors", async () => {
  const promise = requestMoveIt2Server("srdf.solvePose", { id: "req-2" }, {
    url: "ws://moveit2.test/ws",
    WebSocketImpl: FakeWebSocket,
    timeoutMs: 1000,
  });
  const socket = FakeWebSocket.sockets[0];
  socket.open();
  socket.respond({
    id: "req-2",
    ok: false,
    error: {
      message: "planning failed",
    },
  });

  await assert.rejects(promise, /planning failed/);
});

test("moveit2ServerAvailable reflects WebSocket support", () => {
  assert.equal(moveit2ServerAvailable({ WebSocketImpl: FakeWebSocket }), true);
  assert.equal(moveit2ServerAvailable({ WebSocketImpl: null }), false);
});

test("moveit2ServerEnabled can disable production MoveIt2 connections", () => {
  assert.equal(moveit2ServerEnabled({ enabled: true }), true);
  assert.equal(moveit2ServerEnabled({ enabled: false }), false);
  assert.equal(moveit2ServerAvailable({ WebSocketImpl: FakeWebSocket, enabled: false }), false);
});

test("checkMoveIt2ServerLive resolves true when websocket opens", async () => {
  const promise = checkMoveIt2ServerLive({
    url: "ws://moveit2.test/ws",
    WebSocketImpl: FakeWebSocket,
    timeoutMs: 1000,
  });
  const socket = FakeWebSocket.sockets[0];
  assert.equal(socket.url, "ws://moveit2.test/ws");
  socket.open();

  assert.equal(await promise, true);
  assert.equal(socket.readyState, FakeWebSocket.CLOSED);
});

test("checkMoveIt2ServerLive resolves false when websocket errors before opening", async () => {
  const promise = checkMoveIt2ServerLive({
    url: "ws://moveit2.test/ws",
    WebSocketImpl: FakeWebSocket,
    timeoutMs: 1000,
  });
  FakeWebSocket.sockets[0].emit("error");

  assert.equal(await promise, false);
});

test("checkMoveIt2ServerLive does not open a websocket when disabled", async () => {
  const live = await checkMoveIt2ServerLive({
    url: "ws://moveit2.test/ws",
    WebSocketImpl: FakeWebSocket,
    enabled: false,
    timeoutMs: 1000,
  });

  assert.equal(live, false);
  assert.equal(FakeWebSocket.sockets.length, 0);
});

test("requestMoveIt2Server rejects without opening a websocket when disabled", async () => {
  await assert.rejects(
    requestMoveIt2Server("srdf.solvePose", { id: "req-disabled" }, {
      url: "ws://moveit2.test/ws",
      WebSocketImpl: FakeWebSocket,
      enabled: false,
      timeoutMs: 1000,
    }),
    /not enabled/
  );
  assert.equal(FakeWebSocket.sockets.length, 0);
});

test("moveit2ServerUrl uses the generic query override", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    location: {
      href: "http://127.0.0.1:3245/?moveit2Ws=ws%3A%2F%2Fmoveit2.test%2Fws",
    },
  };
  try {
    assert.equal(moveit2ServerUrl(), "ws://moveit2.test/ws");
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});

test("moveit2ServerUrl ignores query overrides when disabled", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    location: {
      href: "http://127.0.0.1:3245/?moveit2Ws=ws%3A%2F%2Fmoveit2.test%2Fws",
    },
  };
  try {
    assert.equal(moveit2ServerUrl({ enabled: false }), "");
  } finally {
    if (originalWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = originalWindow;
    }
  }
});
