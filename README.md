# Resume Tailoring Agent

Resume Tailoring Agent to lokalny system MVP do dopasowywania CV do ofert pracy. Backend FastAPI odpowiada za parsowanie ofert, persystencje SQLite i matching, a frontend React + Vite daje lekki interfejs do codziennej pracy na localhost.

## Aktualny zakres MVP

Backend:
- walidacja `CandidateProfile`
- walidacja `JobPosting`
- URL-first parser ofert `POST /job/parse-url`
- lokalna persystencja SQLite dla `CandidateProfile`, `JobPosting` i `MatchResult`
- matching keywordowy zwracajacy `MatchResult` z weighted score i prostymi gating rules

Frontend:
- zakladka `Oferty pracy`
- zakladka `Profil kandydata` z sekcyjnym formularzem i historia profili
- zakladka `Matching`
- spójny shell zakladek bez ciezkiego routingu

## Architektura repo

- `app/models` - modele domenowe Pydantic
- `app/services` - logika biznesowa backendu
- `app/api` - cienkie routery FastAPI
- `app/db` - SQLite + SQLAlchemy i helpery persystencji
- `frontend/` - React + Vite UI na localhost
- `data/resume_agent.db` - domyslny plik lokalnej bazy SQLite
- `docs/` - dokumentacja produktu i modelu danych

## Wymagane zaleznosci

Backend:
- Python 3.12+
- pip

Frontend:
- Node.js 22+
- npm

Opcjonalnie dla trudniejszych stron ofert:
- `playwright`
- Chromium dla Playwright

## Porty lokalne

- backend: `http://127.0.0.1:8000`
- frontend: `http://127.0.0.1:5173`
- frontend moze tez dzialac na `http://localhost:5173`

## SQLite

- domyslny plik bazy: `data/resume_agent.db`
- testy korzystaja z tymczasowej SQLite, nie z glownej bazy lokalnej

## Wazne env vars

Backend:
- `OPENAI_API_KEY` - wymagany do AI parsera ofert
- `RESUME_AGENT_DB_URL` - opcjonalny override URL SQLite
- `JOB_URL_BROWSER_FALLBACK_ENABLED` - wlacza lokalny fallback Playwright
- `JOB_URL_BROWSER_FALLBACK_DOMAINS` - opcjonalna lista domen dla fallbacku
- `JOB_URL_BROWSER_FALLBACK_TIMEOUT_SECONDS`
- `JOB_URL_BROWSER_FALLBACK_WAIT_MS`

Frontend:
- `VITE_API_BASE_URL` - opcjonalny URL backendu, domyslnie `http://127.0.0.1:8000`

## Uruchomienie backendu - Windows

1. Utworz virtualenv, jesli jeszcze go nie masz:

```powershell
python -m venv .venv
```

2. Aktywuj virtualenv:

```powershell
.\.venv\Scripts\Activate.ps1
```

3. Zainstaluj zaleznosci backendu:

```powershell
python -m pip install -r requirements.txt
```

4. Ustaw wymagane env vars, przede wszystkim `OPENAI_API_KEY`.

5. Uruchom backend:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

6. Sprawdz health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

## Uruchomienie backendu - Linux

1. Utworz virtualenv:

```bash
python3 -m venv .venv
```

2. Aktywuj virtualenv:

```bash
source .venv/bin/activate
```

3. Zainstaluj zaleznosci backendu:

```bash
python -m pip install -r requirements.txt
```

4. Ustaw wymagane env vars, przede wszystkim `OPENAI_API_KEY`.

5. Uruchom backend:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

6. Sprawdz health check:

```bash
curl http://127.0.0.1:8000/health
```

## Uruchomienie frontendu - Windows

1. Przejdz do katalogu `frontend`:

```powershell
cd frontend
```

2. Zainstaluj zaleznosci npm:

```powershell
npm.cmd install
```

3. Opcjonalnie ustaw `VITE_API_BASE_URL`, jesli backend nie dziala na `http://127.0.0.1:8000`.

4. Uruchom frontend:

```powershell
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```

5. Otworz w przegladarce:

```text
http://127.0.0.1:5173
```

## Uruchomienie frontendu - Linux

1. Przejdz do katalogu `frontend`:

```bash
cd frontend
```

2. Zainstaluj zaleznosci npm:

```bash
npm install
```

3. Opcjonalnie ustaw `VITE_API_BASE_URL`, jesli backend nie dziala na `http://127.0.0.1:8000`.

4. Uruchom frontend:

```bash
npm run dev -- --host 127.0.0.1 --port 5173
```

5. Otworz w przegladarce:

```text
http://127.0.0.1:5173
```

## CORS

Backend dopuszcza lokalny frontend z originow:
- `http://localhost:5173`
- `http://127.0.0.1:5173`

## Zakladki i glowne flow

### Oferty pracy
- `GET /health`
- `POST /job/parse-url`
- `POST /job/save`
- `GET /job`
- `GET /job/{job_posting_id}`
- `DELETE /job/{job_posting_id}`
- historia ofert z filtrem i podgladem szczegolow

### Profil kandydata
- sekcyjny formularz `CandidateProfile` jako glowny sposob pracy
- pomocniczy podglad raw JSON tylko jako blok techniczny
- `POST /profile/save`
- `GET /profile`
- `GET /profile/{profile_id}`
- `DELETE /profile/{profile_id}`
- historia zapisanych profili, usuwanie rekordow i podglad wybranego profilu

### Matching
- wybor zapisanej oferty i zapisanego profilu
- `POST /match/analyze`
- czytelny widok `MatchResult`
- `POST /match/save`
- pomocniczy raw JSON tylko jako blok rozwijany

## Obecny matching

`POST /match/analyze` nadal bazuje na prostym keyword matcherze, ale scoring nie jest zwykla srednia.

- `overall_score` jest liczony jako weighted score
- `importance` wplywa na wage wymagania:
  - `high = 1.0`
  - `medium = 0.7`
  - `low = 0.4`
- `requirement_type` wplywa na mnoznik:
  - `must_have = 1.4`
  - `nice_to_have = 1.0`
- `match_status` daje wartosc:
  - `matched = 1.0`
  - `partial = 0.5`
  - `missing = 0.0`
- obowiazuja tez proste gating rules:
  - brak `must_have` z `importance=high` blokuje `fit_classification=high`
  - co najmniej jedno brakujace `must_have` blokuje rekomendacje `generate`
  - co najmniej dwa brakujace `must_have` daja `do_not_recommend`

## Opcjonalny browser fallback dla parsera ofert

Jesli chcesz wlaczyc browser-based fallback dla trudniejszych stron:

```powershell
python -m pip install playwright
playwright install chromium
$env:JOB_URL_BROWSER_FALLBACK_ENABLED = "true"
```

