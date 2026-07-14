.PHONY: help install lint syntax test check scan

help:
	@echo "install  Install Python and Ansible dependencies"
	@echo "lint     Run YAML and Ansible linters"
	@echo "syntax   Check the complete playbook syntax"
	@echo "test     Run local regression tests"
	@echo "check    Run lint, syntax, and tests"
	@echo "scan     Scan the repository with Trivy"

install:
	python3 -m pip install --requirement requirements-dev.txt
	ansible-galaxy collection install --requirements-file ansible/requirements.yml

lint:
	./scripts/run-lint.sh ansible

syntax:
	ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook --syntax-check ansible/site.yml

test:
	./scripts/tests/run-lint.test.sh
	./scripts/tests/safety-gates.test.sh

check: lint syntax test

scan:
	docker run --rm -v $$PWD:/project:ro -v $$PWD/.trivy-cache:/root/.cache/ \
		aquasec/trivy:0.72.0 fs --scanners vuln,misconfig,secret --ignore-unfixed \
		--exit-code 1 --severity HIGH,CRITICAL --skip-dirs /project/.venv \
		--skip-dirs /project/.git --skip-dirs /project/.trivy-cache /project
