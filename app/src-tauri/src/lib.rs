use std::net::TcpListener;
use std::sync::Mutex;

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, RunEvent};
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};

/// Holds the sidecar port and child handle for lifecycle management.
struct SidecarState {
    port: u16,
    child: Option<CommandChild>,
}

/// Payload emitted to the frontend when the sidecar is healthy.
#[derive(Clone, Serialize)]
struct SidecarReadyPayload {
    port: u16,
}

/// Bind to 127.0.0.1:0 and let the OS assign an available port.
fn find_free_port() -> Result<u16, String> {
    let listener =
        TcpListener::bind("127.0.0.1:0").map_err(|e| format!("Failed to bind TCP: {e}"))?;
    let port = listener
        .local_addr()
        .map_err(|e| format!("Failed to get local addr: {e}"))?
        .port();
    Ok(port)
}

/// Poll the sidecar health endpoint via raw TCP connect.
/// We only check that a TCP connection succeeds (not full HTTP) to keep
/// dependencies minimal on the Rust side.
async fn poll_health(port: u16, max_attempts: u32) -> Result<(), String> {
    use tokio::net::TcpStream;
    use tokio::time::{sleep, Duration};

    for attempt in 1..=max_attempts {
        match TcpStream::connect(format!("127.0.0.1:{port}")).await {
            Ok(_) => {
                println!("Sidecar healthy on port {port} (attempt {attempt}/{max_attempts})");
                return Ok(());
            }
            Err(_) => {
                if attempt < max_attempts {
                    sleep(Duration::from_millis(200)).await;
                }
            }
        }
    }
    Err(format!(
        "Sidecar failed to become healthy after {max_attempts} attempts on port {port}"
    ))
}

/// Spawn the sidecar binary and wait for it to become healthy.
/// In dev mode we skip spawning and assume port 9876.
fn spawn_sidecar(app_handle: &AppHandle) {
    if cfg!(debug_assertions) {
        // Dev mode: sidecar runs externally on the default port.
        let port: u16 = 9876;
        println!("Dev mode: assuming sidecar on port {port}");

        let state = app_handle.state::<Mutex<SidecarState>>();
        if let Ok(mut s) = state.lock() {
            s.port = port;
        }

        let handle = app_handle.clone();
        tauri::async_runtime::spawn(async move {
            // Give the external sidecar a moment, then emit ready
            if poll_health(port, 30).await.is_ok() {
                let _ = handle.emit("sidecar-ready", SidecarReadyPayload { port });
            } else {
                eprintln!("Dev sidecar not reachable on port {port} -- frontend will retry");
            }
        });
        return;
    }

    // Release mode: find a free port, spawn the bundled binary via Tauri shell plugin.
    let port = match find_free_port() {
        Ok(p) => p,
        Err(e) => {
            eprintln!("Could not find free port: {e}");
            return;
        }
    };

    println!("Spawning sidecar on port {port}");

    // Use the Tauri shell plugin's sidecar API, which handles path resolution
    // and target-triple binary naming automatically.
    let sidecar_command = match app_handle
        .shell()
        .sidecar("claudetini-sidecar")
    {
        Ok(cmd) => cmd.args(["--port", &port.to_string()]),
        Err(e) => {
            eprintln!("Failed to create sidecar command: {e}");
            return;
        }
    };

    match sidecar_command.spawn() {
        Ok((rx, child)) => {
            println!("Sidecar process spawned, polling health...");

            // Store the child handle in managed state so it lives for the
            // app's lifetime and can be killed on shutdown.
            let state = app_handle.state::<Mutex<SidecarState>>();
            if let Ok(mut s) = state.lock() {
                s.port = port;
                s.child = Some(child);
            }

            // Consume the event receiver in a background task to keep the
            // channel alive and log sidecar output.
            tauri::async_runtime::spawn(async move {
                drain_sidecar_events(rx).await;
            });

            // Poll health in the background, then emit event.
            let handle = app_handle.clone();
            tauri::async_runtime::spawn(async move {
                match poll_health(port, 30).await {
                    Ok(()) => {
                        let _ = handle.emit("sidecar-ready", SidecarReadyPayload { port });
                    }
                    Err(e) => {
                        eprintln!("Sidecar health poll failed: {e}");
                    }
                }
            });
        }
        Err(e) => {
            eprintln!("Failed to spawn sidecar: {e}");
        }
    }
}

/// Read sidecar stdout/stderr and log it. Runs until the process terminates.
async fn drain_sidecar_events(mut rx: tokio::sync::mpsc::Receiver<CommandEvent>) {
    while let Some(event) = rx.recv().await {
        match event {
            CommandEvent::Stdout(line) => {
                println!("[sidecar] {}", String::from_utf8_lossy(&line));
            }
            CommandEvent::Stderr(line) => {
                eprintln!("[sidecar] {}", String::from_utf8_lossy(&line));
            }
            CommandEvent::Terminated(payload) => {
                eprintln!("Sidecar terminated: code={:?} signal={:?}", payload.code, payload.signal);
                break;
            }
            _ => {}
        }
    }
}

/// Tauri command: return the current sidecar port (0 if not yet assigned).
#[tauri::command]
fn get_sidecar_port(state: tauri::State<'_, Mutex<SidecarState>>) -> Option<u16> {
    state.lock().ok().map(|s| s.port).filter(|&p| p != 0)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .manage(Mutex::new(SidecarState {
            port: 0,
            child: None,
        }))
        .invoke_handler(tauri::generate_handler![get_sidecar_port])
        .setup(|app| {
            // Initialize updater plugin (desktop only).
            #[cfg(desktop)]
            app.handle().plugin(tauri_plugin_updater::Builder::new().build())?;

            spawn_sidecar(app.handle());
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    // Kill the sidecar gracefully when the app exits.
    app.run(|app_handle, event| {
        if let RunEvent::Exit = event {
            let child = {
                let state = app_handle.state::<Mutex<SidecarState>>();
                state.lock().ok().and_then(|mut s| s.child.take())
            };
            if let Some(child) = child {
                println!("Killing sidecar on app exit");
                let _ = child.kill();
            }
        }
    });
}
