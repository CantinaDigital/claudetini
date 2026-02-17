/// Placeholder command for sidecar (not yet implemented)
#[tauri::command]
async fn start_sidecar() -> Result<u16, String> {
    // For now, return a mock port - the frontend will use mock data
    // when the backend is not available
    Err("Sidecar not available in development mode".to_string())
}

/// Placeholder command for sidecar
#[tauri::command]
async fn stop_sidecar() -> Result<(), String> {
    Ok(())
}

/// Get the current sidecar port
#[tauri::command]
fn get_sidecar_port() -> Option<u16> {
    None
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            start_sidecar,
            stop_sidecar,
            get_sidecar_port
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
