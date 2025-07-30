# bind_dns Role

Deploys a BIND9 DNS server inside Docker and generates zone files from NetBox.
The container is managed using `docker compose` with a generated compose file.

## Variables

- `bind_dns_domain`: DNS domain to manage (default `home.local`)
- `bind_dns_reverse_prefix`: Reverse zone prefix (default `10.168.192` for `192.168.10.0/24`)
- `bind_dns_dir`: Directory for configuration files (default `/opt/bind`)
- `bind_dns_image`: Docker image tag (default `internetsystemsconsortium/bind9:9.18`)
- `bind_dns_forwarders`: List of DNS forwarder IPs (default `1.1.1.1`, `9.9.9.9`)
- `bind_dns_configure_resolver`: Whether to add 127.0.0.1 to `/etc/resolv.conf`
- `netbox_url`: Base URL for the NetBox API
- `netbox_token`: API token for NetBox
- `bind_dns_zerotier_ip`: IP address of the ZeroTier interface (auto-detected). Ports are bound to this address so BIND listens only on ZeroTier
- `bind_dns_compose_path`: Directory where `docker-compose.yml` is generated (defaults to `bind_dns_dir`)

Example zone output (`zone.j2`):
```
$TTL 3600
@   IN SOA ns1.home.local. admin.home.local. (
        2024010101 ; Serial
        3600       ; Refresh
        900        ; Retry
        604800     ; Expire
        86400 )    ; Negative Cache TTL

@   IN NS ns1.home.local.
ns1 IN A 192.168.1.10
host1 IN A 192.168.1.20
```
