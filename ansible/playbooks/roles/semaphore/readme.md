# Semaphore Role

Deploys [Semaphore](https://github.com/ansible-semaphore/semaphore) using Docker Compose.

## Variables

- `semaphore_version`: Docker image tag (default `latest`)
- `semaphore_dir`: Directory for the compose file (default `/opt/semaphore`)
- `semaphore_db_user`: Database user (default `semaphore`)
- `semaphore_db_name`: Database name (default `semaphore`)
- `semaphore_db_pass`: Database password (empty by default)
- `semaphore_admin`: Semaphore admin account (default `admin`)
- `semaphore_admin_password`: Admin password (empty by default)

Store any sensitive values outside of version control, for example with `ansible-vault`.

