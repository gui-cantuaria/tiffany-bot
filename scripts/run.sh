#!/bin/bash
# Launch wrapper used by tiffany-bot.service.
# Prefers the project venv (Python 3.11+) and falls back to the system
# interpreter if the venv is missing — makes migration/rollback safe.

cd /opt/tiffany-bot || exit 1

if [ -x /opt/tiffany-bot/.venv/bin/python ]; then
    exec /opt/tiffany-bot/.venv/bin/python -u launcher.py
else
    exec /usr/bin/python3 -u launcher.py
fi
