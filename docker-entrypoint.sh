#!/bin/bash
set -e

APP_MODULE=${APP_MODULE:-api:app}
HOST=${HOST:-0.0.0.0}
PORT=${PORT:-5000}
WORKERS=${WORKERS:-2}
THREADS=${THREADS:-4}
TIMEOUT=${GUNICORN_TIMEOUT:-120}

echo "🖥️ Démarrage Narrando en mode serveur (VPS/container)..."

# Créer les dossiers de données
mkdir -p data/audio data/backup logs tmp

if [ "$1" = "api" ]; then
    exec gunicorn \
        --bind "${HOST}:${PORT}" \
        --workers "${WORKERS}" \
        --threads "${THREADS}" \
        --timeout "${TIMEOUT}" \
        "${APP_MODULE}"
fi

echo "➡️  Commande personnalisée: $*"
exec "$@"
