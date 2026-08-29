.PHONY: setup test demo api broker broker-down mock-device mqtt-demo hardware-status

setup:
	UV_CACHE_DIR=.uv-cache uv sync

test:
	UV_CACHE_DIR=.uv-cache uv run pytest

demo:
	UV_CACHE_DIR=.uv-cache uv run python scripts/run_scenario.py success

api:
	UV_CACHE_DIR=.uv-cache uv run uvicorn goodnight_agent.api.app:app --reload

broker:
	docker compose up -d broker

broker-down:
	docker compose down

mock-device:
	UV_CACHE_DIR=.uv-cache uv run python scripts/mock_mqtt_device.py

mqtt-demo:
	UV_CACHE_DIR=.uv-cache uv run python scripts/run_scenario.py success --transport mqtt

hardware-status:
	@UV_CACHE_DIR=.uv-cache uv run --env-file .env.hardware python scripts/check_env_s3_connection.py
