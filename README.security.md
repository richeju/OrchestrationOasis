# Sécurité – Trivy

Ce dépôt inclut une configuration pour analyser les vulnérabilités, les erreurs de configuration et les secrets grâce à [Trivy](https://github.com/aquasecurity/trivy).

## Scan local

```bash
make scan
```

Cette commande lance d'abord `pip-audit`, puis Trivy 0.72.0 en mode
*filesystem* avec les scanners `vuln`, `misconfig` et `secret`. Trivy utilise
le volume Docker nommé `orchestration-oasis-trivy-cache`. Seule la variante
Docker Compose ci-dessous stocke son cache dans `.trivy-cache/`.

Vous pouvez également utiliser docker compose :

```bash
docker compose -f docker-compose.security.yml run --rm trivy
```

## Intégration CI

Le job `security` du workflow GitHub [`ci.yml`](.github/workflows/ci.yml)
exécute les mêmes scanners sur chaque `push` et `pull request`. Les scans
locaux et CI échouent si `pip-audit` détecte une vulnérabilité connue dans les
dépendances Python. Trivy échoue sur les problèmes `HIGH` ou `CRITICAL` qui
disposent d'un correctif ; `ignore-unfixed` exclut explicitement les problèmes
Trivy sans correctif disponible. Le contrôle de liens valide les cibles de
fichiers locales, pas l'existence des fragments `#ancre`.
