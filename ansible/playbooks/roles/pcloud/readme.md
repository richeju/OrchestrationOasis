# How to Generate a Token for pCloud

This guide explains how to generate an authentication token for pCloud using rclone, which is required for the `pcloud` role in this repository.

## Steps

- Install rclone on a machine with a web browser, then type `rclone config` in a command-line interface (CLI).
- Select `n` for "New remote".
- Enter a name for the new remote (e.g., `pcloud`).
- When prompted for "Storage", type `40` (the number for pCloud).
- Press Enter to leave `client_id` and `client_secret` empty.
- When asked about "Advanced Settings", press Enter for "No".
- When prompted "Use web browser to automatically authenticate rclone with remote?", answer:
  - `y` if the machine running rclone has a web browser you can use.
- Log in to pCloud via the browser link provided by rclone and authorize access.
- Once completed, rclone will display a token in JSON format (e.g., `{"access_token":"xxx","token_type":"bearer","expiry":"2025-05-05T22:00:00Z"}`).
- Save this token, including the curly braces, and provide it to the role using the `pcloud_token` variable. You can keep the value in `defaults/main.yml` during testing or store it securely with `ansible-vault` in your inventory.
