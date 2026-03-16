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
- [x] Dodac `GET /profile` do listowania zapisanych profili
- [x] Dodac testy endpointow i persystencji na tymczasowej SQLite
- [x] Dodac minimalny frontend React + Vite dla flow `health -> parse-url -> save`
- [x] Dodac historie zapisanych ofert, szczegoly wybranego `JobPosting` i usuwanie rekordow
- [x] Dodac zakladke `Profil kandydata` z sekcyjnym formularzem, zapisem, historia profili i usuwaniem rekordow
- [x] Dodac zakladke `Matching` z wyborem zapisanej oferty i profilu oraz widokiem `MatchResult`
- [x] Dodac CORS dla lokalnego frontendu (`localhost:5173`)
- [x] Zmienic scoring matchingu na weighted score oparty o `importance`, `requirement_type` i `match_status`
- [x] Dodac proste gating rules dla brakujacych krytycznych `must_have`
- [x] Dodac maly fix graceful shutdown dla zasobow SQLite
- [x] Ujednolicic podstawowy shell zakladek i glownych paneli frontendu

## Aktualny stan
- [x] Routery backendowe pozostaja cienkie, a logika jest w `app/services`
- [x] Modele domenowe w `app/models` nie zostaly przebudowane pod ORM
- [x] `parse-url` i `match/analyze` nie maja ukrytych side-effectow zapisu
- [x] Baza lokalna jest ignorowana przez git (`data/*.db`)
- [x] Frontend MVP jest cienka warstwa UI nad istniejacym API
- [x] Frontend ma trzy zakladki:
  - `Oferty pracy`
  - `Profil kandydata`
  - `Matching`
- [x] Frontend umozliwia:
  - health check backendu
  - parsowanie oferty po URL
  - zapis oferty do SQLite
  - przeglad i usuwanie historii zapisanych ofert
  - podglad szczegolow wybranej zapisanej oferty
  - uzupelnianie `CandidateProfile` przez sekcyjny formularz
  - przeglad historii zapisanych profili
  - usuwanie zapisanych profili
  - podglad wybranego profilu
  - uruchomienie `POST /match/analyze`
  - czytelny podglad `MatchResult`
  - zapis wyniku przez `POST /match/save`

## Najblizsze kroki
- [ ] Dopracowac heurystyki parsera ofert dla dynamicznych portali
- [ ] Dodac AI matching jako osobna warstwe obok prostego keyword matchera
- [ ] Dodac prosty UI dla historii zapisanych wynikow matchingu
- [ ] Dodac import profilu z pliku lub jawne wczytywanie z JSON jako osobny tryb zaawansowany
- [ ] Dodac wybor zapisanych rekordow jako wejscia do kolejnych etapow pracy w UI
- [ ] Dostroic progi i gating matchingu na podstawie realnych ofert i profili testowych
- [ ] Przygotowac pierwsza wersje `ResumeDraft`
- [ ] Przygotowac pierwsza wersje `ChangeReport`

## Poza zakresem tego etapu
- [ ] duzy frontend z ciezkim routingiem i rozbudowanym design systemem
- [ ] Docker
- [ ] Postgres
- [ ] n8n
- [ ] pelna historia uruchomien
- [ ] `GenerationRun`
- [ ] duza przebudowa architektury

