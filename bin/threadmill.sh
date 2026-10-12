#!/usr/bin/env sh

TASK_REDIS_URL="rediss://:$(dotenvx get REDIS_PASSWORD -f .env.production)@redis-tasks.$(dotenvx get HOSTNAME -f .env.production):443" uv run --group=dev python manage.py threadmill inspector
