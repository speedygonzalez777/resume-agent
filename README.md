# Resume Tailoring Agent

Resume Tailoring Agent to lokalny system MVP do analizy ofert pracy, profilow kandydatow i dopasowywania CV do konkretnej oferty. Backend FastAPI odpowiada za parsowanie ofert, matching, generowanie draftu CV i lokalna persystencje SQLite, a frontend React + Vite daje lekki interfejs do codziennej pracy na localhost.

## Zasada truthful-first

System dziala w trybie truthful-first:
- nie dopisuje niepotwierdzonych doswiadczen, technologii, certyfikatow ani lat doswiadczenia,
- brak danych nie oznacza spelnienia wymagania,
- lepiej pominac slaby element niz sztucznie go upiekszyc,
- kazdy draft ma byc mocny, ale nadal prawdziwy.

## Aktualny zakres MVP

Backend:
- walidacja `CandidateProfile`
- walidacja `JobPosting`
- URL-first parser ofert `POST /job/parse-url`
- lokalna persystencja SQLite dla `CandidateProfile`, `JobPosting` i `MatchResult`
- category-aware matching zwracajacy `MatchResult` z weighted score, `not_verifiable`, AI-assisted requirement-type classification i AI-assisted education upgrade path
- stateless generator CV `POST /resume/generate`, ktory zwraca `ResumeDraft` i `ChangeReport`

Frontend:
- zakladka `Oferty pracy`
- zakladka `Profil kandydata`
- zakladka `Matching`
- zakladka `CV i list motywacyjny`
- lekki shell zakladek bez ciezkiego routingu

## Etap 1 generowania dokumentow

W aktualnym etapie dziala tylko generowanie CV:
- wybierasz zapisany profil,
- wybierasz zapisana oferte,
- system korzysta z zapisanego `MatchResult` albo liczy matching inline,
- generowany jest ustrukturyzowany `ResumeDraft`,
- UI pokazuje czytelny podglad CV i `ChangeReport`.

List motywacyjny nie jest jeszcze generowany. W zakladce `CV i list motywacyjny` jest tylko informacja, ze ten etap zostanie dodany pozniej.

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
- `OPENAI_API_KEY` - wymagany do AI parsera ofert, AI requirement-type classification, AI-assisted education matching i AI resume tailoring
- `RESUME_AGENT_DB_URL` - opcjonalny override URL SQLite
- `JOB_URL_BROWSER_FALLBACK_ENABLED` - wlacza lokalny fallback Playwright
- `JOB_URL_BROWSER_FALLBACK_DOMAINS` - opcjonalna lista domen dla fallbacku
- `JOB_URL_BROWSER_FALLBACK_TIMEOUT_SECONDS`
- `JOB_URL_BROWSER_FALLBACK_WAIT_MS`
- `OPENAI_REQUIREMENT_TYPE_MODEL` - opcjonalny override modelu dla AI requirement-type classifier
- `OPENAI_REQUIREMENT_TYPE_TEMPERATURE` - opcjonalny sampling override dla wspieranych rodzin modeli
- `OPENAI_REQUIREMENT_TYPE_TOP_P` - opcjonalny sampling override dla wspieranych rodzin modeli
- `OPENAI_EDUCATION_MATCH_MODEL` - opcjonalny override modelu dla AI-assisted education matching

Frontend:
- `VITE_API_BASE_URL` - opcjonalny URL backendu, domyslnie `http://127.0.0.1:8000`

## Virtualenv

- docelowe developerskie srodowisko backendu to lokalne `.venv` zbudowane jawnie na Pythonie 3.12
- jesli masz stare `.venv` zbudowane na innej wersji Pythona, usun je i utworz ponownie komenda dla 3.12 z sekcji ponizej

## Uruchomienie backendu - Windows

1. Sprawdz, czy Python 3.12 jest dostepny przez launcher `py`:

```powershell
py -3.12 --version
```

2. Utworz virtualenv na Pythonie 3.12:

```powershell
py -3.12 -m venv .venv
```

3. Aktywuj virtualenv:

```powershell
.\.venv\Scripts\Activate.ps1
```

4. Zainstaluj zaleznosci backendu:

```powershell
python -m pip install -r requirements.txt
```

5. Ustaw wymagane env vars, przede wszystkim `OPENAI_API_KEY`.

6. Uruchom backend:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

7. Sprawdz health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
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

