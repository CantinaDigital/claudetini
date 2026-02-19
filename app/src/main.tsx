import React from "react";
import ReactDOM from "react-dom/client";
import { listen } from "@tauri-apps/api/event";
import { invoke } from "@tauri-apps/api/core";
import { AppRouter } from "./AppRouter";
import { setApiPort } from "./api/backend";
import "./styles/global.css";

// Listen for sidecar ready event (emitted by Rust after health poll succeeds).
// This handles the normal case where the listener registers before the event fires.
listen<{ port: number }>("sidecar-ready", (event) => {
  setApiPort(event.payload.port);
}).catch(() => {
  // Not running in Tauri context (dev server only) -- use default port
});

// Fallback: if the event already fired before the listener was registered,
// invoke the Tauri command to get the port directly.
invoke<number | null>("get_sidecar_port")
  .then((port) => {
    if (port && port > 0) {
      setApiPort(port);
    }
  })
  .catch(() => {
    // Not running in Tauri context or sidecar not ready yet -- use default port
  });

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <AppRouter />
  </React.StrictMode>
);
