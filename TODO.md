# TODO — Resume Tailoring Agent

## Aktualny focus
Obecnie pracujemy nad:
- [ ] uporządkowaniem `match_service.py`
- [ ] zwracaniem `MatchResult` i `RequirementMatch` zamiast zwykłego słownika
- [ ] przygotowaniem repo pod pierwsze zadanie dla Codexa

## Etap 1 — uporządkowanie backendu MVP
- [x] Utworzyć strukturę projektu
- [x] Dodać modele Pydantic dla kandydata
- [x] Dodać modele Pydantic dla oferty pracy
- [x] Dodać modele Pydantic dla matchingu
- [x] Dodać modele Pydantic dla resume
- [x] Dodać endpoint `/profile/validate`
- [x] Dodać endpoint `/job/validate`
- [x] Dodać endpoint `/match/analyze`
- [x] Dodać testowe pliki JSON do walidacji

## Etap 2 — uporządkowanie wyników matchingu
- [ ] Przerobić `match_service.py`, aby zwracał `MatchResult` zamiast zwykłego słownika
- [ ] Przerobić wyniki pojedynczych wymagań na `RequirementMatch`
- [ ] Uporządkować logikę `matched / partial / missing`
- [ ] Dodać prosty test dla `match_service.py`
- [ ] Sprawdzić, czy endpoint `/match/analyze` zwraca poprawną strukturę modelu

## Etap 3 — integracja AI do analizy ofert
- [ ] Dodać plik `AGENTS.md`
- [ ] Przygotować serwis OpenAI do komunikacji z modelem
- [ ] Dodać parser surowej oferty pracy do modelu `JobPosting`
- [ ] Dodać endpoint `/job/parse`
- [ ] Przygotować prompt do parsowania ofert pracy
- [ ] Przetestować parsowanie na 2–3 realnych ofertach

## Etap 4 — integracja AI do dopasowania profilu
- [ ] Dodać wersję AI dla analizy dopasowania profilu do oferty
- [ ] Porównać wynik AI z prostym matcherem keywordowym
- [ ] Dodać uzasadnienia dla każdego wymagania
- [ ] Dodać bezpieczniki przeciw halucynacjom

## Etap 5 — generowanie treści CV
- [ ] Dodać serwis generujący `ResumeDraft`
- [ ] Przygotować prompt do generowania draftu CV
- [ ] Dopilnować, żeby `professional_summary` było opcjonalne
- [ ] Dodać raport zmian `ChangeReport`

## Etap 6 — eksport dokumentów
- [ ] Przygotować szablon DOCX
- [ ] Dodać wypełnianie szablonu na podstawie `ResumeDraft`
- [ ] Wygenerować pierwszy testowy plik DOCX
- [ ] Sprawdzić, czy dokument da się wygodnie ręcznie edytować

## Etap 7 — UI
- [ ] Zdecydować, czy UI będzie w Streamlit czy w prostym frontendzie webowym
- [ ] Dodać prosty formularz: profil + oferta
- [ ] Dodać podgląd wyniku matchingu
- [ ] Dodać przycisk generowania draftu CV
- [ ] Dodać pobieranie DOCX

## Etap 8 — porządki i portfolio
- [ ] Dodać README z instrukcją uruchomienia
- [ ] Uporządkować strukturę repo
- [ ] Dodać przykładowe dane testowe
- [ ] Opisać architekturę projektu do portfolio
- [ ] Przygotować demo projektu