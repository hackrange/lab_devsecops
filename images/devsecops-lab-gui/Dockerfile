# DevSecOps workstation lab, desktop edition.
#
# Same box as devsecops-lab, with an Xfce desktop served over RDP, for the
# lessons that need a browser: the lab package registry portal, the lab Git
# server, Grafana, Keycloak, the Kong manager, PortSwigger's hosted labs, and
# the local OWASP Juice Shop.
#
# WHY IT BUILDS FROM THE TERMINAL IMAGE
# The alternative was repeating the whole toolchain on top of debian:13-slim.
# That produces a second, unrelated 9GB stack, so a lab node that runs both
# variants carries about 18GB.  Building FROM devsecops-lab means the two
# images SHARE every toolchain layer: the desktop edition costs only its own
# delta (the desktop, the browser and the fonts) on disk, in the registry, and
# on every pull.  It also guarantees the two boxes carry identical tool
# versions, which repeating the install could never promise once an upstream
# release moved.  The price is a build order: devsecops-lab has to be built (or
# pulled) first, and rebuilding it means rebuilding this one too.  BASE is an
# ARG so a deploy can point it at the registry copy instead of a local tag.
#
# The session wiring follows the labs that already work over RDP here
# (analyst-lab, splunk-lab, kali-lab-gui): xrdp on 3389, xfce4-session as the
# session, and the stale X lock cleared at start.  Deliberately NOT the 'xorg'
# metapackage: xorgxrdp brings its own keyboard and mouse drivers, so
# xserver-xorg-core plus xfonts-base is the whole X server this needs.
#
# By course-owner instruction this image ships NO Burp Suite (it is a
# developer's desktop, not an attack box) and NO IDE; Mousepad is the graphical
# editor, and the command line editors are the ones the base image already
# configures.
#
# LOCAL LAB COPY: the hosted image's Dockerfile, with Visual Studio Code taken
# from Microsoft's repository for the processor it is built on (amd64 or
# arm64) rather than amd64 only.  Nothing else differs.
#
# Author: Tim Rice
ARG BASE=devsecops-lab:latest
FROM ${BASE}

ENV DEBIAN_FRONTEND=noninteractive

