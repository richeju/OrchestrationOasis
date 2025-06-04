FROM debian:12

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ansible \
       python3-pip \
       git curl \
    && pip3 install --no-cache-dir kubernetes ansible-lint \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/ansible
COPY ansible/ ansible/
COPY .ansible-lint .
RUN ansible-galaxy collection install -r ansible/requirements.yml

CMD ["ansible-playbook", "ansible/site.yml", "-i", "localhost,", "-c", "local"]
