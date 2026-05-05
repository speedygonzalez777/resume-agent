// =========================
// OPTIONS
// =========================
#let language = "en" // "pl" | "en"
#let include_photo = false // true | false
#let consent_mode = "default" // "default" | "custom" | "none"

// If consent_mode == "custom", paste your own clause here.
#let custom_consent_text = [
  Wklej tutaj własną klauzulę.
]

// =========================
// HELPERS: TRANSLATIONS
// =========================
#let txt(pl, en) = (pl: pl, en: en)
#let pick(value) = if language == "pl" { value.pl } else { value.en }

// =========================
// DATA
// =========================
#let photo_path = "assets/example-profile.jpg"

#let profile = (
  full_name: "ALEX EXAMPLE",
  email: "alex.example@example.com",
  phone: "+48 000 000 000",
  linkedin: "linkedin.com/in/alex-example",
  github: "github.com/alex-example",
)

#let labels = (
  email: txt("Email:", "Email:"),
  phone: txt("Telefon:", "Phone:"),
  linkedin: txt("LinkedIn:", "LinkedIn:"),
  github: txt("GitHub:", "GitHub:"),
)

#let section_titles = (
  summary: txt("PODSUMOWANIE", "SUMMARY"),
  education: txt("WYKSZTAŁCENIE", "EDUCATION"),
  experience: txt("DOŚWIADCZENIE", "EXPERIENCE"),
  projects: txt("PROJEKTY", "PROJECTS"),
  skills: txt("UMIEJĘTNOŚCI", "SKILLS"),
  languages: txt("JĘZYKI I CERTYFIKATY", "LANGUAGES & CERTIFICATES"),
)

#let thesis_label = txt("Praca dyplomowa:", "Thesis:")

#let summary_text = txt(
  "Przykładowy profil techniczny łączący podstawy automatyki, aplikacje Pythonowe i dokumentację inżynierską. Rozwija projekty demonstracyjne oparte na danych, prostych integracjach systemowych i czytelnej komunikacji technicznej.",
  "Example technical profile combining automation fundamentals, Python applications and engineering documentation. Develops demo projects based on data, simple system integrations and clear technical communication.",
)

#let education_entries = (
  (
    institution: txt(
      "Example University of Technology, Example City",
      "Example University of Technology, Example City",
    ),
    date: txt("2026–obecnie", "2026–Present"),
    degree: txt(
      "Studia magisterskie z inżynierii systemów — specjalizacja analiza danych",
      "Master's degree in Systems Engineering — Data Analysis Specialization",
    ),
    thesis: none,
  ),
  (
    institution: txt(
      "Example University of Technology, Example City",
      "Example University of Technology, Example City",
    ),
    date: txt("2022–2026", "2022–2026"),
    degree: txt(
      "Studia inżynierskie z automatyki i systemów technicznych",
      "Engineer's degree in Automation and Technical Systems",
    ),
    thesis: txt(
      "Platforma demonstracyjna robotyki z prostym sterowaniem wbudowanym, narzędziami Pythonowymi do testów oraz dokumentacją techniczną.",
      "Design of a robotics demo platform with simple embedded control, Python-based testing tools and technical documentation.",
    ),
  ),
)

#let experience_entries = (
  (
    company: txt("Orion Systems, Example City", "Orion Systems, Example City"),
    role: txt("Inżynier automatyk", "Automation Engineer"),
    date: txt("10.2025 – 03.2026", "Oct 2025 – Mar 2026"),
    bullets: (
      txt(
        "Pracowałem nad przykładowymi zadaniami sterowania dla linii szkoleniowej, obejmującymi logikę PLC, dokumentację testów oraz weryfikację scenariuszy pracy.",
        "Worked on sample control tasks for a training line, covering PLC logic, test documentation and verification of operating scenarios.",
      ),
      txt(
        "Współtworzyłem systemy automatyki budynkowej oparte na IoT dla przykładowych obiektów oraz rozwój aplikacji Inventory Assistant App w interdyscyplinarnym środowisku inżynierskim.",
        "Contributed to IoT-based building automation systems for sample facilities and the Inventory Assistant App in a multidisciplinary engineering environment.",
      ),
    ),
  ),
  (
    company: txt("Northbridge Automation, Example City", "Northbridge Automation, Example City"),
    role: txt("Praktykant ds. elektrycznych", "Electrical Engineering Intern"),
    date: txt("06.2025 – 08.2025", "Jun 2025 – Aug 2025"),
    bullets: (
      txt(
        "Montowałem szafy sterownicze na podstawie dokumentacji technicznej oraz weryfikowałem poprawność schematów elektrycznych i okablowania.",
        "Assembled control cabinets based on technical documentation and verified electrical diagrams and wiring correctness.",
      ),
      txt(
        "Wykonywałem podstawowe pomiary elektryczne i wspierałem prace instalacyjne przy przykładowych panelach szkoleniowych.",
        "Performed basic electrical measurements and supported installation work on sample training panels.",
      ),
    ),
  ),
)

