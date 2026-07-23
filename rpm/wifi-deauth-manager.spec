# RPM spec for WiFi Deauth Manager
# Build: rpmbuild -ba rpm/wifi-deauth-manager.spec
# Tag-based release: Source0 = GitHub tarball matching %{version}.

%global github_owner carlosjarenom
%global github_repo  wifi-deauth-manager
%global version      1.0.0
%global release      1

Name:           wifi-deauth-manager
Version:        %{version}
Release:        %{release}%{?dist}
Summary:        Editorial PySide6/Qt6 GUI for local pentesting with aircrack-ng
License:        GPL-2.0-or-later
URL:            https://github.com/%{github_owner}/%{github_repo}
Source0:        %{url}/archive/v%{version}/%{name}-%{version}.tar.gz

BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  python3-pip
BuildRequires:  python3-setuptools
BuildRequires:  pyproject-rpm-macros >= 1.0
BuildRequires:  systemd
BuildRequires:  desktop-file-utils

Requires:       python3-pyside6
Requires:       python3-platformdirs
Requires:       aircrack-ng
Requires:       iw
Requires:       polkit

Recommends:     inter-fonts
Recommends:     jetbrains-mono-fonts
Suggests:       wireless-regdb

%description
Editorial PySide6/Qt6 GUI that wraps aircrack-ng (airmon-ng, airodump-ng,
aireplay-ng) with monitoring, focused scanning, JSON/CSV export, OUI
vendor lookup and channel overlap analysis. Uses pkexec via polkit for
monitor-mode elevation and persists target names via XDG Base Directory
(platformdirs).

Use this tool ONLY on networks you own or have explicit authorization
to audit. Active attacks against third-party networks are illegal.

%prep
%autosetup -n %{name}-%{version}

%build
%pyproject_build

%install
%pyproject_install

# Mover wifi_deauth_manager.py desde dist-packages (varía por Python) a
# /usr/share/wifi-deauth-manager/ — el wrapper en /usr/bin/wifi-deauth-manager
# (instalado más abajo) espera este path FHS-stable, igual que el PKGBUILD
# de Arch y el .deb de Debian.
PYLIB=$(python3 -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
mkdir -p %{buildroot}%{_datadir}/%{name}
if [ -f "%{buildroot}${PYLIB}/wifi_deauth_manager.py" ]; then
    mv "%{buildroot}${PYLIB}/wifi_deauth_manager.py" \
       %{buildroot}%{_datadir}/%{name}/wifi_deauth_manager.py
fi

# Wrapper bash en /usr/bin/wifi-deauth-manager (root:root 0755 para polkit).
install -Dm755 wifi-deauth-manager-launcher.sh \
    %{buildroot}%{_bindir}/%{name}

# .desktop (freedesktop), .policy (polkit), SVG icon, LICENSE.
install -Dm644 wifi-deauth-manager.desktop \
    %{buildroot}%{_datadir}/applications/%{name}.desktop
install -Dm644 com.wifi-deauth-manager.policy \
    %{buildroot}%{_datadir}/polkit-1/actions/com.wifi-deauth-manager.policy
install -Dm644 wifi-deauth-manager.svg \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/%{name}.svg
install -Dm644 LICENSE %{buildroot}%{_licensedir}/%{name}/LICENSE

%post
%systemd_post() || :
if [ -x %{_bindir}/update-desktop-database ]; then
    update-desktop-database %{_datadir}/applications >/dev/null 2>&1 || :
fi
if [ -x %{_bindir}/gtk-update-icon-cache ]; then
    gtk-update-icon-cache -f -t %{_datadir}/icons/hicolor >/dev/null 2>&1 || :
fi

%postun
%systemd_postun() || :
if [ -x %{_bindir}/update-desktop-database ]; then
    update-desktop-database %{_datadir}/applications >/dev/null 2>&1 || :
fi
if [ -x %{_bindir}/gtk-update-icon-cache ]; then
    gtk-update-icon-cache -f -t %{_datadir}/icons/hicolor >/dev/null 2>&1 || :
fi

%files
%license %{_licensedir}/%{name}/LICENSE
%{_datadir}/%{name}/wifi_deauth_manager.py
%{_datadir}/applications/%{name}.desktop
%{_datadir}/polkit-1/actions/com.wifi-deauth-manager.policy
%{_datadir}/icons/hicolor/scalable/apps/%{name}.svg
%{_bindir}/%{name}

%changelog
* Thu Jul 23 2026 WiFi Deauth Manager Maintainers <noreply@wifi-deauth-manager.invalid> - 1.0.0-1
- Initial release: editorial PySide6 GUI for local aircrack-ng pentesting.
- Cross-distro install via pipx, Arch PKGBUILD, Debian .deb and Fedora .rpm.
- Polkit pkexec policy (auth_admin) for monitor-mode elevation.
