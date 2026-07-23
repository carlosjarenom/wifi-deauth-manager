# Prompt de Recreación: WiFi Deauth Manager

> **Contexto:** Tarea de universidad (ciberseguridad/redes). Basado en el tutorial de Matias Vergara / Granaje: *"Como apagar la musica del vecino"* (video en `~/Descargas/Proyecto interfaz/Video/...mp4`, transcripción en `~/Descargas/Proyecto interfaz/Video/transcripción/...txt`).
>
> **Objetivo:** App GUI (Linux-only, Arch Linux) que sustituya escribir comandos en terminal por una interfaz gráfica. Usa `aircrack-ng` (`airmon-ng`, `airodump-ng`, `aireplay-ng`) + `iw`. Requiere **sudo**.
>
> **Funcionalidades obligatorias:**
> 1. **Selector de interfaz WiFi** (lista interfaces compatibles con `iwconfig`/`iw dev`).
> 2. **Activar/desactivar modo monitor** (`airmon-ng start/stop`), con **reconexión automática a WiFi normal** al desactivar (`nmcli device wifi reconnect` + fallback `systemctl restart NetworkManager`).
> 3. **Escaneo de redes** (bandas 2.4/5GHz o todas):
>    - Parseo correcto de `airodump-ng`: columnas **BSSID(0) CH(2) PWR(3) ENC(9) ESSID(12+)**.
>    - **Deduplicación por BSSID**.
>    - **Agrupar por ESSID** (checkbox) — útil para redes con varios APs (ej. Deco Mesh).
>    - SSIDs ocultos → mostrar `<oculta>` (no basura tipo `[0K`).
>    - Sanitizado UTF-8 robusto (quitar bytes inválidos + control chars, mantener acentos/emojis).
> 4. **Escaneo focalizado de estaciones** (doble clic o botón "Enfocar"): `airodump-ng -c <CH> --bssid <BSSID> <iface>` → parsea tabla STATION (formato 13+ cols: STATION(0) AP(12)).
> 5. **Guardar nombres personalizados por BSSID/MAC** (persistente en `saved_targets.json`):
>    - Formato: `{"BSSID": {"name": "TV del vecino", "type": "AP|Estacion"}, ...}`
>    - Pestaña "Guardados" con formulario Guardar/Eliminar + tabla editable (clic para cargar).
>    - Los nombres aparecen automáticos en escaneos (columna NAME).
> 6. **Ataques de desautenticación**:
>    - Individual: `aireplay-ng --deauth 0 -a <BSSID> -c <STATION> <iface>`
>    - Masivo (todas las estaciones): `aireplay-ng --deauth 0 -a <BSSID> <iface>`
>    - Botón "Detener todo" (mata subprocesos).
>    - Combo "Selección rápida" con estaciones del escaneo focalizado.
> 7. **UX/UI (Tkinter nativo, tema `clam`)**:
>    - 5 pestañas: Configuración / Escaneo / Ataque / Guardados / Ayuda (Wiki).
>    - **Menú contextual (clic derecho)** en tablas: "Copiar BSSID/MAC", "Copiar NAME".
>    - Atajo **Ctrl+Shift+C** → copia BSSID/MAC de fila seleccionada.
>    - Log inferior con timestamps.
>    - Wiki integrada en español: conceptos (BSSID, ESSID, MAC, Canal, PWR, ENC, Modo Monitor, Deauth), guía de uso por pestaña, troubleshooting, aviso legal.
> 8. **Manejo de errores robusto**:
>    - `subprocess` con `encoding='utf-8', errors='ignore'`.
>    - `UnicodeDecodeError` → `errors='ignore'`.
>    - `TclError -foreground` → mover `foreground` al constructor del widget.
>    - `airmon-ng check kill` antes de activar monitor.
>
> **Dependencias:** `aircrack-ng`, `iw`, `python3-tk` (Arch: `sudo pacman -S aircrack-ng iw tk`).
>
> **Ejecución:** `sudo python3 wifi_deauth_manager.py`
>
> **Estructura:** Un solo archivo `wifi_deauth_manager.py` (backend + GUI juntos) + `saved_targets.json` (auto-creado) + `README.md`.
>
> **Datos de prueba reales (Carlos, 13/06):**
> - Monitor: `wlan0mon`
> - Red objetivo: SSID oculto (Deco Mesh TP-Link Jazztel)
> - BSSIDs visibles: `CC:BA:BD:87:3D:47` (CH2), `CC:BA:BD:87:3D:9F` (CH2), `CC:BA:BD:87:3D:43` (CH3)
> - BSSID vecino: `50:0F:F5:E5:95:AC` (CH2)
> - Target estación: Redmi Note 10 → `1A:08:08:D9:E8:C8` (5GHz)
>
> **Bugs conocidos pendientes (13/06):**
> - SSID oculto a veces muestra `[0K` en lugar de `<oculta>` (fix regex aplicado, pendiente test).
> - Columna PWR muestra 0 → posible mapeo incorrecto de columna.
> - Debug intentado en `/tmp/airodump_debug.txt` (edit falló por texto no único).

---

*Guardado el 2026-07-23 02:01 GMT+2 desde sesión webchat*