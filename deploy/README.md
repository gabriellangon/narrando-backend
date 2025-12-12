# Déploiement VPS (Docker)

## Prérequis
- Docker + plugin Compose sur la machine cible
- Fichier `.env` complet (API_TOKEN, clés AWS S3, clés OpenAI/Perplexity, SENTRY_DSN éventuel)
- Ports 80/443 exposés si vous placez un reverse proxy devant l'API (compose fournit un service `nginx` en profile `production`)

## Lancer l'API sur un VPS
1) Copier le repo et le `.env` sur le serveur  
2) `docker compose up -d --build narrando-api` (ou `docker compose --profile production up -d` si vous activez nginx)  
3) Vérifier la santé: `curl http://localhost:5000/health`  
4) Logs runtime: `docker compose logs -f narrando-api`

Les données locales (audios, backups, logs) vivent dans `./data` et `./logs` montés par Compose.

## Script AWS hérité
Le script `deploy-aws.sh` reste présent pour l'ancien flux EC2 automatisé, mais n'est plus requis pour un VPS standard.
