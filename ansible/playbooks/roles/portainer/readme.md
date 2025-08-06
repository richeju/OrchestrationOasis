# Portainer Role

Deploys [Portainer](https://www.portainer.io/) using Docker Compose.

## Variables

- `portainer_image`: Docker image to deploy (default `portainer/portainer-ce:latest`)
- `portainer_dir`: Directory for the compose file (default `/opt/portainer`)
- `portainer_port`: Host port for the HTTPS UI (default `9443`)
- `portainer_edge_port`: Host port for the Edge agent (default `8000`)
- `portainer_data_volume`: Named volume for Portainer data (default `portainer-data`)

The role always pulls the image before launching the stack so the container is updated to the latest version on each run.

Ports are bound to the ZeroTier interface's IP address so the service is only accessible over ZeroTier.
