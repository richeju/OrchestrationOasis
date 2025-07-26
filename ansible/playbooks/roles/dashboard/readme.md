# Dashboard Role

Deploys [Dashy](https://github.com/Lissy93/dashy) using Docker Compose.

## Variables

- `dashboard_image`: Docker image to deploy (default `lissy93/dashy:latest`)
- `dashboard_dir`: Directory for the compose file (default `/opt/dashboard`)
- `dashboard_port`: Host port for Dashy UI (default `4000`)
- `dashboard_volume`: Named volume for Dashy data (default `dashy-data`)

The role always pulls the image before launching the stack so the container is updated to the latest version on each run.

Store sensitive values outside of version control if required.
