# Dockerfile pour Narrando API - runtime VPS/containers (sans Lambda)
FROM python:3.11-slim

# Définir le répertoire de travail
WORKDIR /app

# Copier les fichiers de requirements
COPY requirements.txt .

# Installer les dépendances système nécessaires
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Installer les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code source
COPY . .

# Créer les dossiers nécessaires
RUN mkdir -p data/audio data/backup logs tmp

# Chemin de données persistant pour le VPS
ENV NARRANDO_DATA_PATH=/app/data

# Variables d'environnement par défaut
ENV FLASK_APP=api.py
ENV FLASK_ENV=production
ENV PORT=5000
ENV PYTHONPATH=/app

# Exposer le port
EXPOSE 5000

# Vérification de santé
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:${PORT:-5000}/health || exit 1

# Script d'entrée pour lancer l'API en mode serveur
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Commande par défaut
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["api"]
