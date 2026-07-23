# Maintainer: Carlos Jareño <carlos@freebuff.com>
pkgname=wifi-deauth-manager
pkgver=1.0.0
pkgrel=1
pkgdesc="Consola editorial GUI de pentesting local para aircrack-ng (PySide6/Qt6)"
arch=('any')
url="https://github.com/carlosjarenom/wifi-deauth-manager"
license=('GPL3')
depends=('python' 'pyside6' 'aircrack-ng' 'iw' 'polkit')
optdepends=(
    'inter-font: tipografía editorial sugerida para la UI'
    'ttf-jetbrains-mono: tipografía monospace recomendada para datos de escaneo'
    'wireless-regdb: base de datos regulatoria para WLAN'
)
install=wifi-deauth-manager.install
source=(
    "wifi_deauth_manager.py"
    "wifi-deauth-manager-launcher.sh"
    "wifi-deauth-manager.desktop"
    "com.freebuff.wifi-deauth-manager.policy"
    "wifi-deauth-manager.svg"
    "LICENSE"
)
sha256sums=('83830e254c8402a150b97cb83d9caf7468ba7229cdf80aa67db025d184596c8f'
            '493996695aa9404032c2633dac7e181792867f1048730c5a73af8c764b983bac'
            '1cdb42c047cf81c953e0c9d54106384349fa35dfc861c9d4274a4d26bf73c453'
            'c9a1e4c35cfd560c2ef3cbda14cfbf9546442ce427fd2eca1a1b4b24e1b5b2af'
            '46b9bf105245aa2d7979cb8aa68c4af4c86ad56ba649ed479327b4391b847a8a'
            'e090e52c3d807b5e2c0348856d6548415acdc89066f0e628e1acaf8420331d2c')

# No hay paso de compilación: el proyecto es Python interpretado + un wrapper bash.
build() {
    return 0
}

package() {
    cd "$srcdir"

    # NOTA: `.desktop`, `.policy` e `icon` ya vienen neutrales del repo
    # (Exec=pkexec /usr/bin/wifi-deauth-manager, exec.path=/usr/bin/wifi-deauth-manager,
    # Icon=wifi-deauth-manager). Sin sed: install -Dm644 los copia tal cual.

    # 1) Script principal: código interpretado, sólo lectura.
    install -Dm644 "wifi_deauth_manager.py" \
        "$pkgdir/usr/share/$pkgname/wifi_deauth_manager.py"

    # 2) Console-script wrapper en /usr/bin para que `pkexec /usr/bin/wifi-deauth-manager`
    #    (usado por .desktop y polkit) y `wifi-deauth-manager` desde shell apunten al
    #    mismo binario. Propiedad root:root 0755 porque polkit lo invoca como root.
    install -Dm755 "wifi-deauth-manager-launcher.sh" \
        "$pkgdir/usr/bin/$pkgname"

    # 3) Política de Polkit (Exec apuntando a /usr/bin/wifi-deauth-manager).
    install -Dm644 "com.freebuff.wifi-deauth-manager.policy" \
        "$pkgdir/usr/share/polkit-1/actions/com.freebuff.$pkgname.policy"

    # 4) Entrada .desktop (Exec + Icon ya neutrales).
    install -Dm644 "wifi-deauth-manager.desktop" \
        "$pkgdir/usr/share/applications/$pkgname.desktop"

    # 5) Icono SVG bajo hicolor (compatibilidad universal con entornos).
    install -Dm644 "wifi-deauth-manager.svg" \
        "$pkgdir/usr/share/icons/hicolor/scalable/apps/$pkgname.svg"

    # 6) Licencia GPL3 instalada en /usr/share/licenses/$pkgname/ (cumple AUR).
    install -Dm644 "LICENSE" "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
