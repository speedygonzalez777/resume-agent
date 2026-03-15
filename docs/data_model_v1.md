# Data model v1

## 1. Założenia modelu danych
Model danych został zaprojektowany tak, aby:
- obsługiwać oferty z różnych portali pracy,
- rozdzielać dane wejściowe, dane pośrednie i dane wyjściowe,
- umożliwiać analizę dopasowania kandydata do oferty,
- wspierać generowanie CV i opcjonalnie listu motywacyjnego,
- zachować możliwość audytu zmian oraz kontroli halucynacji.

Model jest podzielony na:
- dane źródłowe,
- dane znormalizowane,
- dane analityczne,
- dane wyjściowe,
- dane kontrolne.

---

## 2. Główne obiekty systemu
System operuje na następujących głównych obiektach:
- SourceMetadata
- RawJobInput
- CandidateProfile
- JobPosting
- Requirement
- RequirementMatch
- MatchResult
- ResumeDraft
- CoverLetterDraft
- ChangeReport
- GenerationRun

---

## 3. SourceMetadata
Metadane źródła oferty pracy.

### Zawiera:
- source_portal  
  np. `pracuj`, `rocketjobs`, `justjoinit`, `jooble`, `manual`
- source_url  
  oryginalny link do oferty
- source_id  
  identyfikator oferty na portalu, jeśli dostępny
- retrieval_method  
  np. `manual_text`, `url_parse`, `file_upload`
- retrieval_timestamp
- raw_language
- source_note  
  np. informacja o tym, że oferta pochodzi z agregatora

### Cel:
Ten obiekt opisuje, skąd pochodzi oferta i jak została pozyskana.

---

## 4. RawJobInput
Surowa, nieprzetworzona forma oferty pracy.

### Zawiera:
- raw_text  
  pełna treść oferty
- raw_html  
  opcjonalnie HTML strony
- raw_title
- raw_company_name
- raw_location
- raw_salary_text
- raw_sections  
  lista fragmentów wykrytych sekcji, np. „wymagania”, „obowiązki”, „oferujemy”
- metadata  
  referencja do SourceMetadata

### Cel:
To jest warstwa wejściowa przed analizą AI i normalizacją danych.

---

## 5. CandidateProfile
Pełna, zaufana baza danych o kandydacie.

### Zawiera:
- personal_info
- target_preferences
- professional_summary_base
- experience_entries
- project_entries
- skill_entries
- education_entries
- certificate_entries
- language_entries
- achievements
- keywords_allowed
- keywords_forbidden
- immutable_claims
- source_documents

### Cel:
Jest to główne źródło prawdy o kandydacie.

---

## 6. CandidatePersonalInfo
Dane osobowe i kontaktowe użytkownika.

### Zawiera:
- full_name
- email
- phone
- linkedin_url
- github_url
- portfolio_url
- location_city
- location_country

### Uwagi:
To są dane do nagłówka CV i listu motywacyjnego.

---

## 7. TargetPreferences
Preferencje zawodowe kandydata.

### Zawiera:
- target_roles  
  lista stanowisk docelowych
- preferred_industries
- preferred_locations
- preferred_work_modes  
  np. `onsite`, `hybrid`, `remote`
- preferred_employment_types  
  np. `uop`, `b2b`, `uz`, `internship`
- preferred_seniority_levels
- salary_expectation_min
- salary_expectation_max
- salary_currency
- relocation_willingness
- business_travel_willingness

### Cel:
Umożliwia ocenę, czy oferta w ogóle ma sens dla użytkownika.

---

## 8. ExperienceEntry
Pojedynczy wpis doświadczenia zawodowego.

### Zawiera:
- id
- company_name
- position_title
- start_date
- end_date
- is_current
- location
- work_mode
- employment_type
- domain_industry
- responsibilities
- achievements
- technologies_used
- tools_used
- measurable_results
- keywords
- seniority_level
- evidence_strength  
  np. `high`, `medium`, `low`

### Cel:
To podstawowy materiał do dopasowywania CV do ogłoszenia.

---

## 9. ProjectEntry
Pojedynczy projekt, zawodowy lub własny.

### Zawiera:
- id
- project_name
- project_type  
  np. `commercial`, `academic`, `personal`
- role
- start_date
- end_date
- description
- responsibilities
- technologies_used
- tools_used
- outcomes
- keywords
- link
- evidence_strength

### Cel:
Pozwala dopasować doświadczenie nawet wtedy, gdy ogłoszenie lepiej pasuje do projektu niż do formalnego stanowiska.

---

## 10. SkillEntry
Pojedyncza umiejętność lub technologia.

### Zawiera:
- name
- category  
  np. `programming_language`, `framework`, `tool`, `soft_skill`, `domain_knowledge`
- proficiency_level
- years_of_experience
- last_used_date
- evidence_sources  
  referencje do ExperienceEntry lub ProjectEntry
