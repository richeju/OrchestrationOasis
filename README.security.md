# Sécurité – Trivy

Ce dépôt inclut une configuration pour analyser les vulnérabilités, les erreurs de configuration et les secrets grâce à [Trivy](https://github.com/aquasecurity/trivy).

## Scan local

```bash
make scan
```

Cette commande lance Trivy 0.72.0 en mode *filesystem* avec les scanners
`vuln`, `misconfig` et `secret`. Le cache est stocké dans `.trivy-cache/`.

Vous pouvez également utiliser docker compose :

```bash
docker compose -f docker-compose.security.yml run --rm trivy
```

## Intégration CI

Le job `security` du workflow GitHub [`ci.yml`](.github/workflows/ci.yml)
exécute les mêmes scanners sur chaque `push` et `pull request`. Les scans
locaux et CI échouent sur les problèmes `HIGH` ou `CRITICAL` qui disposent
d'un correctif ; `ignore-unfixed` exclut explicitement les problèmes sans
correctif disponible.
