# Vault Role

Deploys [HashiCorp Vault](https://www.vaultproject.io/) using Docker Compose in dev mode.

## Variables

- `vault_version`: Docker image tag (default `latest`)
- `vault_dir`: Directory for the compose file (default `/opt/vault`)
- `vault_port`: Host port for the Vault UI and API (default `8201`)
- `vault_dev_root_token_id`: Root token for dev mode (default `"root"`)

Store any sensitive values outside version control if required.
