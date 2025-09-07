# Orchestration Oasis

Orchestration Oasis is an infrastructure automation project built around **Ansible**. It currently features roles for Docker, UFW, Fail2ban, pCloud, Zerotier, Duplicati, and NetBox, and a Dashy-based Dashboard (using Docker Compose) to help configure a Debian 12 server.
Windows hosts can also be provisioned using Chocolatey. A dedicated role installs Chocolatey, and another role installs the optional Chocolatey GUI.
The list below tracks the remaining work before the first stable release.

## Setup

Run the helper script to install Docker and Fail2ban on a fresh Debian system.
The script is non-interactive, installs Git and optionally clones a
repository if a URL is provided. Docker and Fail2ban are configured with a basic setup and the script skips packages that are already installed:

```bash
./scripts/setup-debian.sh <repo_url>
```


## Usage

Run the Ansible playbook (replace `<inventory>` with your inventory file):

```bash
cd ansible
ansible-playbook -i <inventory> site.yml
```


For Windows hosts, first install Chocolatey:

```bash
ansible-playbook -i <inventory> playbooks/install_chocolatey.yml
```

Optionally install the Chocolatey GUI:

```bash
ansible-playbook -i <inventory> playbooks/install_chocolatey_gui.yml
```

The Chocolatey role now also upgrades all installed packages to their latest
versions on each run.

To install Zerotier only on hosts in the `zerotier` group:

```bash
ansible-playbook -i <inventory> playbooks/install_zerotier.yml
```

Set `zerotier_network_id` to join a specific network (leave empty to skip).

To remove unnecessary packages while keeping Chocolatey, run `choco uninstall <package>` for each application you want to remove.


### YubiKey for SSH

To require a YubiKey alongside your SSH key:

1. Generate a U2F mapping on a system with the YubiKey attached:

   ```bash
   pamu2fcfg >> ~/.config/Yubico/u2f_keys
   ```

   Copy the resulting line into your inventory. For example:

   ```yaml
   yubikey_mappings:
     - "alice:HEXDATA"
   ```

   Alternatively, place the line in a file and set `yubikey_authfile` to its path.

2. Ensure your inventory has a `yubikey` group for the host you want to protect:

   ```yaml
   yubikey:
     hosts:
       localhost:
   ```

3. Deploy the configuration:

   ```bash
   ansible-playbook -i <inventory> playbooks/install_yubikey.yml
   ```

After the playbook runs, SSH logins will prompt for a touch of the YubiKey after public key authentication.


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
    - If yamllint warns about `pcloud/templates/rclone.conf.j2` or `rclone-pcloud.service.j2`,
      ignore the message or add `# yamllint disable-file` to the top of the template.
      These files are not YAML, so adding `---` will break rclone and systemd.

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
    - Run playbooks, verify services (Docker, pCloud, UFW).
    - Test Molecule locally:
     ```bash
     pip install molecule[docker] docker
     cd ansible/playbooks/roles/docker
     molecule test
     ```
