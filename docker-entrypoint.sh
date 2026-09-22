#!/bin/sh
set -eu

chown agent:agent /app/data
exec su -s /bin/sh agent -c "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
