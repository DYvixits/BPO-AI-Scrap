#!/bin/sh
set -e

echo "Waiting for database migrations..."
alembic upgrade head

exec "$@"
