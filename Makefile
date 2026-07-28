MIGRATION_PACKAGES = $(wildcard */migrations/__init__.py)
MIGRATIONS = $(wildcard */migrations/[!_]*.py*)
PYTHON = $(shell command -v python3)

.PHONY: migrations clear-migrations squash-migrations

migrations:
	$(PYTHON) manage.py makemigrations

clear-migrations:
	rm ${MIGRATIONS}

squash-migrations:
	psql $(LOCAL_TABLE_NAME) -a -c "TRUNCATE TABLE django_migrations"
	$(MAKE) migrations
	$(PYTHON) manage.py migrate --fake --no-input
