-include .env
export

# Detect OS for cross-platform venv / python paths (works in Git Bash on Windows)
ifeq ($(OS),Windows_NT)
    PY       := .venv/Scripts/python.exe
    VENV_PY  := $(shell command -v py >$(NULL) 2>&1 && echo py || echo python)
    NULL     := nul
else
    PY       := .venv/bin/python
    VENV_PY  := python3
    NULL     := /dev/null
endif

DOCKER ?= docker
PORT   := $(or $(DB_PORT),3307)

.PHONY: help setup env venv install db-up db run db-down db-shell clean

help:
	@echo "CampusBite - make targets"
	@echo "  make setup     one-shot: env + venv + install + db-up + db"
	@echo "  make run       start the website at http://127.0.0.1:5000"
	@echo "  make install   create .venv and install requirements"
	@echo "  make db-up     start a MySQL 8 Docker container (port $(PORT))"
	@echo "  make db        (re)create CampusCanteenDB and load demo data (wipes it)"
	@echo "  make db-shell  open a mysql prompt inside the container"
	@echo "  make db-down   stop the container"
	@echo "  make clean     remove .venv and caches"
	@echo "On Windows, run these targets from Git Bash (or WSL)."
	@echo "Use DOCKER='sudo docker' if your user cannot run docker."

setup: env install db-up db

env:
	@test -f .env || (cp .env.example .env && echo "Created .env - edit it if needed")

venv:
	test -d .venv || $(VENV_PY) -m venv .venv

install: venv
	$(PY) -m pip install -r requirements.txt

db-up:
	$(DOCKER) start canteen-mysql 2>$(NULL) || $(DOCKER) run -d --name canteen-mysql -p $(PORT):3306 -e MYSQL_ROOT_PASSWORD='$(DB_PASS)' mysql:8.0
	@echo "Waiting for MySQL to accept connections..."
	@until $(DOCKER) exec canteen-mysql mysqladmin ping -h 127.0.0.1 -uroot -p'$(DB_PASS)' --silent; do sleep 2; done
	@echo "MySQL is ready."

db:
	$(PY) init_db.py

run:
	$(PY) app.py

db-shell:
	$(DOCKER) exec -it canteen-mysql mysql -uroot -p'$(DB_PASS)' CampusCanteenDB

db-down:
	$(DOCKER) stop canteen-mysql

clean:
	rm -rf .venv __pycache__
