# NetBox Role

Deploys [NetBox](https://github.com/netbox-community/netbox) using Docker Compose.

## Variables

- `netbox_version`: Docker image tag (default `latest`)
- `netbox_dir`: Directory for the compose file (default `/opt/netbox`)
- `netbox_db_user`: Database user (default `netbox`)
- `netbox_db_name`: Database name (default `netbox`)
- `netbox_db_password`: Database password (default `netbox`)
- `netbox_redis_password`: Redis password (default `netbox`)
- `netbox_secret_key`: Django secret key (default `change-me`)
- `netbox_port`: Host port to expose NetBox (default `8080`)

Store sensitive values outside of version control if required.
