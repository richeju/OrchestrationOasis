# This script installs Git using Chocolatey on Windows.
# Ensure Chocolatey is installed before running. If not, use the commented line below.
# Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# Install Git via Chocolatey
choco install git -y

# Verify the installation
git --version
