# Tasks Remaining for V1 (Debian 12, Bitwarden Web API)

1. **Verify Linting**:
   - Re-run Super-Linter to confirm:
     ```bash
     docker run --rm -v $(pwd):/github/workspace -e VALIDATE_ALL_CODEBASE=true -e VALIDATE_MARKDOWN=true -e VALIDATE_YAML=true -e VALIDATE_ANSIBLE=true -e DEFAULT_BRANCH=main github/super-linter:v5
     ```
   - If warnings appear for `pcloud/templates/rclone.conf.j2` or `rclone-pcloud.service.j2`, add `---`.

2. **Remove `dummy.yml`**:
   - ```bash
     git rm scripts/dummy.yml
     git commit -m "Remove dummy.yml for V1"
     ```

3. **Integrate Bitwarden Web API**:
   - Delete `ansible/roles/pcloud/vars/vault.yml`:
     ```bash
     git rm ansible/roles/pcloud/vars/vault.yml
     ```
   - Update `install_pcloud.yml` (remove `vars_files`).
   - Update `site.yml` (remove `vars_files`).
   - Modify `pcloud/tasks/main.yml` to use Bitwarden API (authentication, token retrieval).
   - Update `.ansible-lint` (remove `exclude_paths`).

4. **Add Validations to Roles**:
   - `docker`: Verify service and `docker ps`.
   - `pcloud`: Verify `/mnt/pcloud` mount.
   - `ufw`: Verify `ufw status`.
   - `jenkins`: Verify port 8080.

5. **Configure Molecule**:
   - Create Molecule files for `docker` and `pcloud` (use `debian:12` image).
   - Update `.github/workflows/lint.yml` with Molecule tests.

6. **Create Documentation**:
   - Create `docs/` with `docker.md`, `pcloud.md`, `ufw.md`, `jenkins.md`.
   - Copy `ansible/roles/pcloud/readme.md` to `docs/pcloud.md`.

7. **Add Inventory**:
   - Create `examples/inventory.yml` with Bitwarden variables (`client_id`, `client_secret`, `password`, `token_item_id`).

8. **Test on Debian 12**:
   - Run playbooks, verify services (Docker, pCloud, UFW, Jenkins).
   - Test Molecule locally:
     ```bash
     pip install molecule[docker] docker
     cd ansible/roles/docker
     molecule test
     ```

9. **Tag V1**:
   - ```bash
     git tag v1.0.0
     git push --tags
     ```
