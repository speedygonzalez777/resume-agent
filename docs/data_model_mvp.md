# Data model MVP

## 1. Cel modelu MVP
Model MVP ma zawierać wyłącznie te obiekty, które są niezbędne do:
- przyjęcia danych kandydata,
- przyjęcia oferty pracy,
- analizy wymagań i słów kluczowych,
- oceny dopasowania,
- wygenerowania treści CV,
- przygotowania raportu zmian.

Model MVP nie obejmuje jeszcze:
- pełnej historii uruchomień,
- zaawansowanych metadanych portali,
- rozbudowanego śledzenia procesu rekrutacji,
- wielu formatów wyjściowych poza głównym DOCX,
- rozbudowanych danych portal-specific.

---

## 2. Główne obiekty MVP
System w wersji MVP operuje na następujących obiektach:
- CandidateProfile
- JobPosting
- Requirement
- RequirementMatch
- MatchResult
- ResumeDraft
- ChangeReport

---

## 3. CandidateProfile
Główne źródło prawdy o kandydacie.

### Zawiera:
- personal_info  
  Komentarz: dane kontaktowe i identyfikacyjne do nagłówka CV.

- target_roles  
  Komentarz: lista ról, na które kandydat realnie chce aplikować.

- professional_summary_base  
  Komentarz: bazowe podsumowanie zawodowe, z którego system może tworzyć wersję dopasowaną do oferty.

- experience_entries  
  Komentarz: lista doświadczeń zawodowych, które będą głównym źródłem bullet pointów do CV.

- project_entries  
  Komentarz: lista projektów, które mogą potwierdzać kompetencje nawet wtedy, gdy nie wynikają wprost z pracy zawodowej.

- skill_entries  
  Komentarz: lista technologii i umiejętności, używana do mapowania słów kluczowych z oferty.

- education_entries  
  Komentarz: edukacja potrzebna do sekcji CV i do weryfikacji wymagań typu „wykształcenie techniczne”.

- language_entries  
  Komentarz: języki obce przydatne zarówno do CV, jak i do dopasowania do wymagań z oferty.

- certificate_entries  
  Komentarz: certyfikaty i szkolenia, które mogą wzmacniać dopasowanie.

- immutable_rules  
  Komentarz: zasady pilnujące, czego nie wolno dopisywać lub zmieniać.

### Cel:
Ten obiekt przechowuje wszystkie prawdziwe dane, na podstawie których system może tworzyć dopasowane CV.

---

## 4. PersonalInfo
Podstawowe dane użytkownika potrzebne do CV.

### Zawiera:
- full_name  
  Komentarz: imię i nazwisko do nagłówka dokumentu.

- email  
  Komentarz: kontakt e-mail.

- phone  
  Komentarz: numer telefonu do kontaktu.

- linkedin_url  
  Komentarz: profil LinkedIn, jeśli kandydat chce go pokazywać.

- github_url  
  Komentarz: przydatne szczególnie dla ról technicznych.

- portfolio_url  
  Komentarz: link do portfolio, strony lub repozytorium projektów.

- location  
  Komentarz: lokalizacja kandydata, np. miasto lub miasto + kraj.

---

## 5. ExperienceEntry
Pojedynczy wpis doświadczenia zawodowego.

### Zawiera:
- id  
  Komentarz: unikalny identyfikator wpisu, potrzebny do referencji w dopasowaniu.

- company_name  
  Komentarz: nazwa firmy.

- position_title  
  Komentarz: nazwa stanowiska.

- start_date  
  Komentarz: data rozpoczęcia pracy.

- end_date  
  Komentarz: data zakończenia pracy.

- is_current  
  Komentarz: informacja, czy to aktualne stanowisko.

- location  
  Komentarz: lokalizacja pracy.

- responsibilities  
  Komentarz: obowiązki wykonywane na stanowisku.

- achievements  
  Komentarz: osiągnięcia i konkretne efekty, najlepiej mierzalne.

- technologies_used  
  Komentarz: technologie, narzędzia i systemy używane w tej pracy.

- keywords  
  Komentarz: dodatkowe słowa kluczowe pomocne przy dopasowaniu.

### Cel:
To główny materiał do dopasowywania CV do wymagań oferty.

---

## 6. ProjectEntry
Pojedynczy projekt powiązany z kandydatem.

### Zawiera:
- id  
  Komentarz: unikalny identyfikator projektu.

