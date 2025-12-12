# Spécification de l'Algorithme du Plus Court Chemin pour Narrando

## Objectif
Créer un algorithme qui détermine le plus court chemin pour visiter toutes les attractions touristiques filtrées, en partant du point le plus excentré.

## Contexte
Dans le cadre du projet Narrando, après avoir récupéré et filtré les attractions touristiques d'une ville via l'API Google Maps et l'API Perplexity, nous devons maintenant optimiser l'itinéraire de visite pour les touristes.

## Problème à résoudre
Le problème est une variante du "Problème du Voyageur de Commerce" (TSP - Traveling Salesman Problem) avec les spécificités suivantes :
- Le point de départ est fixé (le point le plus excentré)
- Tous les points (attractions) doivent être visités une et une seule fois
- La distance à minimiser est la distance de marche réelle (pas la distance à vol d'oiseau)
- Le retour au point de départ n'est pas obligatoire (chemin hamiltonien)

## Approche proposée

### 1. Détermination du point de départ
- Calculer le centroïde de tous les points (moyenne des coordonnées)
- Pour chaque point, calculer sa distance au centroïde
- Sélectionner le point ayant la plus grande distance au centroïde comme point de départ

### 2. Calcul de la matrice de distances
- Pour chaque paire de points (i, j), calculer la distance de marche réelle entre i et j
- Utiliser l'API Google Directions pour obtenir les distances de marche précises
- Stocker ces distances dans une matrice de distances
- Mettre en place un système de cache pour éviter de recalculer les mêmes distances

### 3. Algorithme de résolution du TSP
Plusieurs approches possibles, par ordre de complexité croissante :

#### Option 1 : Algorithme glouton (nearest neighbor)
- Commencer par le point de départ
- À chaque étape, choisir le point non visité le plus proche
- Continuer jusqu'à ce que tous les points soient visités
- Complexité : O(n²), mais solution sous-optimale

#### Option 2 : Algorithme 2-opt
- Commencer par une solution initiale (ex: nearest neighbor)
- Améliorer itérativement la solution en échangeant deux arêtes si cela réduit la distance totale
- Continuer jusqu'à ce qu'aucune amélioration ne soit possible
- Complexité : O(n²) par itération, mais meilleure qualité de solution

#### Option 3 : Programmation dynamique (Held-Karp)
- Résoudre le problème de manière optimale en utilisant la programmation dynamique
- Complexité : O(n² × 2ⁿ), optimal mais très coûteux pour n > 20

### 4. Implémentation recommandée
Pour un nombre raisonnable d'attractions (< 30) :
1. Utiliser l'algorithme nearest neighbor pour obtenir une solution initiale
2. Améliorer cette solution avec l'algorithme 2-opt
3. Limiter le nombre d'itérations pour garantir des performances acceptables

## Contraintes techniques
- Gestion des quotas d'API Google Directions (limités)
- Mise en cache des résultats pour optimiser les appels API
- Gestion des erreurs et fallback sur la distance à vol d'oiseau en cas d'échec de l'API

## Format des données

### Entrée
```json
{
  "filtered_attractions": [
    {
      "name": "Attraction 1",
      "geometry": {
        "location": {
          "lat": 43.9508521,
          "lng": 4.8076971
        }
      },
      "formatted_address": "Adresse 1"
    },
    // ... autres attractions
  ]
}
```

### Sortie
```json
{
  "optimized_route": [
    {
      "index": 5,  // Index dans le tableau original
      "name": "Attraction 6",
      "location": {
        "lat": 43.9508521,
        "lng": 4.8076971
      },
      "distance_from_previous": 0  // En mètres (0 pour le premier point)
    },
    {
      "index": 2,
      "name": "Attraction 3",
      "location": {
        "lat": 43.9498521,
        "lng": 4.8066971
      },
      "distance_from_previous": 250  // En mètres
    },
    // ... autres attractions dans l'ordre optimal
  ],
  "total_distance": 3500,  // Distance totale en mètres
  "estimated_walking_time": 45  // Temps estimé en minutes
}
```

## Considérations futures
- Intégration de contraintes temporelles (heures d'ouverture des attractions)
- Prise en compte de pauses (déjeuner, café)
- Adaptation à différents modes de transport (marche, vélo, transports en commun)
- Optimisation multi-objectifs (distance vs intérêt des attractions)
