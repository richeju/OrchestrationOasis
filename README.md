# Orchestration Oasis

Orchestration Oasis is an infrastructure automation project built around **Ansible**. It currently features roles for Docker, UFW, Fail2ban, pCloud, and Semaphore to help configure a Debian 12 server.
Windows hosts can also be provisioned using Chocolatey, with roles to install VLC, Google Chrome, Thunderbird, Notepad++, Git, OpenJDK 17 (JRE), 7-Zip, Everything, LibreOffice, pCloud, Signal, ZeroTier, and Steam.
The list below tracks the remaining work before the first stable release.

## Setup

Run the helper script to install Docker and Ansible on a fresh Debian system.
The script is non-interactive, installs Git and optionally clones a repository
if a URL is provided. It skips packages that are already installed:

```bash
./scripts/setup-debian.sh <repo_url>
```


## Usage

Run the Ansible playbook (replace `<inventory>` with your inventory file):

```bash
cd ansible
ansible-playbook -i <inventory> site.yml
```

For Windows hosts, you can install Chocolatey along with VLC, Google Chrome,
Thunderbird, Notepad++, Git, OpenJDK 17 (JRE), 7-Zip, Everything, LibreOffice, pCloud, Signal, ZeroTier, and Steam in one step:

```bash
ansible-playbook -i <inventory> playbooks/install_chocolatey_and_vlc.yml
```

The playbooks `install_chocolatey.yml` and `install_vlc.yml` remain available if you prefer to run them separately.
The Chocolatey role now also upgrades all installed packages to their latest
versions on each run.

## OCR Example

An example Node script using **tesseract.js** is available in `examples/ocr.mjs`.
Install `tesseract.js` and run the script with an image path:

```bash
npm install tesseract.js@latest
node examples/ocr.mjs path/to/image.png
```

## Linting

Use the helper script to run `yamllint` and `ansible-lint` locally:

```bash
./scripts/run-lint.sh
```

The script automatically sets `ANSIBLE_CONFIG` to `ansible/ansible.cfg`. If you
can't run the Docker-based Super-Linter locally, rely on the GitHub workflow to
perform the additional checks.

## Tasks Remaining for V1 (Debian 12, Bitwarden Web API)

1. [x] **Verify Linting**:
    - Re-run Super-Linter to confirm:
     ```bash
     docker run --rm -v $(pwd):/github/workspace -e VALIDATE_ALL_CODEBASE=true -e VALIDATE_MARKDOWN=true -e VALIDATE_YAML=true -e VALIDATE_ANSIBLE=true -e DEFAULT_BRANCH=main github/super-linter:v5
     ```
    - If warnings appear for `pcloud/templates/rclone.conf.j2` or `rclone-pcloud.service.j2`, add `---`.
    - `---` has been added to these templates to satisfy the linter.

2. [x] **Integrate Bitwarden Web API**:
    - Delete `ansible/playbooks/roles/pcloud/vars/vault.yml`:
     ```bash
     git rm ansible/playbooks/roles/pcloud/vars/vault.yml
     ```
    - Update `install_pcloud.yml` (remove `vars_files`).
    - Update `site.yml` (remove `vars_files`).
    - Modify `pcloud/tasks/main.yml` to use Bitwarden API (authentication, token retrieval).
    - Update `.ansible-lint` (remove `exclude_paths`).

3. [ ] **Add Validations to Roles**:
    - `docker`: Verify service and `docker ps`.
    - `pcloud`: Verify `/mnt/pcloud` mount.
    - `ufw`: Verify `ufw status`.

4. [ ] **Configure Molecule**:
    - Create Molecule files for `docker` and `pcloud` (use `debian:12` image).
    - Update `.github/workflows/lint.yml` with Molecule tests.

5. [ ] **Create Documentation**:
    - Create `docs/` with `docker.md`, `pcloud.md`, `ufw.md`.
    - Copy `ansible/playbooks/roles/pcloud/readme.md` to `docs/pcloud.md`.

6. [ ] **Add Inventory**:
    - Create `examples/inventory.yml` with Bitwarden variables (`client_id`, `client_secret`, `password`, `token_item_id`).

7. [ ] **Test on Debian 12**:
    - Run playbooks, verify services (Docker, pCloud, UFW, Semaphore).
    - Test Molecule locally:
     ```bash
     pip install molecule[docker] docker
     cd ansible/playbooks/roles/docker
     molecule test
     ```
