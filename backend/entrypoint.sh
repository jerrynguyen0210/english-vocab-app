#!/bin/sh
set -eu
# Failure exits the container before the API can serve against an old schema.
python -m app.migrate
exec "$@"
