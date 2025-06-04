# Running ArgoCD in a Container

ArgoCD is distributed as Docker images, so it can be launched without a Kubernetes
cluster for basic testing. The example compose file below starts the ArgoCD server
with the UI available on port 8080:

```bash
docker compose -f docker-compose.argocd.yml up -d
```

This setup is useful for experiments but does not replace a full Kubernetes
installation. For production use, deploy ArgoCD to a cluster using the `argocd`
role.
