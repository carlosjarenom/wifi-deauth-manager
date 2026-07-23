#!/usr/bin/env bash
# install.sh — Instala la integración de escritorio (.desktop + polkit + icono)
#               a nivel de usuario (~/.local/) para un wifi-deauth-manager que
#               ya está disponible como /usr/bin/wifi-deauth-manager.
#
# Este script NO compila código: presupone que ya has instalado
# wifi-deauth-manager por uno de:
#   * pip install --user wifi-deauth-manager     (cualquier distro con pipx/pip)
#   * sudo pacman -S wifi-deauth-manager        (Arch, usando el PKGBUILD local)
#   * sudo dpkg -i wifi-deauth-manager_*.deb    (Debian/Ubuntu/Kali)
#   * sudo dnf install wifi-deauth-manager      (Fedora/RHEL/CentOS via .rpm)
# Si /usr/bin/wifi-deauth-manager no existe, este script aborta y te dice cómo
# instalarlo primero. Esto evita drift entre el ejecutable "real" y los
# archivos de integración.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

err()  { printf '\033[31merror\033[0m: %s\n' "$*" >&2 ; }
ok()   { printf '\033[32mok\033[0m:    %s\n' "$*" ; }
info() { printf '\033[36minfo\033[0m:   %s\n' "$*" ; }

if [[ "${1:-}" == "--uninstall" ]]; then
    info "Uninstall: limpiando ~/.local/"
    rm -f "$HOME/.local/share/applications/wifi-deauth-manager.desktop"
    rm -f "$HOME/.local/share/icons/hicolor/scalable/apps/wifi-deauth-manager.svg"
    rm -f "$HOME/.local/share/polkit-1/actions/com.wifi-deauth-manager.policy"
    command -v update-desktop-database >/dev/null 2>&1 \
        && update-desktop-database "$HOME/.local/share/applications" || true
    command -v gtk-update-icon-cache     >/dev/null 2>&1 \
        && gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" || true
    ok "Archivos eliminados. El binario /usr/bin/wifi-deauth-manager NO se desinstala (usa pip uninstall o tu gestor de paquetes)."
    exit 0
fi

if ! command -v wifi-deauth-manager >/dev/null 2>&1; then
    err "/usr/bin/wifi-deauth-manager no se encuentra en PATH."
    err "Instálalo primero con UNA de:"
    err "  pipx install wifi-deauth-manager"
    err "  pip install --user wifi-deauth-manager"
    err "  makepkg -si  (dentro de este repo)"
    err "  sudo dpkg -i ./wifi-deauth-manager_*.deb"
    err "  sudo dnf install ./wifi-deauth-manager-*.rpm"
    exit 1
fi

mkdir -p "$HOME/.local/share/applications"
mkdir -p "$HOME/.local/share/icons/hicolor/scalable/apps"
mkdir -p "$HOME/.local/share/polkit-1/actions"

install -m 0644 "$PROJECT_DIR/wifi-deauth-manager.desktop" \
    "$HOME/.local/share/applications/wifi-deauth-manager.desktop"
ok "instalado .desktop → ~/.local/share/applications/"

install -m 0644 "$PROJECT_DIR/com.wifi-deauth-manager.policy" \
    "$HOME/.local/share/polkit-1/actions/com.wifi-deauth-manager.policy"
ok "instalado polkit → ~/.local/share/polkit-1/actions/"

install -m 0644 "$PROJECT_DIR/wifi-deauth-manager.svg" \
    "$HOME/.local/share/icons/hicolor/scalable/apps/wifi-deauth-manager.svg"
ok "instalado icono → ~/.local/share/icons/hicolor/scalable/apps/"

command -v update-desktop-database >/dev/null 2>&1 \
    && { update-desktop-database "$HOME/.local/share/applications"; ok "desktop database refreshed"; } \
    || info "update-desktop-database ausente, saltando."

command -v gtk-update-icon-cache >/dev/null 2>&1 \
    && { gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor"; ok "icon cache refreshed"; } \
    || info "gtk-update-icon-cache ausente, saltando."

command -v xmllint >/dev/null 2>&1 && {
    xmllint --noout "$HOME/.local/share/polkit-1/actions/com.wifi-deauth-manager.policy" \
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
info "Para desinstalar la integración: ./install.sh --uninstall"
echo "Para desinstalar también el binario: pipx uninstall / pip uninstall / pacman -Rns / apt remove / dnf remove"
