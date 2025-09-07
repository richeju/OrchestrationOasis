# YubiKey Role

Installs and configures YubiKey U2F authentication for SSH.

## Variables

- `yubikey_authfile`: Path to the U2F mappings file (default `/etc/yubico/u2f_keys`)
- `yubikey_mappings`: List of YubiKey mappings to deploy (default `[]`)

Store sensitive mapping values outside of version control if required.