# The desktop, the browser, and all of their configuration, in one layer.  Every
# config file is written inline rather than copied, so the layer count stays at
# two (this RUN and the COPY below) and nothing is left behind to clean up in a
# later layer.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      xfce4-session xfwm4 xfdesktop4 xfce4-panel xfce4-settings xfce4-terminal \
      thunar mousepad \
      xrdp xorgxrdp xserver-xorg-core xauth xfonts-base x11-xserver-utils \
      dbus dbus-x11 \
      firefox-esr fonts-dejavu-core fonts-liberation2 \
      xdg-utils xclip; \
    \
    # Visual Studio Code, from Microsoft's own repository.
    #
    # The apt source is removed straight after the install, for the same reason
    # the Node one is: a lab reaches an allowlist and packages.microsoft.com is
    # not on it, so leaving the source behind would make every student's
    # `apt-get update` print a failure that has nothing to do with them.
    curl -fsSLo /tmp/ms.asc https://packages.microsoft.com/keys/microsoft.asc; \
    gpg --dearmor -o /usr/share/keyrings/microsoft.gpg /tmp/ms.asc; \
    # Microsoft publishes Code for amd64 and arm64 in the same repository, so
    # the Local Lab asks for whichever processor it is building on.
    printf 'deb [arch=%s signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/repos/code stable main\n' \
      "$(dpkg --print-architecture)" > /etc/apt/sources.list.d/vscode.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends code; \
    rm -f /etc/apt/sources.list.d/vscode.list /tmp/ms.asc; \
    \
    # ---- RDP session wiring -----------------------------------------------
    # xfce4-session (not startxfce4) is what xrdp expects, and what keeps the
    # panel and the settings daemon wired to the same session bus.
    printf 'xfce4-session\n' > /home/student/.xsession; \
    chown student:student /home/student/.xsession; \
    printf '#!/bin/sh\nexec xfce4-session\n' > /etc/xrdp/startwm.sh; \
    chmod +x /etc/xrdp/startwm.sh; \
    adduser xrdp ssl-cert 2>/dev/null || true; \
    mkdir -p /run/dbus /run/xrdp; \
    \
    # A lab desktop must never blank or lock.  The student never types the
    # password (the broker hands it to Guacamole), so a lock screen is an
    # unanswerable prompt and a support call.  Belt and braces: the autostart
    # entries go, and lab-desktop-setup turns the X blanker off at login too.
    rm -f /etc/xdg/autostart/xfce4-power-manager.desktop \
          /etc/xdg/autostart/xfce4-screensaver.desktop; \
    \
    # ---- Firefox: trust the lab CA in its own certificate store ------------
    # Firefox does not read /etc/ssl/certs; it carries an NSS database per
    # profile.  An enterprise policy installs the lab CA into whatever profile
    # the student ends up with, so https://labrepo.lab:8443 and
    # https://labgit.lab:8444 load clean instead of teaching the class to click
    # through a certificate warning.  DNS over HTTPS is turned off in the same
    # file: the lab hostnames live in /etc/hosts, and a browser that resolves
    # names through a public resolver would never find them.
    mkdir -p /etc/firefox/policies /etc/firefox-esr/policies \
             /usr/lib/firefox-esr/distribution /usr/lib/mozilla/certificates; \
    cp /usr/local/share/ca-certificates/lab-ca.crt /usr/lib/mozilla/certificates/lab-ca.crt; \
    printf '%s\n' \
      '{' \
      '  "policies": {' \
      '    "Certificates": {' \
      '      "ImportEnterpriseRoots": true,' \
      '      "Install": ["/usr/local/share/ca-certificates/lab-ca.crt", "lab-ca.crt"]' \
      '    },' \
      '    "DNSOverHTTPS": { "Enabled": false, "Locked": true },' \
      '    "Homepage": {' \
      '      "URL": "file:///opt/lab/start/index.html",' \
      '      "StartPage": "homepage"' \
      '    },' \
      '    "DisableTelemetry": true,' \
      '    "DisableFirefoxStudies": true,' \
      '    "DisablePocket": true,' \
      '    "DisableFirefoxAccounts": true,' \
      '    "DisableProfileImport": true,' \
      '    "DontCheckDefaultBrowser": true,' \
      '    "OverrideFirstRunPage": "",' \
      '    "OverridePostUpdatePage": "",' \
      '    "UserMessaging": { "WhatsNew": false, "ExtensionRecommendations": false,' \
      '      "FeatureRecommendations": false, "SkipOnboarding": true }' \
      '  }' \
      '}' > /usr/lib/firefox-esr/distribution/policies.json; \
    cp /usr/lib/firefox-esr/distribution/policies.json /etc/firefox/policies/policies.json; \
    cp /usr/lib/firefox-esr/distribution/policies.json /etc/firefox-esr/policies/policies.json; \
    \
    # ---- desktop defaults ---------------------------------------------------
    # Xfce Terminal as the terminal helper, so the panel button and Thunar's
    # "Open Terminal Here" launch it instead of asking which program to use.
    mkdir -p /etc/xdg/xfce4 /home/student/.config/xfce4 /home/student/Desktop /opt/lab/start; \
    printf 'TerminalEmulator=xfce4-terminal\n' > /etc/xdg/xfce4/helpers.rc; \
    cp /etc/xdg/xfce4/helpers.rc /home/student/.config/xfce4/helpers.rc; \
    \
    # Desktop launchers.  lab-desktop-setup pre-trusts these at login so a
    # double click runs them instead of raising an "untrusted launcher" prompt.
    launcher() { printf '%s\n' '[Desktop Entry]' 'Version=1.0' 'Type=Application' \
      "Name=$2" "Comment=$3" "Exec=$4" "Icon=$5" 'Terminal=false' "Categories=$6" \
      > "/home/student/Desktop/$1.desktop"; }; \
    launcher firefox 'Web Browser' 'The lab services, and the web' \
      'firefox-esr %u' 'firefox-esr' 'Network;WebBrowser;'; \
    launcher terminal 'Terminal' 'The same toolchain as the SSH lab' \
      'xfce4-terminal' 'org.xfce.terminal' 'System;TerminalEmulator;'; \
    launcher editor 'Text Editor' 'Edit pipeline and policy files' \
      'mousepad' 'org.xfce.mousepad' 'Utility;TextEditor;'; \
    # --no-sandbox: Code's own sandbox wants user namespaces, which this
    # container does not grant, and without it Code exits before drawing a
    # window.  The container is already the boundary here.
    launcher vscode 'Visual Studio Code' 'The editor, with the code review plugin' \
      'code --no-sandbox --disable-gpu %F' 'vscode' 'Development;IDE;'; \
    launcher fixtures 'Course Fixtures' 'The sample repositories and pipelines' \
      'thunar /home/student/fixtures' 'folder' 'Utility;'; \
    # The lab-env window prints this session's values and then leaves a working
    # shell behind.  xfce4-terminal's own --hold would instead park a "the child
    # process exited" bar across the top of a window that can no longer be
    # typed in, which reads as a broken terminal.
    printf '%s\n' '#!/bin/bash' 'lab-env' 'exec bash -l' \
      > /usr/local/bin/lab-env-window; \
    chmod 755 /usr/local/bin/lab-env-window; \
    printf '%s\n' '[Desktop Entry]' 'Version=1.0' 'Type=Application' \
      'Name=Your Lab Environment' 'Comment=URLs, logins and tokens for this session' \
      # The title MUST be quoted.  A .desktop Exec line is split on spaces, so
      # unquoted it hands xfce4-terminal "--title=Your" and then "Lab" and
      # "Environment" as stray arguments; it rejects them and exits at once,
      # and a double click looks like it did nothing at all.
      'Exec=xfce4-terminal --title="Your Lab Environment" --command=/usr/local/bin/lab-env-window' \
      'Icon=dialog-information' 'Terminal=false' 'Categories=System;' \
      > /home/student/Desktop/lab-env.desktop; \
    chmod +x /home/student/Desktop/*.desktop; \
    chown -R student:student /home/student/Desktop /home/student/.config; \
    \
    # Run the login-time fixups (show the launchers, trust them, kill the
    # blanker) inside the Xfce session.  The script itself arrives in the COPY
    # below; this only records that the session should run it.
    mkdir -p /etc/xdg/autostart; \
    printf '%s\n' '[Desktop Entry]' 'Type=Application' 'Name=Lab Desktop Setup' \
      'Exec=/usr/local/bin/lab-desktop-setup' 'OnlyShowIn=XFCE;' \
      'X-XFCE-Autostart-Override=true' \
      > /etc/xdg/autostart/zzz-lab-desktop-setup.desktop; \
    \
    # ---- clean up in the same layer ----------------------------------------
    apt-get clean; rm -rf /var/lib/apt/lists/* /root/.cache

# The desktop entrypoint, the start-page generator, and the login-time desktop
# fixups.  File modes come from the repository, so no chmod layer is needed.
COPY bin/ /usr/local/bin/

# 3389 for Guacamole (protocol 'rdp'); 22 because the base image's entrypoint
# still runs sshd, so the same box also answers the terminal lessons.
EXPOSE 3389 22
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/lab-gui-entrypoint"]
