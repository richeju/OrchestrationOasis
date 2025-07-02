# Zerotier Role

Deploys [ZeroTier](https://www.zerotier.com/) using Docker Compose and optionally joins a network.

Example inventory entry:

```yaml
[zerotier]
host1 zerotier_network_id=abcd1234
```

## Variables

- `zerotier_version`: Image tag to use (default `"latest"`).
- `zerotier_dir`: Directory for the compose project (default `/opt/zerotier`).
- `zerotier_network_id`: Network ID to join (default `""`). If empty, no network is joined.
