# Configurar Google OAuth para Orion (Gmail / Classroom / Drive / etc.)

Esta guía se hace **una sola vez por instalación**. Cubre desde un repo
recién clonado hasta tener Gmail + Classroom funcionando en el panel de
notificaciones.

> **¿Cuándo necesitás hacerla?**
> - Primera vez que instalás Orion.
> - Si en los logs ves `deleted_client`, `invalid_client` o
>   `The OAuth client was deleted.` — significa que el cliente OAuth
>   asociado fue borrado en Google Cloud Console y hay que crear uno
>   nuevo.

---

## 1 · Crear el proyecto y el cliente OAuth en GCP

Orion usa el CLI [`gog`](https://github.com/rclone/gog) (incluido en
`tools/gog/`) para hablar con las APIs de Google. Necesita un **OAuth
Client ID de tipo Desktop** y los scopes habilitados para los servicios
que vas a usar.

### 1.1 Crear el proyecto (si no tenés uno)

1. Abrí <https://console.cloud.google.com/>.
2. Arriba a la izquierda, **Select a project** → **NEW PROJECT**.
3. Nombre: `Orion` (o el que quieras). Sin organización.
4. **CREATE**.

### 1.2 Habilitar las APIs

En el menú lateral: **APIs & Services → Library**. Buscá y habilitá:

- **Gmail API**
- **Google Classroom API**
- **Google Drive API**
- **Google Calendar API**
- **Google Sheets API**
- **Google Docs API**
- **Google Slides API**
- **People API** (contactos)
- **Tasks API**
- **YouTube Data API v3** (opcional, solo si usás el adapter de YouTube)

> Podés habilitar solo las que te interesen. Las que no habilites
> simplemente devolverán 403 cuando Orion las invoque.

### 1.3 Configurar la pantalla de consentimiento (OAuth consent screen)

**APIs & Services → OAuth consent screen**:

1. **User Type**: `External` (a menos que tengas Google Workspace).
2. **App information**:
   - App name: `Orion`
   - User support email: tu mail
   - Developer contact: tu mail
3. **Scopes**: dejar vacío en este paso — `gog` pide los scopes en
   runtime cuando autorizás cada servicio. Saltear con **SAVE AND CONTINUE**.
4. **Test users**: agregá tu propio mail (el que vas a usar con Orion).
   Mientras la app esté en modo **Testing**, solo los emails de esta
   lista pueden autorizar.
5. **SAVE AND CONTINUE** → **BACK TO DASHBOARD**.

> No hace falta publicar la app (review de Google) si la usás vos solo.
> En modo Testing los refresh tokens caducan a los 7 días — es molesto
> pero suficiente para uso personal. Para extender a 6 meses, publicá
> la app eligiendo "In production" sin pedir verificación de scopes
> sensibles si no los usás.

### 1.4 Crear el Client ID OAuth

**APIs & Services → Credentials → + CREATE CREDENTIALS → OAuth client ID**:

1. **Application type**: **Desktop app**.
2. **Name**: `Orion Desktop` (o lo que quieras).
3. **CREATE**.
4. En el modal de "OAuth client created", **DOWNLOAD JSON**.

El archivo descargado se llama algo como
`client_secret_xxxxx.apps.googleusercontent.com.json`.

---

## 2 · Instalar el client en `gog`

1. Renombrá el JSON a `client_secret.json` y copialo a
   `tools/gog/client_secret.json` (sobreescribiendo el viejo si existe).

   ```powershell
   Copy-Item ~/Downloads/client_secret_*.json tools/gog/client_secret.json -Force
   ```

2. Registralo en `gog`:

   ```powershell
   ./tools/gog/gog.exe auth credentials set tools/gog/client_secret.json
   ```

   Esto guarda las credenciales del cliente en
   `%APPDATA%\gogcli\config.json`.

3. (Opcional) Verificá:

   ```powershell
   ./tools/gog/gog.exe auth credentials list
   ```

---

## 3 · Autorizar tu cuenta

Tenés dos formas — la GUI es la recomendada.

### 3a · Desde la UI de Orion (recomendado)

1. Abrí Orion (`orion.bat` o el instalador).
2. Sidebar → **Ajustes** → card **Cuentas de Google**.
3. **+ Agregar cuenta**.
4. Se abre el browser con la pantalla de Google. Elegí la cuenta,
   aceptá los scopes.
5. Vuelve a Orion y aparece la cuenta con sus servicios listados.

### 3b · Desde la terminal (fallback)

```powershell
./tools/gog/gog.exe auth add tu-email@gmail.com
```

Abre el browser, autorizás, vuelve a la terminal con "success".

---

## 4 · Verificar que todo funciona

```powershell
# Listar mails no leídos
./tools/gog/gog.exe -a tu-email@gmail.com gmail thread list --label-ids UNREAD --max-results 5

# Listar cursos de Classroom
./tools/gog/gog.exe -a tu-email@gmail.com classroom course list
```

Si los dos comandos devuelven datos JSON, el panel de **Notificaciones**
de Orion va a empezar a poblarse automáticamente (poll cada 60s por
default).

---

## 5 · Errores comunes

| Mensaje en logs / UI | Causa | Fix |
|---|---|---|
| `deleted_client: The OAuth client was deleted.` | Borraste el Client ID en GCP. | Volvé al paso **1.4** + **2**: nuevo client, sobreescribí `client_secret.json`, re-corré `auth credentials set`, re-autorizá la cuenta. |
| `invalid_client` | El `client_secret.json` no coincide con el client registrado en GCP. | Idem arriba: bajá el JSON correcto. |
| `access_denied` durante el flow | Tu mail no está en **Test users** (paso 1.3.4). | Agregalo y reintentá. |
| `The refresh token is invalid` después de 7 días | App en modo Testing — los tokens caducan. | Re-autorizá con `gog auth add` o publicá la app a "In production". |
| `Classroom sin token. Autorizá una vez...` | Cuenta existe pero ese servicio puntual no está autorizado. | En la card de la cuenta, click **+ Servicio** → `classroom` → autorizar. |

---

## 6 · Rotar credenciales (si las expusiste)

Si en algún momento commiteaste o compartiste el `client_secret.json`:

1. **APIs & Services → Credentials**.
2. Click el client comprometido → **DELETE**.
3. Volvé al paso **1.4** y creá uno nuevo.

> Los `client_secret` de "Desktop app" no son secretos críticos por
> diseño (van embebidos en binarios), pero combinados con un refresh
> token sí dan acceso. Si rotaste el client, los refresh tokens viejos
> mueren con él.