#let project_entries = (
  (
    name: txt("Resume Tailoring Agent", "Resume Tailoring Agent"),
    description: txt(
      "Stworzyłem aplikację w Pythonie do dostosowywania CV pod oferty pracy, integrując backend FastAPI, frontend React, bazę SQLite oraz OpenAI API do parsowania ofert, dopasowania profili i generowania szkiców CV.",
      "Developed a Python application for CV tailoring that integrates a FastAPI backend, React frontend, SQLite database, and OpenAI API to parse job offers, match profiles, and generate tailored resume drafts.",
    ),
  ),
  (
    name: txt("Interfejs sterowania grą gestami", "Gesture-Controlled Game Interface"),
    description: txt(
      "Stworzyłem interfejs sterowania grą w Pythonie wykorzystujący ruch dłoni do sterowania postacią w czasie rzeczywistym w projekcie z zakresu interakcji człowiek–komputer.",
      "Developed a Python-based gesture-controlled game interface using hand-motion input for real-time character control and interactive human-computer interaction.",
    ),
  ),
)

#let skill_entries = (
  txt(
    "Software & AI: Python, FastAPI, SQLite, OpenAI API, uczenie maszynowe, analiza danych",
    "Software & AI: Python, FastAPI, SQLite, OpenAI API, machine learning, data analysis",
  ),
  txt(
    "Automation & Control: podstawy PLC, logika sterowania, dokumentacja techniczna, testy, integracja czujników, MQTT",
    "Automation & Control: PLC fundamentals, control logic, technical documentation, testing, sensor integration, MQTT",
  ),
  txt(
    "Kompetencje miękkie: analityczne podejście do rozwiązywania problemów, zarządzanie czasem i organizacja pracy, współpraca zespołowa, adaptacyjność",
    "Soft skills: analytical problem-solving, time management and work organization, collaborative mindset, adaptability",
  ),
)

#let language_certificate_entries = (
  txt("Polski — ojczysty", "Polish — Native"),
  txt("Angielski — C1", "English — C1"),
  txt("Niemiecki — A2", "German — A2"),
  txt("Example English Certificate (B2)", "Example English Certificate (B2)"),
  txt("Example Elec Cert (1kV)", "Example Elec Cert (1kV)"),
  txt("Przykładowe szkolenie BHP", "Example safety training"),
)

#let default_consent_text = txt(
  "Wyrażam zgodę na przetwarzanie moich danych osobowych w celu prowadzenia rekrutacji na stanowisko, na które aplikuję, zgodnie z Rozporządzeniem Parlamentu Europejskiego i Rady (UE) 2016/679 z dnia 27 kwietnia 2016 r. (RODO).",
  "I consent to the processing of my personal data for the purposes necessary to conduct the recruitment process for the position I am applying for, in accordance with Regulation (EU) 2016/679 of the European Parliament and of the Council of 27 April 2016 (GDPR).",
)

// =========================
// GLOBAL LAYOUT
// =========================
#set page(
  paper: "a4",
  margin: (
    top: 0.68cm,
    bottom: 0.72cm,
    left: 1.05cm,
    right: 1.05cm,
  ),
)

#set text(
  font: "Calibri",
  size: 10.6pt,
)

#set par(
  justify: false,
  leading: 0.68em,
)

#set list(
  tight: true,
)

#let header_height = 3.45cm
#let no_photo_header_top_offset = 0.82cm

