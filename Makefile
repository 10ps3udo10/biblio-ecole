.DEFAULT_GOAL := help
PYTHON ?= python3
PORT ?= 8427
BIND ?= 127.0.0.1
HOSTS ?= localhost,127.0.0.1
SERVICE_USER ?=
DEST ?= backups

.PHONY: help setup start check admin backup service-install service-start service-stop service-status

help:
	@printf '%s\n' \
	  'make setup PYTHON=python3.12  Install dependencies, migrate, and create the first administrator' \
	  'make start                  Run this-computer-only on port 8427 (Control-C to stop)' \
	  'make start BIND=0.0.0.0 HOSTS=localhost,127.0.0.1,Library-Mac.local  Trusted LAN' \
	  'make check                  Check installation and pending migrations' \
	  'make admin                  Create an additional system administrator' \
	  'make backup DEST=backups    Create a manual database-and-media archive; stop the app first' \
	  'make service-install SERVICE_USER=library  Install macOS boot-time startup (asks for sudo)' \
	  'make service-start | service-stop | service-status  Control the macOS service' \
	  'PORT=8428 can override the port. HOSTS lists allowed browser hostnames/IPs.'

setup:
	@"$(PYTHON)" tools/local_install.py setup

start:
	@.venv/bin/python tools/local_install.py start --bind "$(BIND)" --hosts "$(HOSTS)" --port "$(PORT)"

check:
	@.venv/bin/python tools/local_install.py check

admin:
	@.venv/bin/python tools/local_install.py admin

backup:
	@.venv/bin/python tools/local_install.py backup --destination "$(DEST)"

service-install:
	@test -n "$(SERVICE_USER)" || { printf '%s\n' 'Specify the macOS account that owns the installation: SERVICE_USER=library'; exit 1; }
	@sudo .venv/bin/python tools/macos_service.py install --user "$(SERVICE_USER)" --bind "$(BIND)" --hosts "$(HOSTS)" --port "$(PORT)"

service-start service-stop service-status:
	@sudo .venv/bin/python tools/macos_service.py $(patsubst service-%,%,$@)
