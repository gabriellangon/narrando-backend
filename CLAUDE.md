# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Narrando is a POC for an AI-powered autonomous audio-guided tour application. The system discovers tourist attractions using Google Maps, filters them with Perplexity AI, and optimizes walking routes between points of interest.

## Development Commands

### Environment Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env  # (if .env doesn't exist)
# Edit .env with your API keys
```

### Running the Application

**Main tour generation script:**
```bash
# Generate full tour for a city
python main.py --ville "Paris" --pays "France" --max 30

# Common options:
python main.py -v "Paris" -p "France" -m 15 --indiv
python main.py -v "Avignon" -p "France" --quick  # Use existing filtered data
python main.py -v "Toulouse" -p "France" --skip-search --filtrage-standard
```

**Web server (for local testing):**
```bash
python start_server.py
# Access at http://localhost:8000/web/tours_map.html
```

**Mobile API server:**
```bash
python api/mobile_api.py
# Runs on http://localhost:5000
```

### Database Operations
```bash
# V1 Migrations (legacy)
python database/migrate_to_supabase.py
python database/migrate_to_supabase_with_tours.py

# Migration (respecte le schéma existant - RECOMMANDÉ)
python database/migrate_to_supabase.py

# Migrer un fichier spécifique
python -c "from database.migrate_to_supabase import SupabaseMigrator; SupabaseMigrator().migrate_route_data('path/to/file.json')"
```

## Architecture

### Core Components

**main.py**: Entry point that orchestrates the complete tour generation pipeline:
1. Search attractions via Google Maps API
2. Filter attractions using Perplexity AI (individual or batch mode)
3. Optimize walking route between selected attractions
4. Generate guided tour segments and walking paths

**Client Architecture** (`clients/`):
- `google_maps_client.py`: Google Maps Places API integration for attraction search and city info
- `perplexity_client.py`: AI filtering of attractions for relevance and tourist value
- `route_optimizer_client.py`: Route optimization and walking path generation

**Mobile API** (`api/mobile_api.py`):
- Flask REST API for mobile application
- Automatic tour generation if data doesn't exist
- Supabase integration for data persistence
- Google Maps mobile-compatible data formatting

**Database Layer** (`database/`):
- Supabase integration with complete schema (`supabase_models.sql`)
- Migration scripts for local data to cloud database
- Support for guided tours, walking paths, and user management

### Data Flow

1. **Attraction Discovery**: Google Maps search → raw attraction list (`data/attractions.json`)
2. **AI Filtering**: Perplexity analysis → filtered attractions (`data/filtered_attractions.json`) 
3. **Route Optimization**: TSP algorithm → optimized route with walking paths (`data/optimized_route.json`)
4. **Database Sync**: Migration to Supabase for mobile app consumption
5. **Mobile API**: REST endpoints serving formatted data to mobile applications

### Key Data Formats

**Filtered attractions** support two filtering methods:
- `--filtrage-individuel`: Individual AI analysis per attraction (default, more accurate)
- `--filtrage-standard`: Batch processing of all attractions

**Route optimization** produces:
- Ordered attraction sequence minimizing walking distance
- Detailed walking paths with GPS coordinates between points
- Guided tour segments (max 15min walking between attractions)
- Integration with Google Maps mobile polylines

## Environment Variables

Required in `.env`:
```bash
GOOGLE_PLACES_API_KEY=your_key_here
PERPLEXITY_API_KEY=your_key_here
SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_KEY=your_service_key

# Text-to-Speech (NEW - V2.0)
TTS_PROVIDER=openai  # ou 'elevenlabs'
OPENAI_API_KEY=your_openai_key_here
```

Optional:
```bash
MAPBOX_API_KEY=your_mapbox_key
OPENTRIPMAP_API_KEY=your_opentripmap_key
FOURSQUARE_API_KEY=your_foursquare_key

# ElevenLabs TTS (optionnel)
ELEVENLABS_API_KEY=your_elevenlabs_key
```

**⚡ NEW - Version 2.0 : Architecture TTS modulaire**
- Support d'OpenAI TTS (par défaut) et ElevenLabs
- Coût réduit de 5-10x avec OpenAI
- Switch facile entre providers via `TTS_PROVIDER`
- Documentation complète dans `docs/README_TTS.md`

## API Endpoints

**Mobile API** (`/api/`):
- `GET /api/tours?city=<city>&country=<country>` - Get or generate tour data
- `GET /api/health` - Service health check
- `GET /api/cities` - List available cities
- `POST /api/invitations/accept` - Accept tour invitation
- `POST /api/tours/start` - Start guided tour for participant
- `POST /api/tours/complete` - Complete guided tour

## Database Schema

**Core Tables**:
- `cities`: City metadata and route statistics
- `attractions`: POIs with AI descriptions and Google Places data
- `guided_tours`: Tour segments with timing constraints
- `tour_points`: Ordered attractions within tours
- `walking_paths`: Detailed GPS paths between attractions

**User Management**:
- `tour_purchases`: Tour purchases and sharing
- `tour_invitations`: Invitation system for shared tours
- `tour_participants`: User participation tracking

## Common Patterns

**Backup Strategy**: All generated data is saved both in working files (`data/`) and timestamped backups (`data/backup/`) with city-country naming convention.

**Error Handling**: Each client implements retry logic and graceful degradation. The mobile API falls back to local JSON files if Supabase is unavailable.

**Mobile Integration**: Data is formatted specifically for Google Maps mobile SDK with proper coordinate structures and polyline support.
