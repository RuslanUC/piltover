#!/bin/sh

openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -sha256 -days 3650 -nodes -subj "/C=XX/ST=Idk/L=Idk/O=Piltover/OU=Idk/CN=localhost"
