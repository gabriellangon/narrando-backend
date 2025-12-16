# Deployment quick checklist (VPS + GitHub Actions)

## 1) Prep the VPS (as root)
```bash
adduser --disabled-password --gecos "" deploy
usermod -aG docker deploy        # allow docker without sudo
usermod -aG sudo deploy          # optional, only if you want sudo

# SSH key: from your laptop, scp your public key then install it
scp ~/.ssh/id_ed25519.pub root@api.narrando.app:/tmp/id_ed25519.pub
install -d -o deploy -g deploy -m 700 /home/deploy/.ssh
tee /home/deploy/.ssh/authorized_keys >/dev/null < /tmp/id_ed25519.pub
chown deploy:deploy /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys
rm /tmp/id_ed25519.pub
```

## 2) App directories and permissions
```bash
install -d -o deploy -g deploy -m 755 /srv/narrando-staging /srv/narrando
install -d -o deploy -g deploy -m 755 /srv/narrando-staging/{data,logs} /srv/narrando/{data,logs}
```
Place a full `.env` in each app dir (`/srv/narrando-staging/.env` and `/srv/narrando/.env`).

## 3) (Recommended) Create GitHub environments
```bash
gh api repos/gabriellangon/narrando-backend/environments/staging -X PUT
gh api repos/gabriellangon/narrando-backend/environments/production -X PUT
```

## 4) Set environment-scoped secrets (GHCR/VPS SSH)
```bash
# staging
gh secret set STAGING_SSH_KEY  --repo gabriellangon/narrando-backend --env staging < ~/.ssh/id_ed25519
gh secret set STAGING_SSH_USER --repo gabriellangon/narrando-backend --env staging --body "deploy"
gh secret set STAGING_SSH_HOST --repo gabriellangon/narrando-backend --env staging --body "api.narrando.app"
gh secret set STAGING_SSH_PORT --repo gabriellangon/narrando-backend --env staging --body "22"
gh secret set STAGING_APP_DIR  --repo gabriellangon/narrando-backend --env staging --body "/srv/narrando-staging"

# production
gh secret set PROD_SSH_KEY  --repo gabriellangon/narrando-backend --env production < ~/.ssh/id_ed25519
gh secret set PROD_SSH_USER --repo gabriellangon/narrando-backend --env production --body "deploy"
gh secret set PROD_SSH_HOST --repo gabriellangon/narrando-backend --env production --body "api.narrando.app"
gh secret set PROD_SSH_PORT --repo gabriellangon/narrando-backend --env production --body "22"
gh secret set PROD_APP_DIR  --repo gabriellangon/narrando-backend --env production --body "/srv/narrando"
```

## 5) If you prefer repo-level secrets (no environments)
```bash
gh secret set STAGING_SSH_KEY  --repo gabriellangon/narrando-backend < ~/.ssh/id_ed25519
gh secret set STAGING_SSH_USER --repo gabriellangon/narrando-backend --body "deploy"
gh secret set STAGING_SSH_HOST --repo gabriellangon/narrando-backend --body "api.narrando.app"
gh secret set STAGING_SSH_PORT --repo gabriellangon/narrando-backend --body "22"
gh secret set STAGING_APP_DIR  --repo gabriellangon/narrando-backend --body "/srv/narrando-staging"

gh secret set PROD_SSH_KEY  --repo gabriellangon/narrando-backend < ~/.ssh/id_ed25519
gh secret set PROD_SSH_USER --repo gabriellangon/narrando-backend --body "deploy"
gh secret set PROD_SSH_HOST --repo gabriellangon/narrando-backend --body "api.narrando.app"
gh secret set PROD_SSH_PORT --repo gabriellangon/narrando-backend --body "22"
gh secret set PROD_APP_DIR  --repo gabriellangon/narrando-backend --body "/srv/narrando"
```

## 6) Quick checks
- SSH: `ssh -i ~/.ssh/id_ed25519 deploy@api.narrando.app` (doit passer sans mot de passe).
- Docker group: `sudo -u deploy docker ps` doit marcher sans sudo.
- Ports: prod écoute 5000, staging 5001 (reverse proxy/firewall à ouvrir si besoin).

## 7) Déployer
- Push sur `staging` ou `main`, ou lancer `workflow_dispatch` avec l’environnement voulu.
- Les jobs `deploy-*-vps` pull l’image GHCR et relancent les conteneurs : `narrando-api-staging` (5001) et `narrando-api-prod` (5000).
