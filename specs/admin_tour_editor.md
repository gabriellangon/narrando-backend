# Admin Tour Editor – Spécification Fonctionnelle

## 1. Objectif
Créer une interface web d’administration permettant de :
- lister les villes puis leurs tours existants ;
- visualiser chaque tour sur Google Maps (points + polylignes) ;
- réordonner manuellement les attractions d’un tour (choix du point de départ / arrivée inclus) ;
- valider les changements pour écraser l’ordre `tour_points` et recalculer les `walking_paths` ;
- supprimer proprement une attraction si nécessaire (avec ses traductions et liens).

Cette interface sert d’outil interne pour ajuster les itinéraires quand l’algorithme automatique n’est pas satisfaisant.

## 2. Contexte existant
- **Schéma Supabase** – tables principales : `cities`, `guided_tours`, `tour_points`, `attractions`, `walking_paths`, traductions (`*_translations`). Voir `database/database.sql` pour les colonnes et contraintes (ex. `tour_points` : `database/database.sql:349`).
- **RPC disponibles** (`database/supabase_rpc.json`) :
  - `get_city_tours_map` ou `get_tours_by_city_place_id` pour lister les tours d’une ville.
  - `get_complete_tour_with_attractions` / `get_complete_tour_with_walking_paths` pour récupérer un tour + points + segments prêts à afficher.
- **API Python** (`api.py`) : déjà configurée avec Supabase et Google, pourra héberger les nouveaux endpoints d’admin si besoin.

## 3. Architecture proposée
1. **Frontend** (Tailwind + Vanilla JS) hébergé dans `web/` :
   - Auth simple (token admin dans `.env` ou Basic Auth) suffisant pour usage interne.
   - Appels directs au PostgREST Supabase (service role) **ou** passage par `api.py` pour encapsuler la logique sensible.
2. **Backend** :
   - Réutiliser les RPCs pour la lecture (villes/tours/points).
   - Ajouter des endpoints REST côté `api.py` pour les actions critiques :
     - `POST /admin/tours/{tour_id}/reorder`
     - `DELETE /admin/attractions/{attraction_id}`
   - Ces endpoints utiliseront la clé service-role côté serveur, jamais exposée au front.

## 4. Parcours utilisateur
1. **Sélection ville**
   - Dropdown alimenté par `SELECT id, city, country FROM cities ORDER BY city`.
   - Option de recherche par nom.
2. **Liste des tours pour la ville**
   - Affichage type carte ou liste : nom du tour, nb de points, distance, temps (`guided_tours`).
   - Clic ouvre l’éditeur.
3. **Éditeur de tour**
   - **Colonne gauche** : liste ordonnée des attractions (carte, adresse, bouton delete). Drag & drop (lib `@dnd-kit` ou `react-beautiful-dnd`). Alternative fallback : champs numériques pour définir la position.
   - **Carte Google Maps** : markers numérotés + polyline utilisant `walking_paths`.
   - **Footer** : boutons `Réinitialiser`, `Sauvegarder l’ordre`, `Recalculer chemin`, `Supprimer attraction`.

## 5. Logique de réordonnancement
### Frontend
1. L’utilisateur réorganise la liste → nouvel array d’IDs.
2. Bouton « Valider l’ordre » envoie `PATCH /admin/tours/{tour_id}/reorder` avec :
   ```json
   {
     "ordered_attraction_ids": ["uuid1", "uuid2", "..."],
     "deleted_attraction_ids": [],
     "start_attraction_id": "uuid1",
     "end_attraction_id": "uuidN"
   }
   ```

### Backend (`api.py`)
1. Vérifie que tous les IDs appartiennent à `tour_id`.
2. Commence une transaction :
   - Supprime les `tour_points` existants du tour.
   - Réinsère les lignes avec `point_order` séquentiels, `global_index` mis à jour.
   - Recalcule les stats du tour :
     - Pour chaque paire consécutive, appelle les mêmes services que `RouteOptimizer._get_walking_distance_cached` pour récupérer la distance + polyline (Google Directions, fallback euclidien).
     - Met à jour/insère dans `walking_paths` (`tour_id`, `from_attraction_id`, `to_attraction_id`, `path_coordinates`).
     - Met à jour `guided_tours.total_distance`, `estimated_walking_time`, `start_point`, `end_point`.
3. Commit et renvoie la version actualisée du tour (peut réutiliser `get_complete_tour_with_walking_paths`).

### Points techniques
- Réutiliser la logique de cache déjà présente dans `RouteOptimizer` si possible (extraction dans un helper commun).
- Ajouter un petit throttling côté API pour ne pas dépasser les quotas Google si beaucoup de permutations successives.
- Prévoir un flag `dry_run=true` pour tester l’ordre sans toucher la base (utile pour debug).

## 6. Suppression d’une attraction
1. Bouton « Supprimer » à côté de chaque POI.
2. Confirmation modale rappelant les impacts (supprime toutes les traductions, audios, walking_paths adjacents).
3. Endpoint `DELETE /admin/attractions/{id}` :
   - Supprime `tour_points` associés (cascade déjà en place via FK).
   - Supprime les `walking_paths` où `from_attraction_id` ou `to_attraction_id` = id (FK cascade gère aussi).
   - Supprime l’attraction et ses traductions (`attraction_translations` cascade).
   - Déclenche un recalcul automatique du tour pour conserver un chemin valide (réutilise la logique §5).

## 7. Datasources / RPC à consommer
| Besoin | RPC / Table | Notes |
| --- | --- | --- |
| Liste des villes | `cities` (direct) | peu de colonnes, pas besoin de RPC |
| Tours d’une ville | `get_city_tours_map` ou `get_tours_by_city_place_id` | choisir selon clé disponible (id vs place_id) |
| Détails d’un tour | `get_complete_tour_with_walking_paths` | inclut attractions + segments pour afficher la carte |
| Sauvegarde ordre | Nouveau endpoint `POST /admin/tours/{id}/reorder` | encapsule la logique critique |
| Suppression attraction | Nouveau endpoint `DELETE /admin/attractions/{id}` | pour gérer les cascades côté serveur |

## 8. Roadmap suggérée
1. **Backend**
   - [ ] Créer blueprint Flask `admin_routes.py` avec auth simple (token).
   - [ ] Implémenter les deux endpoints (`reorder`, `delete attraction`) + helpers de recalcul.
   - [ ] Tests unitaires pour la transaction Supabase (utiliser PostgREST local ou mocks).
2. **Frontend**
   - [ ] Setup bundle statique (Tailwind + Vanilla JS).
   - [ ] Écran sélection ville/tour.
   - [ ] Éditeur avec drag & drop + Google Maps JS API (lib légère type SortableJS).
   - [ ] Intégrer appels aux endpoints d’admin.
3. **Ops**
   - [ ] Stocker les clés (Supabase service role, Google Maps JS & Directions) dans `.env` et ne jamais les exposer côté client.
   - [ ] Ajouter doc utilisateur (capture écran + guide).

## 9. Points ouverts
- Faut-il maintenir un historique des permutations ? → proposer une table `tour_point_revisions`.
- Gestion des traductions après suppression d’un point : cascade suffit mais prévoir un script pour nettoyer les audios sur S3.
- Droit d’accès : limiter l’interface à un groupe restreint (auth basique ou SSO).

Ce README servira de base pour la prochaine session afin d’implémenter concrètement l’éditeur.
