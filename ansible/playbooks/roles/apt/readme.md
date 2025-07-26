# Apt Role

Updates and upgrades packages on Debian-based systems using the `apt` module.

## Variables

- `apt_cache_valid_time`: Cache validity in seconds before refreshing (default `3600`).
- `apt_upgrade_type`: Upgrade type passed to the module (default `dist`).
- `apt_autoremove`: Whether to remove unused packages (default `true`).
- `apt_autoclean`: Whether to clean the apt cache (default `true`).
