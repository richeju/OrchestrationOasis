#!/bin/bash
# Install Docker and Ansible on Debian-based systems
set -euo pipefail

# Optional repository URL to clone
REPO_URL="${1:-}"

if [ "$(id -u)" -ne 0 ]; then
    SUDO='sudo'
else
    SUDO=''
fi

$SUDO apt-get update
$SUDO apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release software-properties-common git

if [ -n "$REPO_URL" ]; then
    git clone "$REPO_URL"
fi

# Install Ansible if not present
if ! command -v ansible >/dev/null 2>&1; then
    $SUDO apt-get install -y ansible
fi


# Install Docker if not present
if ! command -v docker >/dev/null 2>&1; then
    $SUDO install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg | $SUDO gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    $SUDO chmod a+r /etc/apt/keyrings/docker.gpg

    if [ ! -f /etc/apt/sources.list.d/docker.list ]; then
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | $SUDO tee /etc/apt/sources.list.d/docker.list > /dev/null
    fi

    $SUDO apt-get update
    $SUDO apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    # Enable Docker service
    $SUDO systemctl enable --now docker

    # Add current user to docker group if not root
    if [ "$(id -u)" -ne 0 ]; then
        $SUDO usermod -aG docker "$USER"
    fi
fi

echo "Docker and Ansible installation complete."
