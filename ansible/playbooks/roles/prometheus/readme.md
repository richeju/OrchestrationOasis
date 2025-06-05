# Prometheus Role

Deploys [Prometheus](https://prometheus.io/) using Docker Compose.

## Variables

- `prometheus_version`: Docker image tag (default `latest`)
- `prometheus_dir`: Directory for the compose file (default `/opt/prometheus`)

Store sensitive values outside version control if required.
