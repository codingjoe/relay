FROM ghcr.io/codingjoe/relay:local-base

COPY .env /app/.env

ENTRYPOINT ["dotenvx", "run", "-f", "/app/.env", "--", "/opt/venv/bin/python"]
