variable "docker_tag" {
  type    = string
  default = "latest"
}

source "docker" "debian" {
  image  = "debian:12"
  commit = true
}

build {
  sources = ["source.docker.debian"]

  provisioner "shell" {
    inline = [
      "apt-get update",
      "apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release sudo",
      "mkdir -p /etc/apt/keyrings",
      "curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg",
      "chmod a+r /etc/apt/keyrings/docker.gpg",
      "echo \"deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable\" | tee /etc/apt/sources.list.d/docker.list > /dev/null",
      "apt-get update",
      "apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin"
    ]
  }

  post-processor "docker-tag" {
    repository = "ghcr.io/richeju/debian12-server"
    tag        = ["${var.docker_tag}"]
  }
}
