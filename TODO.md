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
- [x] Dodac endpointy persystencji dla profili, ofert i wynikow matchingu
- [x] Dodac testy endpointow i persystencji na tymczasowej SQLite
- [x] Dodac minimalny frontend React + Vite dla flow `health -> parse-url -> save`
- [x] Dodac CORS dla lokalnego frontendu (`localhost:5173`)

## Aktualny stan
- [x] Routery backendowe pozostaja cienkie, a logika jest w `app/services`
- [x] Modele domenowe w `app/models` nie zostaly przebudowane pod ORM
- [x] `parse-url` i `match/analyze` nie maja ukrytych side-effectow zapisu
- [x] Baza lokalna jest ignorowana przez git (`data/*.db`)
- [x] Frontend MVP jest cienka warstwa UI nad istniejacym API
- [x] Frontend umozliwia:
  - health check backendu
  - parsowanie oferty po URL
  - podglad `JobPosting`
  - zapis oferty do SQLite

## Najblizsze kroki
- [ ] Dodac `GET /profile` do listowania zapisanych profili, jesli bedzie potrzebny frontendowi
- [ ] Dopracowac heurystyki parsera ofert dla dynamicznych portali
- [ ] Dodac AI matching jako osobna warstwe obok prostego keyword matchera
- [ ] Dodac prosty UI dla profilu kandydata
- [ ] Dodac prosty UI dla matchingu
- [ ] Przygotowac pierwsza wersje `ResumeDraft`
- [ ] Przygotowac pierwsza wersje `ChangeReport`

## Poza zakresem tego etapu
- [ ] duzy frontend z routingiem i wieloma widokami
- [ ] Docker
- [ ] Postgres
- [ ] n8n
- [ ] pelna historia uruchomien
- [ ] `GenerationRun`
- [ ] duza przebudowa architektury
