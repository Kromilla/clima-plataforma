# Atajos de desarrollo. Requiere `make` (viene en macOS/Linux y en Git Bash).
# En Windows sin make, los pasos manuales siguen en CONTRIBUTING.md.
.PHONY: install test lint api dashboard collector bot dev

## install — dependencias de Python y del dashboard
install:
	pip install -r requirements.txt
	npm install --prefix dashboard-ui

## test — suite de Python + build del dashboard
test:
	pytest -q
	npm run build --prefix dashboard-ui

## lint — ruff (Python) + oxlint (dashboard)
lint:
	ruff check . --select E,F,W --ignore E501
	npm run lint --prefix dashboard-ui

## api / dashboard / collector / bot — cada servicio por separado
api:
	python api.py
dashboard:
	npm run dev --prefix dashboard-ui
collector:
	python collector.py
bot:
	python bot.py

## dev — API (:8000) + collector + dashboard (:5173) juntos; Ctrl-C detiene todo
dev:
	@echo "API :8000 · dashboard :5173 · collector — Ctrl-C detiene todo"
	@trap 'kill 0' INT TERM EXIT; \
	python api.py & \
	python collector.py & \
	npm run dev --prefix dashboard-ui & \
	wait
