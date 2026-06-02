// Prevents additional console window on Windows in release.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

//! Tauri shell de O.R.I.O.N (Fase 6).
//!
//! Diseño
//! ------
//! - Spawnea ``orion-backend`` (sidecar PyInstaller) al iniciar la app.
//! - El backend escucha en ``127.0.0.1:8765`` y sirve la UI React +
//!   ``/api/*`` + ``/ws``.
//! - La ventana Tauri navega a ``http://127.0.0.1:8765`` (declarado en
//!   ``tauri.conf.json``).
//! - Espera a que ``/api/health`` responda antes de mostrar la ventana
//!   (evita el flash blanco mientras uvicorn está arrancando).
//! - Al cerrar la app, el sidecar se mata via su ``CommandChild``.
//!
//! Sidecar: el binario debe llamarse ``orion-backend-<target-triple>``
//! (p.ej. ``orion-backend-x86_64-pc-windows-msvc.exe``). Lo coloca el
//! script de build en ``src-tauri/binaries/`` antes de ``cargo tauri build``.

use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use tauri::api::process::{Command, CommandChild, CommandEvent};
use tauri::{Manager, RunEvent, WindowEvent};

/// Handle al proceso sidecar, compartido entre setup y on_event.
struct SidecarHandle(Arc<Mutex<Option<CommandChild>>>);

fn main() {
    let handle: SidecarHandle = SidecarHandle(Arc::new(Mutex::new(None)));
    let handle_for_event = handle.0.clone();

    tauri::Builder::default()
        .manage(handle)
        .setup(|app| {
            let app_handle = app.handle();
            let sidecar = app.state::<SidecarHandle>().0.clone();

            // Evitar que el backend abra el navegador del sistema:
            // Tauri ya muestra la UI en su propia ventana embebida.
            // El backend hereda esta var de entorno al spawnearse.
            std::env::set_var("ORION_NO_BROWSER", "1");

            // Lanzar el backend.
            let (mut rx, child) = Command::new_sidecar("orion-backend")
                .expect("orion-backend sidecar no encontrado en binaries/")
                .args(["--web"])
                .spawn()
                .expect("No se pudo arrancar orion-backend");

            *sidecar.lock().unwrap() = Some(child);

            // Reenviar logs del backend a la consola de Tauri en debug.
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(line) | CommandEvent::Stderr(line) => {
                            eprintln!("[backend] {}", line);
                        }
                        CommandEvent::Terminated(payload) => {
                            eprintln!("[backend] terminated: code={:?}", payload.code);
                            break;
                        }
                        _ => {}
                    }
                }
            });

            // Esperar a /api/health (máx 30s) antes de mostrar la ventana.
            let app_for_wait = app_handle.clone();
            tauri::async_runtime::spawn(async move {
                let deadline = Instant::now() + Duration::from_secs(30);
                let client = reqwest_blocking();
                loop {
                    if let Some(ok) = client.as_ref().and_then(|c| {
                        c.get("http://127.0.0.1:8765/api/health")
                            .timeout(Duration::from_millis(500))
                            .send().ok()
                            .map(|r| r.status().is_success())
                    }) {
                        if ok { break; }
                    }
                    if Instant::now() > deadline {
                        eprintln!("[orion] backend no respondio en 30s");
                        break;
                    }
                    std::thread::sleep(Duration::from_millis(200));
                }
                if let Some(win) = app_for_wait.get_window("main") {
                    let _ = win.show();
                    let _ = win.set_focus();
                }
            });

            // La ventana arranca oculta y se muestra cuando el backend responde.
            if let Some(win) = app_handle.get_window("main") {
                let _ = win.hide();
            }

            Ok(())
        })
        .on_window_event(move |event| {
            if let WindowEvent::CloseRequested { .. } = event.event() {
                kill_sidecar(&handle_for_event);
            }
        })
        .build(tauri::generate_context!())
        .expect("error mientras se ejecutaba Orion")
        .run(|_app_handle, event| {
            if let RunEvent::ExitRequested { .. } = event {
                // ya manejado en CloseRequested, pero por si acaso:
                // nada extra que limpiar.
            }
        });
}

/// Mata el sidecar si sigue vivo.
fn kill_sidecar(handle: &Arc<Mutex<Option<CommandChild>>>) {
    if let Ok(mut guard) = handle.lock() {
        if let Some(child) = guard.take() {
            let _ = child.kill();
        }
    }
}

/// Devuelve un cliente HTTP minimal sin añadir dep nueva: usamos la
/// API blocking de tauri::api::http si está disponible, o un fallback
/// con TcpStream. Para mantener el scaffold simple, intentamos
/// ``reqwest`` solo si el usuario lo añade; si no, hacemos un check
/// TCP plano.
fn reqwest_blocking() -> Option<DummyClient> {
    Some(DummyClient {})
}

/// Cliente mínimo que solo expone ``get(url).send()``. Hace un TCP
/// connect a 127.0.0.1:8765 y considera "ok" si el puerto está
/// escuchando. Es suficiente para nuestro health-check; no parseamos el
/// HTTP. Esto evita añadir reqwest como dependencia.
struct DummyClient {}
struct DummyRequest {
    timeout: Duration,
}
struct DummyResponse {
    ok: bool,
}
impl DummyClient {
    fn get(&self, _url: &str) -> DummyRequest {
        DummyRequest { timeout: Duration::from_millis(500) }
    }
}
impl DummyRequest {
    fn timeout(mut self, t: Duration) -> Self { self.timeout = t; self }
    fn send(self) -> Result<DummyResponse, std::io::Error> {
        use std::net::{SocketAddr, TcpStream};
        let addr: SocketAddr = "127.0.0.1:8765".parse().unwrap();
        match TcpStream::connect_timeout(&addr, self.timeout) {
            Ok(_) => Ok(DummyResponse { ok: true }),
            Err(e) => Err(e),
        }
    }
}
impl DummyResponse {
    fn status(&self) -> DummyStatus { DummyStatus { ok: self.ok } }
}
struct DummyStatus { ok: bool }
impl DummyStatus {
    fn is_success(&self) -> bool { self.ok }
}
