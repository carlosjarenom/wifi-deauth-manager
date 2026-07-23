#!/usr/bin/env bash
# WiFi Deauth Manager — privileged launcher (instalado en /usr/bin por
# el PKGBUILD y por el console_script que crea `pip install`).
# Invocado por polkit's pkexec desde:
#   /usr/share/applications/wifi-deauth-manager.desktop
# Esta capa existe para:
#   1. Reconstruir dinámicamente HOME y XAUTHORITY del usuario real (no root),
#      resolviendo $PKEXEC_UID → /home/<user> mediante getent passwd.
#      Evita rutas hardcoded tipo /home/<user>/... para que el paquete
#      funcione en cualquier máquina, sin asumir un usuario concreto.
#      NOTA: el script Python también implementa `_resolve_pkexec_user()` al
#      cargar el módulo. Defensa en profundidad: si lanzas el binario sin este
#      wrapper (p.ej. `sudo python3 wifi_deauth_manager.py` directo),
#      la resolución sigue funcionando desde Python.
#   2. Garantizar que DISPLAY y DBUS_SESSION_BUS_ADDRESS sobrevivan al
#      filtro de entorno de pkexec.
#   3. Apuntar a una ruta FHS estable (/usr/bin/wifi-deauth-manager) que
#      coincide con la anotación org.freedesktop.policykit.exec.path del
#      .policy — así polkit autoriza el binario correcto.
set -euo pipefail

# Propagar entorno gráfico del usuario que invoca el icono.
export DISPLAY="${DISPLAY:-:0}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-}"

# Resolver el usuario real a partir del UID preservado por polkit.
# getent respeta NSS (LDAP/SSSD) además de /etc/passwd.
if [ -n "${PKEXEC_UID:-}" ]; then
    REAL_HOME="$(getent passwd "$PKEXEC_UID" | cut -d: -f6 || true)"
    if [ -n "$REAL_HOME" ] && [ -d "$REAL_HOME" ]; then
        export HOME="$REAL_HOME"
        if [ -z "${XAUTHORITY:-}" ] && [ -f "$REAL_HOME/.Xauthority" ]; then
            export XAUTHORITY="$REAL_HOME/.Xauthority"
        fi
    fi
fi

# Fallback final de XAUTHORITY; en Wayland no se usa.
export XAUTHORITY="${XAUTHORITY:-/root/.Xauthority}"

# Ruta FHS estable (definida en PKGBUILD). Usa `env` para respetar el
# provides=python del paquete y permitir múltiples versiones del intérprete.
exec /usr/bin/env python3 /usr/share/wifi-deauth-manager/wifi_deauth_manager.py "$@"
