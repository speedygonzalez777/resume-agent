# AGENTS.md

To repo to lokalny backend FastAPI do dopasowywania CV do ofert pracy.

Aktualna architektura:
- `app/models` zawiera modele domenowe Pydantic
- `app/services` zawiera logike biznesowa
- `app/api` zawiera cienkie routery
- `app/db` zawiera lokalna persystencje SQLite oparta o SQLAlchemy
- fizyczny plik bazy jest w `data/resume_agent.db`

Zasady pracy:
- nie zmieniaj plikow w `app/models` bez wyraznej potrzeby
- nie zmieniaj nazw istniejacych endpointow bez wyraznej potrzeby
- nie dodawaj nowych bibliotek bez uzasadnienia
- logike biznesowa umieszczaj w `app/services`
- routery maja byc cienkie, bez logiki biznesowej
- rob male zmiany, bez duzego refaktoru
- nie dodawaj Dockera, frontendu, Postgresa ani n8n w biezacych zadaniach
- nie buduj multi-agent systemu
- jesli cos zmieniasz, pokaz ktore pliki zostaly zmienione
- po zmianach uruchom minimalny test importow albo endpointu

Aktualny stan backendu:
- istnieje `POST /profile/validate`
- istnieje `POST /job/validate`
- istnieje URL-first parser `POST /job/parse-url`
- istnieje `POST /match/analyze`
- matching zwraca `MatchResult` i `RequirementMatch`
- parser ofert ma HTTP-first fetch i lokalny browser fallback
- lokalna persystencja SQLite zapisuje:
  - `CandidateProfile`
  - `JobPosting`
  - `MatchResult`

Aktualne endpointy persystencji:
- `POST /profile/save`
- `GET /profile/{profile_id}`
- `POST /job/save`
- `GET /job`
- `GET /job/{job_posting_id}`
- `POST /match/save`
- `GET /match`
- `GET /match/{match_result_id}`

Zasady persystencji:
- dane domenowe sa trzymane jako JSON serializowany do tekstu
- nie przebudowujemy teraz backendu pod pelny ORM domenowy
- `init_db()` jest wywolywane jawnie przy starcie aplikacji
- testy persystencji maja uzywac tymczasowej SQLite, nie realnego `data/resume_agent.db`
