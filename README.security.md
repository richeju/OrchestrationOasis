# Sécurité – Trivy

Ce dépôt inclut une configuration pour analyser les vulnérabilités, les erreurs de configuration et les secrets grâce à [Trivy](https://github.com/aquasecurity/trivy).

## Scan local

```bash
make scan
```

Cette commande lance le conteneur `aquasec/trivy` en mode *filesystem* sur le projet. Le cache est stocké dans le dossier `.trivy-cache/`.

Vous pouvez également utiliser docker compose :

```bash
docker compose -f docker-compose.security.yml run --rm trivy
```

## Intégration CI

Le workflow GitHub [`security.yml`](.github/workflows/security.yml) exécute automatiquement un scan Trivy sur chaque `push` et `pull request`. Le job échouera si des vulnérabilités de sévérité `HIGH` ou `CRITICAL` sont trouvées.
