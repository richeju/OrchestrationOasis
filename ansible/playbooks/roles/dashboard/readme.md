# Dashboard Role

Deploys [Dashy](https://github.com/Lissy93/dashy) using Docker Compose.

## Variables

- `dashboard_version`: Docker image tag (default `latest`)
- `dashboard_dir`: Directory for the compose file (default `/opt/dashboard`)
- `dashboard_port`: Host port for Dashy UI (default `4000`)

Store sensitive values outside of version control if required.