- project_name  
  Komentarz: nazwa projektu.

- role  
  Komentarz: rola kandydata w projekcie.

- description  
  Komentarz: krótki opis projektu.

- technologies_used  
  Komentarz: technologie i narzędzia użyte w projekcie.

- outcomes  
  Komentarz: rezultat projektu, np. działający prototyp, aplikacja, publikacja, raport.

- keywords  
  Komentarz: słowa kluczowe związane z projektem.

- link  
  Komentarz: link do repozytorium, strony, dokumentacji lub demo.

### Cel:
Pozwala wykorzystać projekty jako dowód spełniania wymagań, nawet jeśli nie wynikają one wprost z doświadczenia zawodowego.

---

## 7. SkillEntry
Pojedyncza umiejętność lub technologia.

### Zawiera:
- name  
  Komentarz: nazwa umiejętności, np. Python, TIA Portal, AutoCAD.

- category  
  Komentarz: typ umiejętności, np. techniczna, miękka, narzędziowa, język programowania.

- level  
  Komentarz: deklarowany poziom znajomości.

- years_of_experience  
  Komentarz: orientacyjna liczba lat pracy z daną umiejętnością.

- evidence_sources  
  Komentarz: referencje do doświadczeń lub projektów, które potwierdzają tę umiejętność.

- aliases  
  Komentarz: alternatywne nazwy i zapisy tej samej umiejętności.

### Cel:
Umożliwia lepsze mapowanie słów kluczowych z oferty na realne kompetencje użytkownika.

---

## 8. EducationEntry
Pojedynczy wpis edukacyjny.

### Zawiera:
- institution_name  
  Komentarz: nazwa uczelni lub szkoły.

- degree  
  Komentarz: stopień lub typ wykształcenia.

- field_of_study  
  Komentarz: kierunek lub specjalizacja.

- start_date  
  Komentarz: data rozpoczęcia nauki.

- end_date  
  Komentarz: data zakończenia nauki.

- is_current  
  Komentarz: informacja, czy edukacja nadal trwa.

---

## 9. LanguageEntry
Pojedynczy język obcy.

### Zawiera:
- language_name  
  Komentarz: nazwa języka.

- proficiency_level  
  Komentarz: poziom znajomości, np. B2, C1, komunikatywny.

---

## 10. CertificateEntry
Pojedynczy certyfikat lub szkolenie.

### Zawiera:
- certificate_name  
  Komentarz: nazwa certyfikatu lub kursu.

- issuer  
  Komentarz: organizacja wydająca.

- issue_date  
  Komentarz: data uzyskania.

- notes  
  Komentarz: dodatkowa informacja, np. zakres kursu lub numer certyfikatu.

---

## 11. ImmutableRules
Zasady nienaruszalne dotyczące profilu kandydata.

### Zawiera:
- forbidden_skills  
  Komentarz: umiejętności, których system nie może dopisać.

- forbidden_claims  
  Komentarz: stwierdzenia, których system nie może używać, jeśli nie mają pokrycia.

- forbidden_certificates  
  Komentarz: certyfikaty, których nie wolno wymyślać ani sugerować.

- editing_rules  
  Komentarz: zasady modyfikacji treści, np. „wolno skracać, nie wolno zmieniać sensu”.

### Cel:
Pilnuje, aby system nie dopisywał nieprawdziwych informacji.

---

## 12. JobPosting
Ustrukturyzowana wersja oferty pracy.

### Zawiera:
- source  
  Komentarz: źródło oferty, np. pracuj, jooble, justjoinit, rocketjobs, manual.

- title  
  Komentarz: tytuł stanowiska.

- company_name  
  Komentarz: nazwa firmy.

- location  
  Komentarz: lokalizacja pracy.

- work_mode  
  Komentarz: tryb pracy, np. onsite, hybrid, remote.

- employment_type  
  Komentarz: typ zatrudnienia, np. UoP, B2B, staż.

- seniority_level  
  Komentarz: poziom stanowiska, np. junior, mid, senior.

- role_summary  
  Komentarz: krótki opis roli lub stanowiska.

- responsibilities  
  Komentarz: lista obowiązków z ogłoszenia.

- requirements  
  Komentarz: lista wymagań z ogłoszenia, zwykle przechowywana jako Requirement.

- keywords  
  Komentarz: lista słów kluczowych wykrytych w ogłoszeniu.

- language_of_offer  
  Komentarz: język, w którym napisana jest oferta.

