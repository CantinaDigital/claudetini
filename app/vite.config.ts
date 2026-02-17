import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { existsSync } from "fs";
import { resolve } from "path";

// @ts-expect-error process is a nodejs global
const host = process.env.TAURI_DEV_HOST;

/**
 * Suppress Vite HMR while parallel execution is merging branches.
 * The orchestrator writes `.parallel-running` at execution start and
 * removes it when done. While the file exists, all HMR updates are
 * swallowed so git merges don't flash-reload the app.
 */
function parallelHmrGuard(): Plugin {
  const lockFile = resolve(__dirname, ".parallel-running");

  return {
    name: "parallel-hmr-guard",
    handleHotUpdate() {
      if (existsSync(lockFile)) {
        return [];
      }
    },
  };
}

// https://vite.dev/config/
export default defineConfig(async () => ({
  plugins: [react(), parallelHmrGuard()],

  // Vite options tailored for Tauri development and only applied in `tauri dev` or `tauri build`
  //
  // 1. prevent Vite from obscuring rust errors
  clearScreen: false,
  // 2. tauri expects a fixed port, fail if that port is not available
  server: {
    port: 1420,
    strictPort: true,
    host: host || false,
    hmr: host
      ? {
          protocol: "ws",
          host,
          port: 1421,
        }
      : undefined,
    watch: {
      // 3. tell Vite to ignore watching `src-tauri`
      ignored: ["**/src-tauri/**"],
    },
  },
}));
