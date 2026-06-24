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
                let mut backend_ok = false;
                loop {
                    if let Some(ok) = client.as_ref().and_then(|c| {
                        c.get("http://127.0.0.1:8765/api/health")
                            .timeout(Duration::from_millis(500))
                            .send().ok()
                            .map(|r| r.status().is_success())
                    }) {
                        if ok { backend_ok = true; break; }
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
                    if !backend_ok {
                        // Mostrar una pantalla de error en lugar de un blank
                        // page (que es lo que veria el usuario sin esto).
                        let html = error_page_html();
                        // Navegamos via data: URL para no requerir un
                        // archivo embebido extra. El URL es del mismo
                        // origen que el iframe interno, asi que window.
                        // location funciona sin CSP issues.
                        let js = format!(
                            "window.location.replace({});",
                            serde_json::to_string(&format!("data:text/html;charset=utf-8,{}", urlencode(&html))).unwrap_or_else(|_| "''".to_string())
                        );
                        let _ = win.eval(&js);
                    }
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

/// Devuelve la ruta APPDATA donde el backend escribe logs en frozen mode.
/// Coincide con `_user_data_home()` en `orion/config/__init__.py`.
fn appdata_log_path() -> String {
    #[cfg(windows)]
    {
        if let Ok(appdata) = std::env::var("APPDATA") {
            return format!("{}\\Orion\\logs\\orion.log", appdata);
        }
        if let Ok(local) = std::env::var("LOCALAPPDATA") {
            return format!("{}\\Orion\\logs\\orion.log", local);
        }
    }
    "logs/orion.log".to_string()
}

/// HTML embebido para la pantalla de error cuando el backend no arranca.
/// Self-contained: sin CSS externo ni JS de framework. Estilizado en linea
/// para que renderee identico sin importar el origen.
fn error_page_html() -> String {
    let log_path = appdata_log_path();
    // Usamos string raw (`r#"..."#`) para evitar escaping de comillas y backticks.
    format!(
        r##"<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Orion - Error de arranque</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; min-height: 100vh; display: grid; place-items: center;
    background: radial-gradient(circle at 30% 20%, #1a1d2e 0%, #0a0c14 60%);
    color: #e6e8ee; font-family: -apple-system, "Segoe UI", Roboto, system-ui, sans-serif;
    padding: 24px;
  }}
  .card {{
    max-width: 560px; width: 100%;
    background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
    border-radius: 14px; padding: 32px;
    box-shadow: 0 24px 60px rgba(0,0,0,0.4);
    backdrop-filter: blur(12px);
  }}
  .icon {{ font-size: 32px; margin-bottom: 8px; color: #ff6b6b; }}
  h1 {{ font-size: 18px; margin: 0 0 8px 0; font-weight: 500; }}
  p {{ font-size: 14px; line-height: 1.55; color: #a8acbb; margin: 0 0 12px 0; }}
  code {{
    background: rgba(255,255,255,0.06); padding: 2px 6px; border-radius: 4px;
    font-family: ui-monospace, "Cascadia Code", Consolas, monospace; font-size: 12px;
    word-break: break-all;
  }}
  .actions {{ display: flex; gap: 8px; margin-top: 20px; flex-wrap: wrap; }}
  button {{
    border: 1px solid rgba(255,255,255,0.1); background: rgba(255,255,255,0.04);
    color: #e6e8ee; font: inherit; font-size: 13px;
    padding: 8px 14px; border-radius: 8px; cursor: pointer;
    transition: background .15s ease;
  }}
  button:hover {{ background: rgba(255,255,255,0.08); }}
  button.primary {{ background: #5b8def; border-color: #5b8def; }}
  button.primary:hover {{ background: #6b9eff; }}
  ul {{ font-size: 13px; color: #a8acbb; padding-left: 18px; margin: 8px 0 16px 0; }}
  li {{ margin-bottom: 4px; }}
</style>
</head>
<body>
<div class="card">
  <div class="icon">!</div>
  <h1>El backend de Orion no respondio a tiempo</h1>
  <p>Despues de 30 segundos, el servicio local sigue sin contestar en
     <code>http://127.0.0.1:8765</code>. Suele ser una de estas causas:</p>
  <ul>
    <li>Otro programa ya usa el puerto 8765.</li>
    <li>Antivirus o firewall bloquearon a <code>orion-backend.exe</code>.</li>
    <li>Falta la API key de Gemini (raro: el wizard suele aparecer igual).</li>
    <li>Falta el <a href="https://aka.ms/vs/17/release/vc_redist.x64.exe" style="color:#5b8def">Microsoft Visual C++ Redistributable</a> (Windows).</li>
  </ul>
  <p>El log activo esta en:<br><code>{log_path}</code></p>
  <div class="actions">
    <button class="primary" onclick="location.reload()">Reintentar</button>
    <button onclick="window.location.href='https://aka.ms/vs/17/release/vc_redist.x64.exe'">Descargar VC++ Redist</button>
    <button onclick="window.location.href='https://github.com/Zero0889/Orion-AI/issues'">Reportar issue</button>
    <button onclick="window.close()">Cerrar</button>
  </div>
</div>
</body>
</html>"##,
        log_path = log_path
    )
}

/// URL-encode minimal para data: URIs. Reemplaza caracteres no-ASCII basicos
/// y los reservados (#, &, espacios).
fn urlencode(s: &str) -> String {
    let mut out = String::with_capacity(s.len() * 3);
    for b in s.bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' |
            b'-' | b'_' | b'.' | b'~' | b'/' | b':' |
            b'<' | b'>' | b'!' | b'"' | b'\'' | b'(' | b')' |
            b'{' | b'}' | b'[' | b']' | b';' | b',' | b'?' | b'=' |
            b'\n' => out.push(b as char),
            _ => out.push_str(&format!("%{:02X}", b)),
        }
    }
    out
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
