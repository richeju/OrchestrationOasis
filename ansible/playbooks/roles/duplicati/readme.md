# Duplicati Role

Deploys [Duplicati](https://www.duplicati.com/) using Docker Compose.

## Variables

- `duplicati_version`: Docker image tag (default `latest`)
- `duplicati_dir`: Directory for the compose file (default `/opt/duplicati`)
- `duplicati_puid`: User ID for the container (default `1000`)
- `duplicati_pgid`: Group ID for the container (default `1000`)
- `duplicati_timezone`: Time zone (default `Etc/UTC`)
- `duplicati_settings_key`: Optional settings encryption key from `DUPLICATI_SETTINGS_KEY`
- `duplicati_port`: Host port for the web UI (default `8200`)
- `duplicati_web_password`: Required web UI password from `DUPLICATI_WEB_PASSWORD`

Store sensitive values in the environment or Ansible Vault, never in version control.
