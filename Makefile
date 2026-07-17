.PHONY: help install lint workflows syntax test links check scan

help:
	@echo "install  Install Python and Ansible dependencies"
	@echo "lint     Run YAML and Ansible linters"
	@echo "workflows Validate GitHub Actions workflows"
	@echo "syntax   Check the complete playbook syntax"
	@echo "test     Run local regression tests"
	@echo "links    Validate repository-local Markdown links"
	@echo "check    Run lint, syntax, tests, and documentation checks"
	@echo "scan     Audit Python dependencies and scan with Trivy"

install:
	python3 -m pip install --requirement requirements-dev.txt
	ansible-galaxy collection install --requirements-file ansible/requirements.yml

lint:
	./scripts/run-lint.sh ansible

workflows:
	./scripts/run-actionlint.sh

syntax:
	ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook --syntax-check ansible/site.yml

test:
	./scripts/tests/run-lint.test.sh
	./scripts/tests/markdown-links.test.sh
	./scripts/tests/safety-gates.test.sh
	./scripts/tests/repository-safety.test.sh
	./scripts/tests/service-roles.test.sh
	./scripts/tests/hermes-role.test.sh
	./scripts/tests/restic-role.test.sh
	./scripts/tests/semaphore-role.test.sh

links:
	python3 ./scripts/check-markdown-links.py

check: lint workflows syntax test links

scan:
	python -m pip_audit --requirement requirements-dev.txt --progress-spinner off
	./scripts/run-trivy.sh
