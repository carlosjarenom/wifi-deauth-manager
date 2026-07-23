# Maintainer: WiFi Deauth Manager Maintainers <noreply@wifi-deauth-manager.invalid>
pkgname=wifi-deauth-manager
pkgver=1.0.0
pkgrel=1
pkgdesc="Editorial PySide6/Qt6 GUI for local pentesting with aircrack-ng"
arch=('any')
url="https://github.com/carlosjarenom/wifi-deauth-manager"
license=('GPL2')
depends=('python' 'pyside6' 'aircrack-ng' 'iw' 'polkit')
optdepends=(
    'inter-font: editorial typography for the UI'
    'ttf-jetbrains-mono: monospace typography for scan data'
    'wireless-regdb: regulatory database for WLAN'
)
install=wifi-deauth-manager.install
source=(
    "wifi_deauth_manager.py"
    "wifi-deauth-manager-launcher.sh"
    "wifi-deauth-manager.desktop"
    "com.wifi-deauth-manager.policy"
    "wifi-deauth-manager.svg"
    "LICENSE"
)
sha256sums=('83830e254c8402a150b97cb83d9caf7468ba7229cdf80aa67db025d184596c8f'
            '493996695aa9404032c2633dac7e181792867f1048730c5a73af8c764b983bac'
            '1cdb42c047cf81c953e0c9d54106384349fa35dfc861c9d4274a4d26bf73c453'
            'c9a1e4c35cfd560c2ef3cbda14cfbf9546442ce427fd2eca1a1b4b24e1b5b2af'
            '46b9bf105245aa2d7979cb8aa68c4af4c86ad56ba649ed479327b4391b847a8a'
            '7e8903cad43095830e0697d258e24568aa9769d5df088adf8bbe9d58e35ac24f')

build() {
    return 0
}

package() {
    cd "$srcdir"

    # 1) Script principal: código interpretado, sólo lectura.
    install -Dm644 "wifi_deauth_manager.py" \
        "$pkgdir/usr/share/$pkgname/wifi_deauth_manager.py"

    # 2) Console-script wrapper en /usr/bin/wifi-deauth-manager (root:root 0755).
    install -Dm755 "wifi-deauth-manager-launcher.sh" \
        "$pkgdir/usr/bin/$pkgname"

    # 3) Política de Polkit (action ID: com.wifi-deauth-manager.run).
    install -Dm644 "com.wifi-deauth-manager.policy" \
        "$pkgdir/usr/share/polkit-1/actions/com.wifi-deauth-manager.policy"

    # 4) Entrada .desktop.
    install -Dm644 "wifi-deauth-manager.desktop" \
        "$pkgdir/usr/share/applications/$pkgname.desktop"

    # 5) Icono SVG bajo hicolor.
    install -Dm644 "wifi-deauth-manager.svg" \
        "$pkgdir/usr/share/icons/hicolor/scalable/apps/$pkgname.svg"

    # 6) Licencia GPL-2.0-or-later (cumple convenciones AUR/Debian/Fedora).
    install -Dm644 "LICENSE" "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
