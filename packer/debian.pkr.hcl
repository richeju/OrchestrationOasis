# Variables
variable "iso_url" {
  type    = string
  default = "https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/debian-12.11.0-amd64-netinst.iso"
}

variable "iso_checksum" {
  type    = string
  default = "sha256:30ca12a15cae6a1033e03ad59eb7f66a6d5a258dcf27acd115c2bd42d22640e8"
}

# Data source pour récupérer dynamiquement la dernière image et son SHA256
data "http" "debian_image_page" {
  url = "https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/"
}

data "http" "debian_sha256sums" {
  url = "https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/SHA256SUMS"
}

# Local pour parser les données et extraire la dernière image et son SHA256
locals {
  # Extraire toutes les images Debian netinst de la page HTML
  image_names = [
    for match in regexall("debian-[0-9]+\\.[0-9]+\\.[0-9]+-amd64-netinst\\.iso", data.http.debian_image_page.body) : match
  ]

  # Trier les images par version et prendre la plus récente
  latest_image = sort(local.image_names)[length(local.image_names) - 1]

  # Construire l'URL complète de la dernière image
  latest_image_url = "https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/${local.latest_image}"

  # Extraire le SHA256 correspondant à la dernière image
  sha256_lines = split("\n", data.http.debian_sha256sums.body)
  sha256 = [
    for line in local.sha256_lines : split("  ", line)[0]
    if contains(split("  ", line), local.latest_image)
  ][0]
}

source "virtualbox-iso" "debian" {
  guest_os_type = "Debian_64"
  iso_url       = local.latest_image_url
  iso_checksum  = "sha256:${local.sha256}"
  ssh_username  = "packeruser"
  ssh_password  = "packeruser"
  ssh_timeout   = "30m"
  disk_size     = 30000
  memory        = 2048
  cpus          = 2
  headless      = true
  vm_name       = "debian12-lab-server"
  boot_command  = [
    "<esc><wait>",
    "auto url=http://{{ .HTTPIP }}:{{ .HTTPPort }}/preseed.cfg ",
    "DEBIAN_FRONTEND=text ",
    "keyboard-configuration/xkb-keymap=fr ",
    "console-setup/ask_detect=false ",
    "locale=fr_FR.UTF-8 ",
    "priority=critical ",
    "interface=auto ",
    "netcfg/get_hostname=debian ",
    "netcfg/get_domain=local ",
    "<enter>"
  ]
  http_directory   = "http"
  shutdown_command = "echo 'packeruser' | sudo -S shutdown -P now"
}

# Build
build {
  sources = ["source.virtualbox-iso.debian"]

  provisioner "shell" {
    script = "scripts/setup.sh"
  }
}
