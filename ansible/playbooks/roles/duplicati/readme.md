# Duplicati Role

Deploys [Duplicati](https://www.duplicati.com/) using Docker Compose.

## Variables

- `duplicati_version`: Docker image tag (default `latest`)
- `duplicati_dir`: Directory for the compose file (default `/opt/duplicati`)
- `duplicati_puid`: User ID for the container (default `1000`)
- `duplicati_pgid`: Group ID for the container (default `1000`)
- `duplicati_timezone`: Time zone (default `Etc/UTC`)
- `duplicati_settings_key`: Optional settings encryption key (default empty)
- `duplicati_port`: Host port for the web UI (default `8200`)
- `duplicati_web_password`: Password for the web UI (default `""`)

Store sensitive values outside version control if required.