- aliases  
  np. różne zapisy tej samej technologii

### Cel:
To ułatwia mapowanie słów kluczowych z ogłoszenia do faktycznych kompetencji.

---

## 11. EducationEntry
Pojedynczy wpis edukacyjny.

### Zawiera:
- institution_name
- degree
- field_of_study
- start_date
- end_date
- is_current
- location
- notes

---

## 12. CertificateEntry
Pojedynczy certyfikat lub szkolenie.

### Zawiera:
- certificate_name
- issuer
- issue_date
- expiry_date
- credential_id
- url
- keywords

---

## 13. LanguageEntry
Pojedynczy język obcy.

### Zawiera:
- language_name
- proficiency_level
- certification
- notes

---

## 14. SourceDocuments
Dokumenty źródłowe kandydata.

### Zawiera:
- base_cv_path
- additional_cv_paths
- portfolio_paths
- certificates_paths
- notes_paths

### Cel:
Referencje do dokumentów wejściowych, nie do publikacji.

---

## 15. JobPosting
Znormalizowana, ustrukturyzowana wersja oferty pracy.

### Zawiera:
- source_metadata
- basic_info
- company_info
- compensation
- employment_details
- role_profile
- requirements
- responsibilities
- benefits
- recruitment_process
- application_details
- portal_specific_fields
- parsing_notes

### Cel:
To główny obiekt reprezentujący ofertę po przetworzeniu.

---

## 16. JobBasicInfo
Podstawowe informacje o ofercie.

### Zawiera:
- title
- normalized_title
- company_name
- location_text
- locations
- country
- language_of_offer
- publication_date
- expiration_date
- is_active
- source_portal

---

## 17. CompanyInfo
Informacje o pracodawcy lub firmie rekrutującej.

### Zawiera:
- company_name
- hiring_company_name
- company_description
- industry
- company_size
- headquarters_location
- website
- brand_notes

### Cel:
Pomaga przy generowaniu listu motywacyjnego i lepszym dopasowaniu stylu CV.

---

## 18. Compensation
Wynagrodzenie i warunki finansowe.

### Zawiera:
- salary_min
- salary_max
- salary_currency
- salary_period  
  np. `month`, `hour`, `day`
- salary_type  
  np. `gross`, `net`, `net_b2b`
- salary_visible
- bonus_info
- additional_financial_notes

### Cel:
Obsługa widełek wynagrodzenia i różnych typów stawek.

---

## 19. EmploymentDetails
Warunki zatrudnienia.

### Zawiera:
- employment_types  
  lista, np. `uop`, `b2b`, `uz`
- work_mode  
  np. `onsite`, `hybrid`, `remote`
- working_time  
  np. `full_time`, `part_time`
- shift_work
- flexible_hours
- remote_recruitment
- immediate_start
- vacancies_count
- relocation_required
- travel_required

### Cel:
Zbiera parametry typu umowa, tryb pracy, wymiar czasu.

---

## 20. RoleProfile
Profil stanowiska.

### Zawiera:
- seniority_level
- function_area  
  np. `engineering`, `sales`, `marketing`, `operations`, `it`
- domain
- team_name
- role_summary
- tech_stack
- tags
- language_requirements_summary

### Cel:
To skrót najważniejszych informacji o roli.

---

## 21. Requirement
Pojedyncze wymaganie z oferty.

### Zawiera:
- id
- text
- normalized_text
- category  
  np. `technology`, `experience`, `education`, `language`, `soft_skill`, `certification`, `domain`
- subcategory
- importance  
  np. `critical`, `important`, `optional`
- requirement_type  
  `must_have` lub `nice_to_have`
- extracted_keywords
- years_required
- seniority_reference
- evidence_needed
- ambiguity_flag

### Cel:
To podstawowa jednostka analizy dopasowania.

---

## 22. ResponsibilityEntry
Pojedynczy obowiązek z oferty.

### Zawiera:
- id
- text
- category
- extracted_keywords
- importance

### Cel:
Obowiązki są osobnym typem treści, bo nie zawsze są tym samym co wymagania.

---

## 23. BenefitEntry
Pojedynczy benefit lub element oferty.

### Zawiera:
- text
- category  
  np. `health`, `learning`, `time_off`, `equipment`, `financial`, `culture`
- importance_estimate

---

## 24. RecruitmentStep
Pojedynczy etap rekrutacji.

### Zawiera:
- step_order
- step_name
- description
- is_optional

### Cel:
Przydatne szczególnie dla portali pokazujących etapy procesu.

---

## 25. ApplicationDetails
Informacje o aplikowaniu.

### Zawiera:
- apply_url
- application_deadline
- cv_required
- cover_letter_required
- portfolio_required
- additional_questions
- contact_person
- contact_email

---

## 26. PortalSpecificFields
Dane specyficzne dla danego portalu, które nie mieszczą się w modelu wspólnym.