### Cel:
Reprezentuje jedną konkretną ofertę pracy po analizie.

---

## 13. Requirement
Pojedyncze wymaganie z oferty.

### Zawiera:
- id  
  Komentarz: identyfikator wymagania.

- text  
  Komentarz: pełna treść wymagania.

- category  
  Komentarz: rodzaj wymagania, np. technologia, doświadczenie, język, edukacja.

- requirement_type  
  Komentarz: informacja, czy to must-have czy nice-to-have.

- importance  
  Komentarz: priorytet wymagania, np. high, medium, low.

- extracted_keywords  
  Komentarz: słowa kluczowe wyciągnięte z tego konkretnego wymagania.

### Wyjaśnienie pól:
- category  
  np. `technology`, `experience`, `language`, `education`, `soft_skill`, `domain`

- requirement_type  
  `must_have` albo `nice_to_have`

- importance  
  np. `high`, `medium`, `low`

### Cel:
To podstawowa jednostka, według której system ocenia dopasowanie.

---

## 14. RequirementMatch
Wynik dopasowania jednego wymagania do profilu kandydata.

### Zawiera:
- requirement_id  
  Komentarz: wskazuje, którego wymagania dotyczy to dopasowanie.

- match_status  
  Komentarz: wynik dopasowania, np. matched, partial, missing.

- matched_experience_ids  
  Komentarz: ID doświadczeń zawodowych, które potwierdzają spełnienie wymagania.

- matched_project_ids  
  Komentarz: ID projektów, które również mogą stanowić dowód spełnienia wymagania.

- matched_skill_names  
  Komentarz: nazwy umiejętności powiązanych z tym wymaganiem.

- evidence_texts  
  Komentarz: krótkie fragmenty uzasadnienia, które później mogą posłużyć do raportu lub CV.

- explanation  
  Komentarz: opis, dlaczego wymaganie uznano za spełnione, częściowo spełnione albo niespełnione.

- missing_elements  
  Komentarz: czego brakuje, aby uznać wymaganie za w pełni spełnione.

### Wyjaśnienie pól:
- match_status  
  `matched`, `partial`, `missing`

### Cel:
Pokazuje, czy kandydat rzeczywiście spełnia konkretne wymaganie i na jakiej podstawie.

---

## 15. MatchResult
Wynik całościowego dopasowania profilu do oferty.

### Zawiera:
- overall_score  
  Komentarz: liczbowy wynik ogólny dopasowania.

- fit_classification  
  Komentarz: klasyfikacja jakości dopasowania, np. high, medium, low.

- recommendation  
  Komentarz: decyzja systemu, czy warto generować CV.

- requirement_matches  
  Komentarz: lista dopasowań dla wszystkich wymagań.

- strengths  
  Komentarz: mocne strony kandydata względem tej oferty.

- gaps  
  Komentarz: luki i brakujące elementy względem oferty.

- keyword_coverage  
  Komentarz: informacja, jak dobrze pokryto słowa kluczowe z oferty.

- final_summary  
  Komentarz: końcowe podsumowanie, które może być pokazane użytkownikowi.

### Wyjaśnienie pól:
- fit_classification  
  `high`, `medium`, `low`

- recommendation  
  `generate`, `generate_with_caution`, `do_not_recommend`

### Cel:
Jest to główny wynik analizy, na podstawie którego system decyduje, czy i jak generować CV.

---

## 16. ResumeDraft
Treść CV przed zapisaniem do pliku DOCX.

### Zawiera:
- header  
  Komentarz: dane nagłówkowe gotowe do wstawienia do szablonu.

- professional_summary  
  Komentarz: dopasowane podsumowanie zawodowe pod tę konkretną ofertę.

- selected_skills  
  Komentarz: lista wybranych umiejętności, które mają największe znaczenie dla tej oferty.

- selected_experience_entries  
  Komentarz: lista doświadczeń zawodowych w wersji dostosowanej do oferty.

- selected_project_entries  
  Komentarz: lista projektów użytych jako wsparcie dopasowania.

- selected_education_entries  
  Komentarz: edukacja wybrana do finalnego CV.

- selected_language_entries  
  Komentarz: języki pokazane w CV.

- selected_certificate_entries  
  Komentarz: certyfikaty pokazane w CV.

- keyword_usage  
  Komentarz: informacja, które słowa kluczowe zostały użyte w treści CV.

