#!/bin/bash

echo "Database user:"
read db_user

echo "Original database name:"
read db_name

echo "New database name:"
read db_new_name

echo "Root password:"
read db_root_password

echo "Creating database..."
mysql -u root -h 127.0.0.1 "-p${db_root_password}" -e "CREATE DATABASE ${db_new_name}; GRANT ALL PRIVILEGES ON ${db_new_name}.* TO '${db_user}'@'%';" || exit 1

echo "Copying database data..."
mysqldump -u root "-p${db_root_password}" -h 127.0.0.1 "${db_name}" | mysql -u root "-p${db_root_password}" -h 127.0.0.1 "${db_new_name}" || exit 1
