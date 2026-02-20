#!/bin/bash
# Install Docker and Fail2ban on Debian-based systems
set -euo pipefail

REPO_URL="${1:-}"

if [ "$(id -u)" -ne 0 ]; then
    SUDO='sudo'
else
    SUDO=''
fi

log() {
    echo "[setup-debian] $*"
}

run() {
    if [ -n "$SUDO" ]; then
        "$SUDO" "$@"
    else
        "$@"
    fi
}

install_base_packages() {
    log "Updating apt cache and installing prerequisites"
    run apt-get update
    run apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release software-properties-common git
}

clone_repository_if_requested() {
    if [ -n "$REPO_URL" ]; then
        log "Cloning repository: $REPO_URL"
        git clone "$REPO_URL"
    fi
}

configure_docker_repository() {
    run install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg | run gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    run chmod a+r /etc/apt/keyrings/docker.gpg

    if [ ! -f /etc/apt/sources.list.d/docker.list ]; then
        log "Adding Docker apt repository"
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | run tee /etc/apt/sources.list.d/docker.list > /dev/null
    fi
}

install_docker() {
    if command -v docker >/dev/null 2>&1; then
        log "Docker already installed; skipping"
        return
    fi

    log "Installing Docker"
    configure_docker_repository
    run apt-get update
    run apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    run systemctl enable --now docker

    if [ "$(id -u)" -ne 0 ]; then
        run usermod -aG docker "$USER"
    fi

    log "Docker installation complete"
}

install_fail2ban() {
    if ! dpkg -s fail2ban >/dev/null 2>&1; then
        log "Installing Fail2ban"
        run apt-get install -y fail2ban
    else
        log "Fail2ban already installed"
    fi
}

configure_fail2ban() {
    log "Configuring Fail2ban"
    run tee /etc/fail2ban/fail2ban.conf >/dev/null <<'CONF'
[DEFAULT]
loglevel = INFO
logtarget = SYSLOG
backend = systemd
CONF

    run tee /etc/fail2ban/jail.local >/dev/null <<'CONF'
[DEFAULT]
backend = systemd
bantime = 3600
maxretry = 5

[sshd]
enabled = true
filter = sshd
CONF

    run systemctl enable --now fail2ban
    log "Fail2ban installation complete"
}

main() {
    install_base_packages
    clone_repository_if_requested
    install_docker
    install_fail2ban
    configure_fail2ban
}

main
