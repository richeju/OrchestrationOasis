#!/bin/bash

echo "PCLOUD_USERNAME: $PCLOUD_USERNAME"
echo "Starting pcloudcc with provided credentials"

expect -c "
spawn /usr/local/bin/pcloudcc -u \"$PCLOUD_USERNAME\" -p \"$PCLOUD_PASSWORD\" -m /mnt/pcloud -d
expect \"Please, enter password\"
send \"$PCLOUD_PASSWORD\r\"
interact
"

exec "$@"
