# Zerotier Role

Installs [ZeroTier](https://www.zerotier.com/) on Linux systems and optionally joins a network.

Example inventory entry:

```yaml
[zerotier]
host1 zerotier_network_id=abcd1234
```

## Variables

- `zerotier_network_id`: Network ID to join (default `""`). If empty, no network is joined.

