# AGENTS.md

To repo to backend FastAPI do dopasowywania CV do ofert pracy.

Zasady:
- nie zmieniaj plików w `app/models` bez wyraźnej potrzeby
- nie zmieniaj nazw istniejących endpointów bez wyraźnej potrzeby
- nie dodawaj nowych bibliotek bez uzasadnienia
- logikę biznesową umieszczaj w `app/services`
- routery mają być cienkie, bez logiki biznesowej
- rób małe zmiany, bez dużego refaktoru
- nie dodawaj Dockera, frontendu, Postgresa ani n8n w bieżących zadaniach
- nie buduj multi-agent systemu
- jeśli coś zmieniasz, pokaż które pliki zostały zmienione
- po zmianach uruchom minimalny test importów albo endpointu

Aktualny focus:
- uporządkowanie `match_service.py`
- zwracanie `MatchResult` i `RequirementMatch` zamiast zwykłego słownika
- przygotowanie repo pod późniejszą integrację AI