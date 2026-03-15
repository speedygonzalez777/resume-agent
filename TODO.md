# TODO - Resume Tailoring Agent

## Zrobione
- [x] Utworzyc backend FastAPI z modelami domenowymi MVP
- [x] Dodac `POST /profile/validate`
- [x] Dodac `POST /job/validate`
- [x] Dodac `POST /match/analyze`
- [x] Uporzadkowac matching tak, aby `/match/analyze` zwracal `MatchResult` i `RequirementMatch`
- [x] Dodac explainability dla `RequirementMatch`
- [x] Dodac URL-first parser ofert pracy `POST /job/parse-url`
- [x] Dodac jawne bledy parsera ofert:
  - `fetch_failed`
  - `page_content_too_poor`
  - `ai_parsing_failed`
  - `parsed_result_incomplete`
- [x] Dodac HTTP-first fetch i lokalny browser fallback dla trudniejszych stron
- [x] Dodac minimalna lokalna persystencje SQLite w `app/db`
- [x] Ustawic domyslna baze na `data/resume_agent.db`
- [x] Wywolywac `init_db()` jawnie przy starcie aplikacji
- [x] Trzymac `CandidateProfile`, `JobPosting` i `MatchResult` jako JSON w SQLite
- [x] Dodac endpointy persystencji:
  - `POST /profile/save`
  - `GET /profile/{profile_id}`
  - `POST /job/save`
  - `GET /job`
  - `GET /job/{job_posting_id}`
  - `POST /match/save`
  - `GET /match`
  - `GET /match/{match_result_id}`
- [x] Dodac testy endpointow i persystencji na tymczasowej SQLite

## Aktualny stan
- [x] Routery pozostaja cienkie, a logika jest w `app/services`
- [x] Modele domenowe w `app/models` nie zostaly przebudowane pod ORM
- [x] `parse-url` i `match/analyze` nie maja ukrytych side-effectow zapisu
- [x] Baza lokalna jest ignorowana przez git (`data/*.db`)
- [x] Backend jest przygotowany pod przyszly frontend przez proste endpointy zapisu i odczytu

## Najblizsze kroki
- [ ] Dodac `GET /profile` do listowania zapisanych profili, jesli bedzie potrzebny frontendowi
- [ ] Zdecydowac, czy frontend ma zapisywac wynik `parse-url` i `match/analyze` jawnie po stronie UI, czy przez dodatkowy backend flow
- [ ] Dopracowac heurystyki parsera ofert dla dynamicznych portali
- [ ] Dodac AI matching jako osobna warstwe obok prostego keyword matchera
- [ ] Przygotowac pierwsza wersje `ResumeDraft`
- [ ] Przygotowac pierwsza wersje `ChangeReport`

## Poza zakresem tego etapu
- [ ] frontend / UI
- [ ] Docker
- [ ] Postgres
- [ ] n8n
- [ ] pelna historia uruchomien
- [ ] `GenerationRun`
- [ ] duza przebudowa architektury
