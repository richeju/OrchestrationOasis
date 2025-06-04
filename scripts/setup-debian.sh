#!/bin/bash
# Install Docker and Ansible on Debian-based systems
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    SUDO='sudo'
else
    SUDO=''
fi

$SUDO apt-get update
$SUDO apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release software-properties-common

# Install Ansible
$SUDO apt-get install -y ansible

# Install Packer
$SUDO curl -fsSL https://apt.releases.hashicorp.com/gpg | $SUDO apt-key add -
$SUDO apt-add-repository "deb [arch=$(dpkg --print-architecture)] https://apt.releases.hashicorp.com $(lsb_release -cs) main"
$SUDO apt-get update
$SUDO apt-get install -y packer

# Configure Docker repository
$SUDO install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | $SUDO gpg --dearmor -o /etc/apt/keyrings/docker.gpg
$SUDO chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | $SUDO tee /etc/apt/sources.list.d/docker.list > /dev/null

$SUDO apt-get update
$SUDO apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Enable Docker service
$SUDO systemctl enable --now docker

# Add current user to docker group if not root
if [ "$(id -u)" -ne 0 ]; then
    $SUDO usermod -aG docker "$USER"
fi

echo "Docker, Ansible and Packer installation complete."
