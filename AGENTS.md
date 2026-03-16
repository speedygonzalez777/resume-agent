# AGENTS.md

To repo to lokalny system MVP do dopasowywania CV do ofert pracy.

Aktualna architektura:
- `app/models` zawiera modele domenowe Pydantic
- `app/services` zawiera logike biznesowa backendu
- `app/api` zawiera cienkie routery FastAPI
- `app/db` zawiera lokalna persystencje SQLite oparta o SQLAlchemy
- `frontend/` zawiera minimalny React + Vite UI na localhost
- fizyczny plik bazy jest w `data/resume_agent.db`

Zasady pracy:
- nie zmieniaj plikow w `app/models` bez wyraznej potrzeby
- nie zmieniaj nazw istniejacych endpointow bez wyraznej potrzeby
- nie dodawaj nowych bibliotek bez uzasadnienia
- logike biznesowa trzymaj w backendzie, glownie w `app/services`
- routery backendowe maja pozostac cienkie
- frontend ma byc cienka warstwa UI nad istniejacym API
- rob male zmiany, bez duzego refaktoru
- nie dodawaj Dockera, Postgresa ani n8n w biezacych zadaniach
- nie buduj multi-agent systemu
- jesli cos zmieniasz, pokaz ktore pliki zostaly zmienione
- po zmianach uruchom minimalny test backendu albo endpointu i smoke test frontendu

Aktualny stan backendu:
- istnieje `POST /profile/validate`
- istnieje `POST /job/validate`
- istnieje URL-first parser `POST /job/parse-url`
- istnieje `POST /match/analyze`
- matching zwraca `MatchResult` i `RequirementMatch`
- matching liczy weighted score z wagami `importance` i mnoznikiem `requirement_type`
- matching ma proste gating rules dla brakujacych krytycznych `must_have`
- parser ofert ma HTTP-first fetch i lokalny browser fallback
- lokalna persystencja SQLite zapisuje:
  - `CandidateProfile`
  - `JobPosting`
  - `MatchResult`

Aktualne endpointy persystencji:
- `POST /profile/save`
- `GET /profile`
- `GET /profile/{profile_id}`
- `DELETE /profile/{profile_id}`
- `POST /job/save`
- `GET /job`
- `GET /job/{job_posting_id}`
- `DELETE /job/{job_posting_id}`
- `POST /match/save`
- `GET /match`
- `GET /match/{match_result_id}`

Aktualny stan frontendu:
- frontend MVP jest w `frontend/`
- korzysta z React + Vite
- ma lekki shell zakladek bez ciezkiego routingu
- udostepnia zakladki:
  - `Oferty pracy`
  - `Profil kandydata`
  - `Matching`
- zakladka `Oferty pracy` obsluguje:
  - `GET /health`
  - `POST /job/parse-url`
  - `POST /job/save`
  - `GET /job`
  - `GET /job/{job_posting_id}`
  - `DELETE /job/{job_posting_id}`
- zakladka `Profil kandydata` obsluguje:
  - sekcyjny formularz `CandidateProfile`
  - pomocniczy podglad raw JSON
  - `POST /profile/save`
  - `GET /profile`
  - `GET /profile/{profile_id}`
  - `DELETE /profile/{profile_id}`
- zakladka `Matching` obsluguje:
  - wybor zapisanej oferty
  - wybor zapisanego profilu
  - `POST /match/analyze`
  - `POST /match/save`
  - czytelny widok `MatchResult`
- frontend nie zawiera logiki biznesowej parsera ani matchingu

Zasady persystencji:
- dane domenowe sa trzymane jako JSON serializowany do tekstu
- nie przebudowujemy teraz backendu pod pelny ORM domenowy
- `init_db()` jest wywolywane jawnie przy starcie aplikacji
- testy persystencji maja uzywac tymczasowej SQLite, nie realnego `data/resume_agent.db`

