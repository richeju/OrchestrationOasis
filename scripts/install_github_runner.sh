#!/bin/bash

# Bash script to install and configure a GitHub self-hosted runner on Debian
# Prerequisites: user with sudo privileges, outgoing Internet connection (port 443)

# Variables
RUNNER_VERSION="2.312.0"  # GitHub runner version (update if necessary)
RUNNER_DIR="/home/github-runner/actions-runner"
GITHUB_USER="github-runner"
GITHUB_REPO="https://github.com/richeju/richeju-orchestrationoasis"  # Replace with your GitHub repository

# Functions
check_root() {
    if [ "$EUID" -ne 0 ]; then
        echo "This script must be run with sudo. Try: sudo $0"
        exit 1
    fi
}

check_debian() {
    if ! grep -q "Debian" /etc/os-release; then
        echo "This script is intended for Debian. Your system is not Debian."
        exit 1
    fi
}

check_internet() {
    echo "Checking Internet connection (port 443)..."
    if ! curl -s --head https://github.com | grep "200 OK" > /dev/null; then
        echo "Error: Outgoing Internet connection (port 443) is not available. Check your network."
        exit 1
    fi
}

check_resources() {
    echo "Checking minimum resource requirements..."
    CPU_CORES=$(nproc)
    RAM_MB=$(free -h | grep "Mem:" | awk '{print $2}' | sed 's/G//;s/M//')
    DISK_GB=$(df -h / | tail -n1 | awk '{print $4}' | sed 's/G//;s/M//')

    if [ "$CPU_CORES" -lt 2 ]; then
        echo "Error: Less than 2 CPU cores detected. The runner requires at least 2 cores."
        exit 1
    fi
    if [ "$RAM_MB" -lt 7000 ] && [ "$RAM_MB" -gt 0 ]; then
        echo "Warning: Less than 7 GB of RAM detected. The runner may be slow."
    fi
    if [ "$DISK_GB" -lt 14 ]; then
        echo "Error: Less than 14 GB of disk space available. The runner requires at least 14 GB."
        exit 1
    fi
}

create_user() {
    if ! id "$GITHUB_USER" >/dev/null 2>&1; then
        echo "Creating user $GITHUB_USER..."
        adduser --disabled-password --gecos "" "$GITHUB_USER"
        usermod -aG sudo "$GITHUB_USER"
    else
        echo "User $GITHUB_USER already exists."
    fi
}

install_dependencies() {
    echo "Installing dependencies..."
    apt update && apt install -y curl unzip libicu70 libssl1.1
    # Adjust libicu based on your Debian version (e.g., libicu72 for Debian 12)
    if [ $? -ne 0 ]; then
        echo "Error: Failed to install dependencies."
        exit 1
    fi
}

download_runner() {
    echo "Downloading GitHub runner (version $RUNNER_VERSION)..."
    mkdir -p "$RUNNER_DIR" && cd "$RUNNER_DIR"
    curl -o actions-runner-linux-x64-$RUNNER_VERSION.tar.gz -L https://github.com/actions/runner/releases/download/v$RUNNER_VERSION/actions-runner-linux-x64-$RUNNER_VERSION.tar.gz
    if [ $? -ne 0 ]; then
        echo "Error: Failed to download the runner."
        exit 1
    fi

    echo "Extracting the runner..."
    tar xzf ./actions-runner-linux-x64-$RUNNER_VERSION.tar.gz
    if [ $? -ne 0 ]; then
        echo "Error: Failed to extract the runner."
        exit 1
    fi

    echo "Updating permissions..."
    chown -R "$GITHUB_USER:$GITHUB_USER" "$RUNNER_DIR"
    chmod -R 750 "$RUNNER_DIR"
}

configure_runner() {
    echo "Configuring the runner..."
    su - "$GITHUB_USER" -c "cd $RUNNER_DIR && ./config.sh --url $GITHUB_REPO --token <YOUR_GITHUB_PAT> --labels self-hosted,linux,debian --name debian-home-runner --unattended"
    # Replace <YOUR_GITHUB_PAT> with your GitHub Personal Access Token (PAT) with 'repo' permissions
    if [ $? -ne 0 ]; then
        echo "Error: Failed to configure the runner. Check the PAT and GitHub URL."
        exit 1
    fi
}

setup_service() {
    echo "Configuring the runner as a systemd service..."
    su - "$GITHUB_USER" -c "cd $RUNNER_DIR && ./svc.sh install"
    if [ $? -ne 0 ]; then
        echo "Error: Failed to install the service."
        exit 1
    fi

    echo "Starting and enabling the service..."
    systemctl start actions.runner.debian-home-runner.service
    systemctl enable actions.runner.debian-home-runner.service
    if [ $? -ne 0 ]; then
        echo "Error: Failed to start or enable the service."
        exit 1
    fi

    echo "Checking the service status..."
    systemctl status actions.runner.debian-home-runner.service
}

test_runner() {
    echo "Testing the runner (manual execution)..."
    su - "$GITHUB_USER" -c "cd $RUNNER_DIR && ./run.sh" &
    sleep 10  # Wait a bit to see if the runner starts
    pkill -u "$GITHUB_USER" -f run.sh  # Stop the runner after the test
    echo "Test completed. Check logs in $RUNNER_DIR/_diag for errors."
}

# Main execution
echo "Starting the installation of the GitHub self-hosted runner..."

check_root
check_debian
check_internet
check_resources
create_user
install_dependencies
download_runner
configure_runner
setup_service
test_runner

echo "GitHub self-hosted runner installation completed successfully!"
