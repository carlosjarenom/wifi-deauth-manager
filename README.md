# WiFi Deauth Manager

> Editorial PySide6/Qt6 GUI for local pentesting with `aircrack-ng`
> — replaces CLI commands with a hand-curated GUI, 8 themes,
> an integrated 12-section Spanish wiki-guide and a focus-mode scanner.

[![License: GPL-2.0-or-later](https://img.shields.io/badge/License-GPL--2.0--or--later-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![Platform: Linux](https://img.shields.io/badge/platform-Linux-lightgrey.svg)](#-installation-matrix)

> ⚠️ **Solo para redes propias o con autorización explícita.** El uso contra redes ajenas es ilegal (España: CP arts. 197–264, LOPDGDD, Ley 9/2014).

## 🚀 Instalación rápida — pick your distro

| Familia | Instalación | Tiempo |
|---|---|---|
| **Arch / CachyOS / Manjaro** | `git clone … && cd … && makepkg -si` | 1 min |
| **Debian / Ubuntu / Kali / Mint / PopOS** | `sudo dpkg -i wifi-deauth-manager_*.deb` *(disponible en [Releases](https://github.com/carlosjarenom/wifi-deauth-manager/releases))* | 30 s |
| **Fedora / RHEL / CentOS / Nobara** | `sudo dnf install ./wifi-deauth-manager-*.rpm` *(id.)* | 30 s |
| **Cualquier distro** | `pipx install wifi-deauth-manager` *(solo CLI)* | 1 min |
| **Desarrollo** | `pip install -e ".[dev]"` | 1 min |

<details>
<summary><b>Opción A — pipx (recomendada, distro-agnostic)</b></summary>

```bash
pipx install wifi-deauth-manager
sudo apt install aircrack-ng iw       # o: sudo pacman -S / sudo dnf install
sudo wifi-deauth-manager               # o desde el menú de apps (polkit pedirá contraseña)
```

`pipx` deja el binario en `~/.local/bin/wifi-deauth-manager`. El icono del menú aparece solo si usas un instalador de sistema (Arch PKGBUILD, .deb, .rpm) o si enlazas manualmente:
```bash
sudo ln -sf "$(which wifi-deauth-manager)" /usr/bin/wifi-deauth-manager
./install.sh   # despliega .desktop + polkit + icon en ~/.local/
```

</details>

<details>
<summary><b>Opción B — Arch desde el PKGBUILD local</b></summary>

```bash
sudo pacman -S aircrack-ng iw python-pyside6 python-platformdirs
git clone https://github.com/carlosjarenom/wifi-deauth-manager
cd wifi-deauth-manager
makepkg -si                      # construye + instala como paquete del sistema
```

</details>

<details>
<summary><b>Opción C — Debian / Ubuntu / Kali desde .deb</b></summary>

```bash
sudo apt install aircrack-ng iw python3-pyside6 python3-platformdirs
wget https://github.com/carlosjarenom/wifi-deauth-manager/releases/download/v1.0.0/wifi-deauth-manager_1.0.0-1_all.deb
sudo dpkg -i wifi-deauth-manager_1.0.0-1_all.deb
```

`.deb` se compila automáticamente en CI al pushear tags `v*` (ver `.github/workflows/release.yml`).

</details>

<details>
<summary><b>Opción D — Fedora / RHEL / CentOS desde .rpm</b></summary>

```bash
sudo dnf install aircrack-ng iw python3-pyside6 python3-platformdirs
wget https://github.com/carlosjarenom/wifi-deauth-manager/releases/download/v1.0.0/wifi-deauth-manager-1.0.0-1.noarch.rpm
sudo dnf install ./wifi-deauth-manager-1.0.0-1.noarch.rpm
```

`.rpm` se compila con `rpmbuild` desde `rpm/wifi-deauth-manager.spec` en CI.

</details>

### Tipografías editoriales (opcional pero recomendado)

```bash
sudo pacman -S inter-font ttf-jetbrains-mono       # Arch
sudo apt install fonts-inter fonts-jetbrains-mono  # Debian / Ubuntu
sudo dnf install fonts-inter fonts-jetbrains-mono   # Fedora
```

Sin ellas Qt6 cae a Cantarell + DejaVu (funcional pero menos cuidado).

## 🧭 Tabla de características

| Pestaña        | Qué hace |
|----------------|----------|
| **Cambio**     | Selección de adaptador WiFi · activar/desactivar modo monitor con `airmon-ng` |
| **Escaneo**    | Escaneo general + filtrado por banda / ESSID · agrupador por ESSID · botón Exportar (JSON/CSV) · botón Analizar solapamiento 2.4 GHz · doble click para enfocar un AP |
| **Ataque**     | Deauth individual o masiva con selección rápida de estaciones · bitácora con timestamps · export a `.txt` |
| **Guardados**  | Nombres legibles por BSSID/MAC persistentes en `~/.config/wifi-deauth-manager/saved_targets.json` (XDG) |
| **Ayuda**      | Wiki-guía editorial: 12 secciones, sticky TOC, Ctrl+F para buscar, sello ATENCIÓN para secciones críticas |

### Atajos de teclado

| Atajo  | Acción |
|--------|--------|
| `Ctrl+1..5` | Cambia a la pestaña 1–5 |
| `Ctrl+T` | Cicla al siguiente tema |
| `Ctrl+R` | (Escaneo) Relanza escaneo |
| `Ctrl+Q` | (Escaneo) Limpia filtro ESSID |
| `Ctrl+F` | (Ayuda) Enfoca la búsqueda lateral |

### Temas editoriales (8)

`Papel → Static Ink (default) → Moderno → Olive Press → Sepia → Nordic → Slate → OLED`. Cada tema define 14 campos de palette (bg / surface / surface_alt / fg / fg_dim / accent / accent_dim / border / border_hi / danger / success / warn / sans / mono). No son variantes cream-on-cream: tienen huella visual propia.

## 🤔 ¿Por qué no usar Wifite / Bettercap?

**Wifite** ataca sin pausa usando heurísticas automáticas (WPA handshake → auto-crack con wordlist). Es ideal cuando solo quieres resultados.

**Bettercap** es un framework swiss-army (WiFi + BLE + HID) mucho más amplio pero menos editorial.

**WiFi Deauth Manager** está en el otro extremo: te deja *ver* lo que está pasando (parser con sticky TOC, OUI vendor realtime, channel-overlap analyzer, bitácora). Es para auditoría metódica, no para "fire-and-forget". Usa el script Python directo solo cuando quieras control total; usa Wifite si lo que quieres es automatizar.

## 🛠 Desarrollo

```bash
git clone https://github.com/carlosjarenom/wifi-deauth-manager
cd wifi-deauth-manager
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Tests del parser airodump-ng
python -m pytest test_parser.py -v

# Smoke test headless (sin DISPLAY)
QT_QPA_PLATFORM=offscreen python -c "
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

## 🤔 FAQ

**P: ¿Por qué GPL-2.0-or-later y no GPL-3?**
R: copyleft clásico (cualquier fork debe seguir siendo open-source) + familiar para la mayoría de proyectos de seguridad. `-or-later` permite a contribuidores futuros relicenciar a v3 si hace falta para interoperar.

**P: ¿Y si mi distro no está en la tabla?**
R: Cubre todo LinuxHF vía `pipx install wifi-deauth-manager`. macOS/Windows no funcionan porque `aircrack-ng` no soporta sus drivers WiFi en modo monitor.

**P: ¿Cómo puedo debuggear un crash?**
R: Lanza desde terminal con `sudo wifi-deauth-manager 2>&1 | tee /tmp/wdm-debug.log`. Adjunta el log en Issues.

**P: ¿Por qué `~/.local/` no es suficiente?**
R: El `install.sh` legacy despliega `.desktop` / `.policy` / `icon` a nivel de usuario, pero el binario debe existir en `/usr/bin/wifi-deauth-manager` antes. Por eso lo más limpio es usar el paquete de tu distro (PKGBUILD / .deb / .rpm) o `pipx install`.

## 🚨 Aviso legal

1. **Requiere `CAP_NET_ADMIN`** (root / sudo) — el modo monitor y la deauth lo necesitan. El `.desktop` invoca la app vía `pkexec` con `auth_admin`.
2. **Solo autoriza el uso en redes propias o con autorización explícita y por escrito.** Los ataques contra redes ajenas son ilegales en la mayoría de jurisdicciones.
3. `saved_targets.json` y los exports de scan se guardan en `~/.config/wifi-deauth-manager/` (XDG, via platformdirs).
4. Si ejecutas la app con pkexec las exports se escriben como root; recuerda `chown tu_usuario:tu_usuario archivo.json` si quieres editarlas con tu usuario.

## 📋 Distribución y empaquetado

| Formato | Carpeta / archivo | Generado por | Estado |
|---|---|---|---|
| Wheel + sdist (PyPI) | `pyproject.toml` | `python -m build` | ✅ |
| Arch `.pkg.tar.zst` | `PKGBUILD` | `makepkg -sf` | ✅ |
| Debian `.deb` | `debian/` | `dpkg-buildpackage -us -uc -b` | ✅ |
| Fedora `.rpm` | `rpm/wifi-deauth-manager.spec` | `rpmbuild -ba` | ✅ |
| GitHub Actions CI | `.github/workflows/release.yml` | push tag `v*` | ✅ |
| Arch User Repository (AUR) | — | — | ❌ fuera de scope |

## 📜 Licencia

**GPL-2.0-or-later** — ver [`LICENSE`](LICENSE). Eres libre de usar, modificar y redistribuir el código, pero **cualquier redistribución debe mantener la misma licencia copyleft**.

## 🤝 Contribuciones

PRs y bug reports bienvenidos en [GitHub Issues](https://github.com/carlosjarenom/wifi-deauth-manager/issues). Bug reports con `~/.config/wifi-deauth-manager/` + `sudo wifi-deauth-manager 2>&1 | tee /tmp/wdm.log` adjuntos suelen resolverse en horas.