### Cel:
To gotowa, dopasowana treść CV, jeszcze przed wstawieniem do szablonu DOCX.

---

## 17. ResumeHeader
Nagłówek CV.

### Zawiera:
- full_name  
  Komentarz: imię i nazwisko kandydata.

- target_title  
  Komentarz: nazwa stanowiska docelowego dla tej wersji CV.

- contact_line  
  Komentarz: skrócona linia kontaktowa do pokazania w nagłówku.

- location  
  Komentarz: lokalizacja pokazywana w CV.

- links  
  Komentarz: linki do LinkedIn, GitHub, portfolio itp.

---

## 18. ResumeExperienceEntry
Wpis doświadczenia zawodowego w wersji dopasowanej do oferty.

### Zawiera:
- source_experience_id  
  Komentarz: referencja do oryginalnego ExperienceEntry.

- company_name  
  Komentarz: nazwa firmy.

- position_title  
  Komentarz: stanowisko.

- date_range  
  Komentarz: zakres dat do wyświetlenia w CV.

- bullet_points  
  Komentarz: bullet pointy przepisane i uporządkowane pod daną ofertę.

- highlighted_keywords  
  Komentarz: słowa kluczowe, które celowo uwypuklono w tym wpisie.

### Cel:
To przetworzona wersja ExperienceEntry, dostosowana do konkretnej oferty pracy.

---

## 19. ResumeProjectEntry
Wpis projektu w wersji dopasowanej do oferty.

### Zawiera:
- source_project_id  
  Komentarz: referencja do oryginalnego ProjectEntry.

- project_name  
  Komentarz: nazwa projektu.

- role  
  Komentarz: rola w projekcie.

- bullet_points  
  Komentarz: najważniejsze informacje o projekcie dobrane pod ofertę.

- highlighted_keywords  
  Komentarz: słowa kluczowe z oferty użyte przy opisie projektu.

---

## 20. ChangeReport
Raport zmian względem profilu bazowego lub bazowego CV.

### Zawiera:
- added_elements  
  Komentarz: elementy dodane do finalnej wersji CV względem wersji bazowej.

- emphasized_elements  
  Komentarz: elementy, które istniały wcześniej, ale zostały mocniej wyeksponowane.

- omitted_elements  
  Komentarz: elementy pominięte w finalnym CV.

- omission_reasons  
  Komentarz: powody pominięcia danych elementów.

- detected_keywords  
  Komentarz: wszystkie ważne słowa kluczowe wykryte w ogłoszeniu.

- used_keywords  
  Komentarz: słowa kluczowe, które faktycznie wykorzystano w CV.

- unused_keywords  
  Komentarz: słowa kluczowe, których nie użyto.

- blocked_items  
  Komentarz: rzeczy, których system nie dodał, bo nie miały pokrycia w danych.

- warnings  
  Komentarz: ostrzeżenia, np. niski poziom dopasowania lub brak twardych dowodów.

### Cel:
Ma pokazać użytkownikowi, co zostało zmienione, co zostało wykorzystane i czego system celowo nie dodał.

---

## 21. Relacje między obiektami
Przepływ logiczny wygląda następująco:

- CandidateProfile zawiera pełne dane o kandydacie
- JobPosting zawiera wymagania i słowa kluczowe z jednej oferty
- JobPosting jest rozbijany na Requirement
- CandidateProfile i Requirement są porównywane, czego wynikiem jest RequirementMatch
- wszystkie RequirementMatch tworzą MatchResult
- MatchResult i CandidateProfile są używane do stworzenia ResumeDraft
- ResumeDraft oraz MatchResult są podstawą do wygenerowania ChangeReport

---

## 22. Minimalne wymagania implementacyjne MVP
Na poziomie kodu pierwsza implementacja musi umożliwiać:
- zapis i odczyt CandidateProfile,
- zapis i odczyt JobPosting,
- analizę listy Requirement,
- utworzenie MatchResult,
- utworzenie ResumeDraft,
- utworzenie ChangeReport,
- późniejsze wypełnienie szablonu DOCX na podstawie ResumeDraft.

---

## 23. Zasady modelowania w MVP
- dane źródłowe muszą być oddzielone od danych wygenerowanych,
- każde wymaganie z oferty musi być analizowane osobno,
- każde istotne twierdzenie w CV musi mieć pokrycie w danych kandydata,
- brak danych nie oznacza spełnienia wymagania,
- model ma być prosty do zakodowania i rozszerzalny w przyszłości.