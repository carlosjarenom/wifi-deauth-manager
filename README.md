# WiFi Deauth Manager

> Consola editorial de pentesting local para `aircrack-ng` — sustituye los comandos de terminal por una GUI PySide6 con 8 temas curados y un wiki-guía integrado en español.

## Stack

- **GUI**: Python 3.12 · PySide6 / Qt6
- **Backend**: `airmon-ng`, `airodump-ng`, `aireplay-ng`, `iw`
- **Modelo UI**: editorial monocromo + 1 acento · 8 temas curados
- **Estado actual**: parser regex anclado a `airodump-ng` · 8 temas · wiki 12 secciones con sticky TOC · export JSON/CSV · channel overlap analyzer · OUI vendor lookup embebida (~610 prefixes)
- **Tamaño**: ~2.7 k líneas en un único archivo (backend + GUI + WIKI + OUI DB)

## 🚀 Instalación rápida

### Opción A — pipx (recomendada, distro-agnostic)
```bash
pipx install wifi-deauth-manager
# añade deps de sistema (aircrack-ng + iw):
#   Arch:   sudo pacman -S aircrack-ng iw
#   Debian: sudo apt install aircrack-ng iw
sudo wifi-deauth-manager        # o desde el menú de apps (polkit pedirá contraseña)
```

### Opción B — pip (--user o venv)
```bash
python3 -m pip install --user wifi-deauth-manager
sudo apt install aircrack-ng iw       # o: pacman -S aircrack-ng iw
sudo $(python3 -c 'import sys, pathlib; print(pathlib.Path(sys.prefix).parent / "bin" / "wifi-deauth-manager")')
```

### Opción C — Arch desde el PKGBUILD local
```bash
sudo pacman -S aircrack-ng iw python-pyside6 python-platformdirs
git clone https://github.com/carlosjarenom/wifi-deauth-manager
cd wifi-deauth-manager
makepkg -si                      # construye + instala como paquete del sistema
```

### Opción D — Debian / Ubuntu / Kali desde .deb (siguiente fase)
```bash
sudo apt install aircrack-ng iw python3-pyside6.qtgui python3-platformdirs
# Una vez publicado el .deb en GitHub Releases:
sudo dpkg -i wifi-deauth-manager_*.deb
```

### Tipografías editoriales (opcional pero recomendado)
```bash
# Arch
sudo pacman -S inter-font ttf-jetbrains-mono
# Debian / Ubuntu
sudo apt install fonts-inter fonts-jetbrains-mono
```
Sin ellas Qt6 cae a Cantarell + DejaVu (funcional pero menos cuidado).

### 📦 Aclaración sobre rutas de instalación

`pipx install wifi-deauth-manager` y `pip install --user` colocan el binario en `~/.local/bin/wifi-deauth-manager`, mientras que el `.desktop` y el `.policy` apuntan a `/usr/bin/wifi-deauth-manager`. Por tanto:

- **Opción A/B (pipx|pip --user)** → command-line funciona (`sudo wifi-deauth-manager`). El icono del menú **no aparecerá** hasta que enlaces el binario manualmente.
- **Opción C/D (PKGBUILD|.deb)** → integración completa con icono, polkit y .desktop listos.

Para activar el icono tras pipx/pip --user:

```bash
sudo ln -sf "$(which wifi-deauth-manager)" /usr/bin/wifi-deauth-manager
./install.sh   # despliega .desktop + .policy + icon en ~/.local/
```

## Uso

1. Lanza desde el menú de aplicaciones (busca "WiFi Deauth Manager"). Polkit te pide contraseña → tecleas y se eleva a root.
2. Pestaña **Cambio** → elige adaptador + activa modo monitor con `airmon-ng`.
3. Pestaña **Escaneo** → escaneo general (≈5 s) + filtrar por ESSID o por canal. Doble-click sobre un AP para enfocarlo.
4. Pestaña **Ataque** → deauth individual o masiva contra un AP / todas las estaciones. Bitácora con timestamps + export a `.txt`.

### Atajos de teclado

| Atajo  | Acción |
|--------|--------|
| `Ctrl+1..5` | Cambia a la pestaña 1–5 |
| `Ctrl+T` | Cicla al siguiente tema |
| `Ctrl+R` | (Escaneo) Relanza escaneo |
| `Ctrl+Q` | (Escaneo) Limpia filtro ESSID |
| `Ctrl+F` | (Ayuda) Enfoca la búsqueda lateral |

## 🛠 Desarrollo

```bash
git clone https://github.com/carlosjarenom/wifi-deauth-manager
cd wifi-deauth-manager
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Tests del parser airodump-ng
python3 -m pytest test_parser.py

# Smoke test headless (sin DISPLAY)
QT_QPA_PLATFORM=offscreen python3 -c "
import wifi_deauth_manager as w
from PySide6.QtWidgets import QApplication
import sys
app = QApplication(sys.argv)
win = w.MainWindow()
print('Themes:', list(w.THEMES.keys()))
print('WIKI_SECTIONS:', len(w.MainWindow.WIKI_SECTIONS))
print('OUI DB:', len(w.OUI_TO_VENDOR), 'prefixes')
"
```

## 🚨 Notas importantes

1. **Requiere root / sudo** — el modo monitor y la deauth necesitan `CAP_NET_ADMIN`. Por eso el `.desktop` invoca la app vía `pkexec` con `auth_admin`.
2. **No usar sin autorización** — los ataques contra redes ajenas son ilegales (España: CP arts. 197–264, LOPDGDD, Ley 9/2014). Esta herramienta es **exclusivamente para auditorías en redes propias**.
3. `saved_targets.json` se guarda en `~/.config/wifi-deauth-manager/` (XDG) — no se mete en el repo.
4. Botones Exportar / Analizar se desactivan automáticamente cuando no hay escaneo.
5. Si ejecutas la app con `pkexec` las exports se escriben como root; recuerda `chown` si quieres editarlas con tu usuario.

## Licencia

GPL-3.0-or-later — ver [`LICENSE`](LICENSE).

## Contribuir

PRs y bug reports bienvenidos en `https://github.com/carlosjarenom/wifi-deauth-manager/issues`.

---

Hecho con ☕ por Carlos Jareño · Freebuff.
