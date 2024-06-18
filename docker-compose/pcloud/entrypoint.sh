#!/usr/bin/expect -f

set timeout -1

# Environment variables
set username $env(PCLOUD_USERNAME)
set password $env(PCLOUD_PASSWORD)

puts "PCLOUD_USERNAME: $username"
puts "Starting pcloudcc with provided credentials"

spawn /usr/local/bin/pcloudcc -u $username -p $password -m /mnt/pcloud -d
expect "Please, enter password"
send "$password\r"
expect eof

# Keep the container running
exec sh -c "tail -f /dev/null"
