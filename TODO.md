# TODO

1. **Tour Naming Rules**
   - If a tour contains only one attraction, skip the marketing name generation and reuse the attraction’s name directly.
   - Update the naming prompt so the tour name stays short and consistent (max ~3–4 words). Make sure the new instructions are applied wherever `_assign_tour_names` is used.

2. **Deployment / Tests**
   - Run the full pipeline and deploy to the test environment once the above naming changes are in place.

3. **RPC `get_tours_by_city_place_id`**
   - Investigate why the RPC returns an incorrect first-attraction audio URL. Fix the query so the first point in each tour exposes the right translated/default audio.

4. **Regression Testing**
   - After the fixes above, run end-to-end tests (city generation → translations → audio generation) for multiple languages to ensure the realtime status and RPC responses are correct.

5. **Sentry Monitoring**
   - Provide infra docs on the new `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE` and `SENTRY_SEND_DEFAULT_PII` env vars so staging/prod can toggle error tracking easily.
