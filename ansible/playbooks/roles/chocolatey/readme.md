# Chocolatey Role

Installs [Chocolatey](https://chocolatey.org/) on Windows hosts using the `win_chocolatey` module from the `chocolatey.chocolatey` collection.

The role also upgrades all installed Chocolatey packages to their latest
versions.

## Variables

- `chocolatey_state`: Installation state for Chocolatey (`present` or `absent`). Defaults to `present`.
- `chocolatey_install_args`: Arguments passed to all Chocolatey package installs. Defaults to `ALLUSERS=1`.
