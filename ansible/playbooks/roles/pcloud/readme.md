# How to generate a pCloud token

The `pcloud` role uses an rclone OAuth token. Generate it on a trusted machine
with a web browser; never paste the resulting token into Git or a plaintext
inventory.

1. Install a current rclone release and run `rclone config`.
2. Choose `n` to create a new remote and give it a local name such as `pcloud`.
3. Select the backend named `pcloud`. Do not rely on its numeric menu position,
   which can change between rclone versions.
4. Leave `client_id` and `client_secret` empty unless you operate your own pCloud
   OAuth application.
5. Use browser authentication, sign in to pCloud, and authorize rclone.
6. Copy the complete JSON token returned by rclone.
7. Supply it as `PCLOUD_TOKEN` or an encrypted `pcloud_token` Ansible Vault
   value. The environment variable takes precedence.

Treat the token as a password. Revoke it in pCloud and replace the deployment
secret if it is ever exposed.