## Uruchomienie backendu - Linux

1. Sprawdz, czy `python3.12` jest dostepny:

```bash
python3.12 --version
```

2. Utworz virtualenv na Pythonie 3.12:

```bash
python3.12 -m venv .venv
```

3. Aktywuj virtualenv:

```bash
source .venv/bin/activate
```

4. Zainstaluj zaleznosci backendu:

```bash
python -m pip install -r requirements.txt
```

5. Ustaw wymagane env vars, przede wszystkim `OPENAI_API_KEY`.

6. Uruchom backend:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

7. Sprawdz health check:

```bash
curl http://127.0.0.1:8000/health
```

## Testy backendu

Po aktywacji `.venv` rekomendowana komenda to:

```bash
python -m pytest -q
```

Wspierane jest tez bezposrednie:

```bash
pytest -q
```

Bez aktywacji virtualenv mozesz uzyc interpretera z `.venv` wprost:
- Linux: `./.venv/bin/python -m pytest -q`
- Windows: `.\.venv\Scripts\python -m pytest -q`

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
- sekcyjny formularz `CandidateProfile`
- `POST /profile/save`
- `GET /profile`
- `GET /profile/{profile_id}`
- `DELETE /profile/{profile_id}`
- historia zapisanych profili i podglad wybranego profilu

### Matching
- wybor zapisanej oferty i zapisanego profilu
- `POST /match/analyze`
- `POST /match/save`
- czytelny widok `MatchResult`

### CV i list motywacyjny
- wybor zapisanego profilu
- wybor zapisanej oferty
- uzycie zapisanego `MatchResult` albo inline `POST /match/analyze`
- `POST /resume/generate`
- czytelny `ResumeDraft`
- czytelny `ChangeReport`
- informacja, ze list motywacyjny bedzie dodany w kolejnym etapie

## Obecny matching

`POST /match/analyze` nie jest juz jednym prostym keyword flow. Obecny backend laczy deterministic matching z ostroznym wsparciem OpenAI, ale nadal zachowuje truthful-first i explainability.

- matcher ma category-aware deterministic baseline
- requirement najpierw trafia do requirement-type classifiera:
  - najpierw probuje AI classify pojedynczy requirement
  - jesli AI nie dziala albo zwroci zly wynik, matcher wraca do obecnej klasyfikacji heurystycznej
- znormalizowane typy requirementow uzywane do routingu to:
  - `technical_skill`
  - `experience`
  - `education`
  - `language`
  - `application_constraint`
  - `soft_signal`
  - `low_signal`
- `application_constraint` obejmuje rzeczy typu availability, commitment duration, work authorization, age, relocation czy on-site availability
- `application_constraint` nie jest traktowany jak zwykly technical gap i pozostaje neutralny dla glownego score, ale nierozwiazany `must_have` nadal moze obnizyc rekomendacje do `generate_with_caution`
- `education` ma deterministic baseline oraz AI-assisted semantic upgrade path dla niejednoznacznych przypadkow
- `match_status` moze byc teraz:
  - `matched = 1.0`
  - `partial = 0.5`
  - `missing = 0.0`
  - `not_verifiable = neutralne dla score`
- `overall_score` nadal jest liczony jako weighted score
- `importance` wplywa na wage wymagania:
  - `high = 1.0`
  - `medium = 0.7`
  - `low = 0.4`
- `requirement_type` wplywa na mnoznik:
  - `must_have = 1.4`
  - `nice_to_have = 1.0`
- obowiazuja tez proste gating rules:
  - brak `must_have` z `importance=high` blokuje `fit_classification=high`
  - co najmniej jedno brakujace `must_have` blokuje rekomendacje `generate`
  - co najmniej dwa brakujace `must_have` daja `do_not_recommend`
  - `must_have` oznaczone jako `not_verifiable` lub `application_constraint` moga wymusic bardziej ostrozne `generate_with_caution`

## Wymagania zaleznosci backendu

Etap 1 generowania CV nie dodal nowych zaleznosci backendowych. `requirements.txt` zostal zweryfikowany i nie wymagal rozszerzenia.

## Opcjonalny browser fallback dla parsera ofert

Jesli chcesz wlaczyc browser-based fallback dla trudniejszych stron:

```powershell
python -m pip install playwright
playwright install chromium
$env:JOB_URL_BROWSER_FALLBACK_ENABLED = "true"
```
