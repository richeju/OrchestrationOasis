# NetBox Role

> **Legacy compact stack only.** This role does not model the official NetBox
> production topology currently running on Infraforge. Do not target production
> without the explicit compact-stack confirmation and a reviewed migration plan.

Deploys [NetBox](https://github.com/netbox-community/netbox) using Docker Compose.

## Variables

- `netbox_version`: Docker image tag (default `latest`)
- `netbox_dir`: Directory for the compose file (default `/opt/netbox`)
- `netbox_db_user`: Database user (default `netbox`)
- `netbox_db_name`: Database name (default `netbox`)
- `netbox_db_password`: Database password (required secret)
- `netbox_redis_password`: Redis password (required secret)
- `netbox_secret_key`: Django secret key (required secret)
- `netbox_port`: Host port to expose NetBox (default `8080`)

Store sensitive values outside of version control if required.