### Zawiera:
- portal_name
- raw_key_value_pairs
- extracted_badges
- extracted_labels
- additional_notes

### Cel:
Zachowuje informacje niestandardowe bez psucia modelu głównego.

---

## 27. RequirementMatch
Wynik dopasowania pojedynczego wymagania do profilu kandydata.

### Zawiera:
- requirement_id
- match_status  
  `matched`, `partial`, `missing`, `uncertain`
- confidence_score  
  wartość 0.0–1.0
- matched_skills
- matched_experience_ids
- matched_project_ids
- evidence_texts
- explanation
- missing_gaps
- allowed_for_resume  
  wartość logiczna

### Cel:
Pokazuje, czy i jak kandydat spełnia dane wymaganie.

---

## 28. MatchResult
Wynik całościowego dopasowania profilu kandydata do oferty.

### Zawiera:
- overall_score
- fit_classification  
  `high`, `medium`, `low`
- recommendation  
  `generate`, `generate_with_caution`, `do_not_recommend`
- requirement_matches
- matched_requirements_count
- partial_requirements_count
- missing_requirements_count
- keyword_coverage_score
- role_alignment_score
- experience_alignment_score
- work_preference_alignment_score
- salary_alignment_score
- strengths_summary
- weaknesses_summary
- risk_flags
- final_reasoning

### Cel:
To główny wynik analizy dopasowania.

---

## 29. ResumeDraft
Treść CV przed wygenerowaniem pliku DOCX.

### Zawiera:
- header
- professional_summary
- selected_skills
- selected_experience_entries
- selected_project_entries
- selected_education_entries
- selected_certificate_entries
- selected_language_entries
- extra_sections
- keyword_usage
- tailoring_notes

### Cel:
To gotowa treść CV, ale jeszcze niezrenderowana do pliku.

---

## 30. ResumeHeader
Nagłówek CV.

### Zawiera:
- full_name
- target_title
- contact_line
- location
- links

---

## 31. ResumeExperienceEntry
Wpis doświadczenia po dopasowaniu do konkretnej oferty.

### Zawiera:
- source_experience_id
- company_name
- position_title
- dates
- location
- bullet_points
- highlighted_keywords
- relevance_score

### Cel:
To nie jest kopia 1:1 ExperienceEntry, tylko wersja dostosowana do tej jednej oferty.

---

## 32. ResumeProjectEntry
Wpis projektu po dopasowaniu.

### Zawiera:
- source_project_id
- project_name
- role
- bullet_points
- highlighted_keywords
- relevance_score

---

## 33. CoverLetterDraft
Opcjonalna treść listu motywacyjnego.

### Zawiera:
- header
- greeting
- opening_paragraph
- body_paragraphs
- closing_paragraph
- signature
- referenced_requirements
- referenced_evidence

### Cel:
Osobny obiekt dla listu motywacyjnego.

---

## 34. ChangeReport
Raport zmian względem profilu bazowego lub bazowego CV.

### Zawiera:
- added_elements
- removed_elements
- emphasized_elements
- reordered_elements
- omitted_elements
- omission_reasons
- keywords_detected
- keywords_used
- keywords_unused
- unsupported_items_blocked
- warnings

### Cel:
Daje użytkownikowi pełen wgląd w to, co system zrobił.

---

## 35. GenerationRun
Log pojedynczego uruchomienia systemu.

### Zawiera:
- run_id
- timestamp
- candidate_profile_version
- source_metadata
- input_job_reference
- parsed_job_reference
- match_result_reference
- resume_draft_reference
- cover_letter_reference
- change_report_reference
- status
- errors
- duration_ms

### Cel:
Umożliwia historię uruchomień i debugowanie procesu.

---

## 36. Relacje między obiektami
Relacje logiczne wyglądają następująco:

- SourceMetadata opisuje pochodzenie RawJobInput
- RawJobInput jest przetwarzany do JobPosting
- CandidateProfile i JobPosting są porównywane w celu uzyskania MatchResult
- MatchResult jest używany do stworzenia ResumeDraft
- ResumeDraft może być użyty do stworzenia CoverLetterDraft
- ResumeDraft i MatchResult są podstawą do wygenerowania ChangeReport
- całość jednego procesu jest zapisywana jako GenerationRun

---

## 37. Zasady modelowania danych
Przy dalszym rozwoju modelu należy pilnować następujących zasad:
- dane źródłowe muszą być oddzielone od danych wygenerowanych,
- wymagania z ogłoszenia muszą być modelowane osobno, a nie tylko jako jeden blok tekstu,
- każde mocne twierdzenie w CV powinno mieć referencję do danych źródłowych,
- model ma wspierać wiele portali, więc pola wspólne i portal-specific muszą być rozdzielone,
- brak danych nie oznacza spełnienia wymagania,
- dane muszą wspierać późniejszy audyt działania systemu.