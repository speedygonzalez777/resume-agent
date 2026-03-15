# Resume Tailoring Agent

Resume Tailoring Agent to lokalny projekt MVP z backendem FastAPI i cienkim frontendem React + Vite do pracy z ofertami pracy i dopasowaniem CV.

Obecne glowne funkcje:
- walidacja `CandidateProfile`
- walidacja `JobPosting`
- URL-first parser oferty pracy
- zapis `CandidateProfile`, `JobPosting` i `MatchResult` do lokalnej SQLite
- prosty matching keywordowy zwracajacy `MatchResult`
- frontend MVP do flow `health -> parse-url -> save`

## Wymagane zaleznosci

Backend:
- Python 3.12+ lub zgodny z lokalnym `.venv`
- pip

Frontend:
- Node.js 22+
- npm

Opcjonalnie dla trudniejszych stron:
- Playwright
- Chromium dla Playwright

## Porty lokalne

- backend FastAPI: `http://127.0.0.1:8000`
- frontend Vite: `http://127.0.0.1:5173` lub `http://localhost:5173`

## Lokalna baza danych

- domyslny plik SQLite: `data/resume_agent.db`
- testy persystencji uzywaja tymczasowej SQLite, nie tej glownej bazy

## Istotne env vars

Backend:
- `OPENAI_API_KEY` - wymagany do parsera AI ofert
- `RESUME_AGENT_DB_URL` - opcjonalny override URL SQLite
- `JOB_URL_BROWSER_FALLBACK_ENABLED` - wlacza Playwright fallback
- `JOB_URL_BROWSER_FALLBACK_DOMAINS` - opcjonalna lista domen dla fallbacku
- `JOB_URL_BROWSER_FALLBACK_TIMEOUT_SECONDS`
- `JOB_URL_BROWSER_FALLBACK_WAIT_MS`

Frontend:
- `VITE_API_BASE_URL` - opcjonalny URL backendu, domyslnie `http://127.0.0.1:8000`

## Jak uruchomic backend lokalnie

1. Utworz i aktywuj virtualenv, jesli jeszcze go nie masz.
2. Zainstaluj zaleznosci:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

3. Upewnij sie, ze masz ustawione wymagane env vars, przede wszystkim `OPENAI_API_KEY`.
4. Uruchom backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

5. Sprawdz health:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

## Jak uruchomic frontend lokalnie

1. Przejdz do folderu `frontend`.
2. Zainstaluj zaleznosci npm:

```powershell
cd frontend
npm.cmd install
```

3. Opcjonalnie ustaw `VITE_API_BASE_URL`, jesli backend nie dziala na `http://127.0.0.1:8000`.
4. Uruchom frontend:

```powershell
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```

5. Otworz:

```text
http://127.0.0.1:5173
```

## CORS

Backend pozwala na lokalny frontend z originow:
- `http://localhost:5173`
- `http://127.0.0.1:5173`

## Obecne flow MVP

Frontend MVP:
1. sprawdza `GET /health`
2. przyjmuje URL oferty
3. wywoluje `POST /job/parse-url`
4. pokazuje sparsowany `JobPosting`
5. wywoluje `POST /job/save`
6. pokazuje komunikat sukcesu albo bledu

Backend:
- `POST /profile/validate`
- `POST /job/validate`
- `POST /job/parse-url`
- `POST /job/save`
- `GET /job`
- `GET /job/{job_posting_id}`
- `POST /match/analyze`
- `POST /match/save`
- `GET /match`
- `GET /match/{match_result_id}`

## Opcjonalny browser fallback dla parsera ofert

Jesli chcesz wlaczyc browser-based fallback dla trudniejszych stron:

```powershell
.\.venv\Scripts\python.exe -m pip install playwright
playwright install chromium
$env:JOB_URL_BROWSER_FALLBACK_ENABLED = "true"
```