#let section(title) = [
  #v(0.03cm)
  #grid(
    columns: (1fr,),
    row-gutter: 0.05cm,
    [
      #text(
        size: 13.2pt,
        weight: "bold",
        bottom-edge: "bounds",
      )[#title]
    ],
    [
      #line(length: 100%, stroke: 0.6pt)
    ],
  )
  #v(0.012cm)
]

#let dated-line(lhs, rhs) = [
  #block[
    #grid(
      columns: (1fr, auto),
      column-gutter: 0.4cm,
      align: (left, right),
      lhs,
      rhs,
    )
  ]
]

#let render-bullet-list(items) = list(
  ..items.map(item => [#pick(item)])
)

#let render-education-entry(entry) = [
  #dated-line(
    [#text(weight: "bold")[#pick(entry.institution)]],
    [#pick(entry.date)],
  )
  #pick(entry.degree)
  #if entry.thesis != none [
    #v(0.01cm)
    #emph[#pick(thesis_label) #pick(entry.thesis)]
  ]
]

#let render-experience-entry(entry) = [
  #dated-line(
    [#text(weight: "bold")[#pick(entry.company)] — #emph[#pick(entry.role)]],
    [#pick(entry.date)],
  )
  #render-bullet-list(entry.bullets)
]

#let render-project-list(entries) = list(
  ..entries.map(entry => [
    #text(weight: "bold")[#pick(entry.name)] — #pick(entry.description)
  ])
)

#let render-skill-list(entries) = list(
  ..entries.map(entry => [#pick(entry)])
)

#let render-language-certificate-list(entries) = list(
  ..entries.map(entry => [#pick(entry)])
)

#let render-header() = [
  #block(height: header_height)[
    #if include_photo [
      #grid(
        columns: (1fr, 3.1cm),
        column-gutter: 0.28cm,
        align: (left, top),
        [
          #v(0.02cm)
          #text(size: 21pt, weight: "bold")[#profile.full_name]
          #v(0.07cm)

          #text(size: 9.9pt)[
            #strong[#pick(labels.email)] #profile.email   |   #strong[#pick(labels.phone)] #profile.phone
          ]
          #v(0.015cm)
          #text(size: 9.9pt)[
            #strong[#pick(labels.linkedin)] #profile.linkedin
          ]
          #v(0.015cm)
          #text(size: 9.9pt)[
            #strong[#pick(labels.github)] #profile.github
          ]
        ],
        [
          #align(left)[
            #image(photo_path, width: 2.75cm, height: 3.45cm, fit: "cover")
          ]
        ],
      )
    ] else [
      #pad(top: no_photo_header_top_offset)[
        #align(center)[
          #text(size: 21pt, weight: "bold")[#profile.full_name]
          #v(0.07cm)

          #text(size: 9.9pt)[
            #strong[#pick(labels.email)] #profile.email   |   #strong[#pick(labels.phone)] #profile.phone
          ]
          #v(0.015cm)
          #text(size: 9.9pt)[
            #strong[#pick(labels.linkedin)] #profile.linkedin
          ]
          #v(0.015cm)
          #text(size: 9.9pt)[
            #strong[#pick(labels.github)] #profile.github
          ]
        ]
      ]
    ]
  ]
]

#let render-consent() = {
  if consent_mode == "custom" {
    custom_consent_text
  } else {
    pick(default_consent_text)
  }
}

// =========================
// DOCUMENT
// =========================
#render-header()

#section(pick(section_titles.summary))
#pick(summary_text)

#section(pick(section_titles.education))
#for (idx, entry) in education_entries.enumerate() [
  #render-education-entry(entry)
  #if idx < education_entries.len() - 1 [
    #v(0.03cm)
  ]
]

#section(pick(section_titles.experience))
#for (idx, entry) in experience_entries.enumerate() [
  #render-experience-entry(entry)
  #if idx < experience_entries.len() - 1 [
    #v(0.035cm)
  ]
]

#section(pick(section_titles.projects))
#render-project-list(project_entries)

#section(pick(section_titles.skills))
#render-skill-list(skill_entries)

#section(pick(section_titles.languages))
#render-language-certificate-list(language_certificate_entries)

#if consent_mode != "none" [
  #place(bottom + center, dy: -0.12cm)[
    #text(size: 8pt)[
      #render-consent()
    ]
  ]
]
