#!/usr/bin/env bash
# install.sh — Instala la integración de escritorio (.desktop + polkit + icono)
#               a nivel de usuario (~/.local/) para un wifi-deauth-manager que
#               ya está disponible como /usr/bin/wifi-deauth-manager.
#
# Este script NO compila código: presupone que ya has instalado
# wifi-deauth-manager por uno de:
#   * pip install --user wifi-deauth-manager     (cualquier distro con pipx/pip)
#   * sudo pacman -S wifi-deauth-manager        (Arch, usando el PKGBUILD local)
#   * sudo dpkg -i wifi-deauth-manager_*.deb    (Debian/Ubuntu)
# Si /usr/bin/wifi-deauth-manager no existe, este script aborta y te dice cómo
# instalarlo primero. Esto evita drift entre el ejecutable "real" y los
# archivos de integración.
set -euo pipefail

# === Localizar proyecto + usuario invocante =================================
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
INVOKING_USER="${SUDO_USER:-$(logname 2>/dev/null || whoami)}"

err()  { printf '\033[31merror\033[0m: %s\n' "$*" >&2 ; }
ok()   { printf '\033[32mok\033[0m:    %s\n' "$*" ; }
info() { printf '\033[36minfo\033[0m:   %s\n' "$*" ; }

# === Uninstall ==============================================================
if [[ "${1:-}" == "--uninstall" ]]; then
    info "Uninstall: limpiando ~/.local/"
    rm -f "$HOME/.local/share/applications/wifi-deauth-manager.desktop"
    rm -f "$HOME/.local/share/icons/hicolor/scalable/apps/wifi-deauth-manager.svg"
    rm -f "$HOME/.local/share/polkit-1/actions/com.freebuff.wifi-deauth-manager.policy"
    command -v update-desktop-database >/dev/null 2>&1 \
        && update-desktop-database "$HOME/.local/share/applications" || true
    command -v gtk-update-icon-cache     >/dev/null 2>&1 \
        && gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" || true
    ok "Archivos eliminados. El binario /usr/bin/wifi-deauth-manager NO se desinstala (usa pip uninstall o tu gestor de paquetes)."
    exit 0
fi

# === Preflight: binario disponible? =========================================
if ! command -v wifi-deauth-manager >/dev/null 2>&1; then
    err "/usr/bin/wifi-deauth-manager no se encuentra en PATH."
    err "Instálalo primero con UNA de:"
    err "  pipx install wifi-deauth-manager"
    err "  pip install --user wifi-deauth-manager"
    err "  makepkg -si  (dentro de este repo)"
    err "  sudo dpkg -i ./wifi-deauth-manager_*.deb"
    exit 1
fi

# === Crear directorios XDG ===================================================
mkdir -p "$HOME/.local/share/applications"
mkdir -p "$HOME/.local/share/icons/hicolor/scalable/apps"
mkdir -p "$HOME/.local/share/polkit-1/actions"

# === Copiar archivos de integración ==========================================
install -m 0644 "$PROJECT_DIR/wifi-deauth-manager.desktop" \
    "$HOME/.local/share/applications/wifi-deauth-manager.desktop"
ok "instalado .desktop → ~/.local/share/applications/"

install -m 0644 "$PROJECT_DIR/com.freebuff.wifi-deauth-manager.policy" \
    "$HOME/.local/share/polkit-1/actions/com.freebuff.wifi-deauth-manager.policy"
ok "instalado polkit → ~/.local/share/polkit-1/actions/"

install -m 0644 "$PROJECT_DIR/wifi-deauth-manager.svg" \
    "$HOME/.local/share/icons/hicolor/scalable/apps/wifi-deauth-manager.svg"
ok "instalado icono → ~/.local/share/icons/hicolor/scalable/apps/"

# === Refrescar cachés (best-effort) ==========================================
command -v update-desktop-database >/dev/null 2>&1 \
    && { update-desktop-database "$HOME/.local/share/applications"; ok "desktop database refreshed"; } \
    || info "update-desktop-database ausente, saltando."

command -v gtk-update-icon-cache >/dev/null 2>&1 \
    && { gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor"; ok "icon cache refreshed"; } \
    || info "gtk-update-icon-cache ausente, saltando."

# === Validación (best-effort) =================================================
command -v xmllint >/dev/null 2>&1 && {
    xmllint --noout "$HOME/.local/share/polkit-1/actions/com.freebuff.wifi-deauth-manager.policy" \
        && ok "polkit policy XML parse OK"
}
command -v desktop-file-validate >/dev/null 2>&1 && {
    desktop-file-validate "$HOME/.local/share/applications/wifi-deauth-manager.desktop" \
        && ok ".desktop file validates"
}

echo
ok "Integración instalada."
echo
info "Próximos pasos:"
echo "  1. Abre el menú de aplicaciones y busca WiFi Deauth Manager."
echo "  2. Click → polkit pide contraseña → GUI se lanza con permisos root."
echo
info "Para desinstalar la integración:"
echo "  ./install.sh --uninstall"
echo
info "Para desinstalar también el binario:"
echo "  pipx uninstall wifi-deauth-manager   # si instalaste con pipx"
echo "  pip uninstall wifi-deauth-manager    # si con pip --user"
echo "  sudo pacman -Rns wifi-deauth-manager # si con makepkg -si / AUR"
echo "  sudo apt remove wifi-deauth-manager  # si con dpkg"
