# Dockerized Deployment

This repository can be used from a Docker container so Ansible and its dependencies do not need to be installed on the host.

## Build the Image

```bash
docker build -t orchestrationoasis .
```

## Run the Playbook

By default the container runs `ansible-playbook` against the local machine:

```bash
docker run --rm -it orchestrationoasis
```

Volume mounts and SSH configuration can be added if remote hosts should be managed from the container.
