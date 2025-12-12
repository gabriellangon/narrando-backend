# 🚀 Plan de Migration : AWS Lambda → AWS Fargate + Docker

## 📋 Résumé de la Discussion

**Problème identifié :**
- Les AWS Lambda ne sont **PAS adaptées** au code Narrando existant
- Complexité des clients Python (GoogleMapsClient, PerplexityClient, RouteOptimizer)  
- Dépendances lourdes et timeouts (15min max)
- Conflits de versions et problèmes de compatibilité
- Code existant fonctionne parfaitement en local - pas besoin de le modifier

**Solution retenue : AWS Fargate + Docker**
- ✅ **Pay-per-use** comme Lambda (scale à zéro = 0€ au repos)
- ✅ **Containers Docker** - code Python existant sans modification
- ✅ **Pas de timeout** - peut tourner des heures
- ✅ **Auto-scaling** intelligent
- ✅ **Déploiement simple** via AWS Copilot CLI

---

## 🎯 Architecture Finale

### Serveur API Python (Nouveau)
**Port d'entrée unique** qui reçoit les requêtes et orchestre le processing :

```python
# api_server.py - NOUVEAU FICHIER À CRÉER
@app.post('/api/generate-city')
def generate_city(request: CityRequest):
    place_id = request.place_id  # INPUT: Place ID de la ville
    
    # Utiliser EXACTEMENT le code existant
    city_info = GoogleMapsClient().get_city_info_by_place_id(place_id)
    attractions = GoogleMapsClient().search_tourist_attractions(...)
    filtered = PerplexityClient().filter_attractions(...)
    optimized = RouteOptimizer().optimize_route(...)
    
    # Sauvegarder en Supabase
    city_id = SupabaseMigrator().migrate_route_data(...)
    
    return {"success": True, "city_id": city_id}
```

### Containerisation Docker
```dockerfile
# Dockerfile - NOUVEAU FICHIER À CRÉER
FROM python:3.13
COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt
EXPOSE 8080
CMD ["python", "api_server.py"]
```

### Déploiement AWS Fargate
```bash
# Via AWS Copilot CLI (plus simple)
copilot app init narrando-backend
copilot svc init --name api --svc-type "Backend Service"
copilot svc deploy
```

---

## 📁 Fichiers à Créer

### 1. `/api_server.py` (PRIORITÉ 1)
Serveur Flask/FastAPI qui :
- Reçoit les requêtes HTTP avec `place_id`
- Utilise **EXACTEMENT** les clients existants (GoogleMapsClient, PerplexityClient, RouteOptimizer)
- Orchestration identique à `main.py`
- Retourne les résultats en JSON

### 2. `/Dockerfile` (PRIORITÉ 1)
Configuration Docker pour containeriser l'application

### 3. `/copilot/` (PRIORITÉ 2)
Configuration AWS Copilot pour déploiement Fargate
- `copilot/api/copilot.yml` - Config du service
- `copilot/environments/production/addons/` - Resources AWS additionnelles

### 4. `/.dockerignore` (PRIORITÉ 3)
Exclusions pour le build Docker

---

## 🔄 Flux de Données Final

```
Client Mobile/Web
    ↓ POST /api/generate-city {"place_id": "ChIJ..."}
AWS Fargate Container (Auto-scaling)
    ↓ place_id
GoogleMapsClient.get_city_info_by_place_id()
    ↓ city_info
GoogleMapsClient.search_tourist_attractions()
    ↓ attractions[]
PerplexityClient.filter_attractions()
    ↓ filtered_attractions[]  
RouteOptimizer.optimize_route()
    ↓ optimized_route{}
SupabaseMigrator.migrate_route_data()
    ↓ city_id
Response {"success": true, "city_id": "uuid"}
```

---

## 💰 Coûts Estimés

**AWS Fargate Pricing :**
- Scale à **zéro** quand pas utilisé = **0€**
- Pendant exécution : ~0.05€ par requête (30min processing)
- Auto-scale selon la demande
- **Beaucoup plus économique** que des serveurs 24/7

---

## ⚡ Avantages vs Lambdas

| Critère | AWS Lambda | AWS Fargate |
|---------|------------|-------------|
| **Timeout** | 15 min MAX ❌ | Illimité ✅ |
| **Code existant** | Modifications requises ❌ | Tel quel ✅ |
| **Dépendances** | Limitations ❌ | Docker = tout marche ✅ |
| **Cost-effectiveness** | Pay-per-invoke ✅ | Pay-per-use ✅ |
| **Cold start** | Long avec gros packages ❌ | Rapide ✅ |
| **Debugging** | Compliqué ❌ | Comme en local ✅ |

---

## 📝 Étapes d'Implémentation

### Phase 1 : Préparation (1-2h)
1. ✅ Créer `api_server.py` avec endpoint `/api/generate-city`
2. ✅ Tester en local : `python api_server.py`
3. ✅ Créer `Dockerfile` et tester : `docker build -t narrando .`

### Phase 2 : Déploiement (1h) 
1. ✅ Installer AWS Copilot CLI
2. ✅ `copilot app init narrando-backend`
3. ✅ `copilot svc init --name api`
4. ✅ `copilot svc deploy`

### Phase 3 : Configuration (30min)
1. ✅ Variables d'environnement (API keys)
2. ✅ Auto-scaling à zéro
3. ✅ Health checks
4. ✅ Tests de charge

---

## 🔧 Configuration Auto-Scaling

```yaml
# copilot/api/copilot.yml
name: api
type: Backend Service

http:
  path: '/api'

image:
  build: './Dockerfile'

secrets:
  - GOOGLE_PLACES_API_KEY
  - PERPLEXITY_API_KEY  
  - SUPABASE_URL
  - SUPABASE_SERVICE_KEY

count:
  min: 0  # Scale à zéro !
  max: 10
  auto_scaling:
    target_cpu: 70
    target_memory: 80
```

---

## 🚀 Résultat Final

**API REST professionnelle :**
- `POST https://api.narrando.com/api/generate-city`
- Input : `{"place_id": "ChIJD7fiBh9u5kcRYJSMaMOCCwQ"}`
- Output : `{"success": true, "city_id": "uuid", "tours": 4}`
- **Auto-scaling** : 0 instance au repos → N instances sous charge
- **Code identique** à main.py - **ZERO modification**
- **Déploiement simple** avec Copilot

---

## 🎯 Prochaines Actions

1. **Créer api_server.py** - serveur qui utilise les clients existants
2. **Docker setup** - containerisation de l'app  
3. **AWS Copilot** - déploiement sur Fargate
4. **Tests** - validation du pipeline complet

**Cette solution respecte parfaitement votre code existant tout en étant économique et scalable !**