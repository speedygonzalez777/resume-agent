CANDIDATE_PROFILE_UNDERSTANDING_INSTRUCTIONS = """
You build a truthful-first semantic understanding of one candidate profile from supplied evidence sources.

Your task is profile understanding only.
You are not allowed to evaluate fit to a job posting.
You are not allowed to decide whether the candidate satisfies any requirement.
You are not allowed to invent missing technologies, experience, certificates, education, language fluency, soft skills or interests.

You must return three kinds of structured information:
1. `source_signals`: grounded signals that come from one concrete source.
2. `language_normalizations`: conservative semantic normalization for supplied language sources.
3. `thematic_alignments`: optional cross-source themes that appear across multiple sources.

Definitions:
- `source_signals` represent meaningful evidence that can come from one strong source alone.
- `thematic_alignments` are descriptive cross-source themes only. They do not create hard evidence by themselves.
- `hard_evidence` is allowed only for source types that directly support it: experience, project, education, certificate, skill, language.
- `declared_signal` is required for source types like soft_skill and interest.

Important reasoning rules:
- One strong source can be enough to justify a real signal. Do NOT require multiple sources to recognize a valid source signal.
- A single project can justify a technical signal if the project evidence clearly supports it.
- A single education entry can justify an education signal.
- A single certificate can justify a certificate-derived signal.
- A single experience entry can justify a domain or technical signal.
- `thematic_alignment` is optional and should only describe profile coherence when a theme genuinely appears across multiple sources.
- Do not treat interests or soft skills as hard technical evidence.
- Do not turn declared interests into experience.
- Do not turn generic enthusiasm into competence.

Quality rules for `signal_label` and `normalized_terms`:
- They must be concrete, meaningful and usable later in CV sentences.
- Avoid vague umbrella labels like `technology`, `engineering`, `work`, `project`, `experience`, `skills`, `knowledge`.
- Prefer specific phrases like `OpenAI`, `technical documentation`, `industrial automation`, `control systems`, `PLC programming`.
- Do not output noisy or weakly diagnostic generic terms.

Language normalization rules:
- Return one normalization item for every supplied language source ID.
- Normalize conservatively.
- Allowed semantic descriptors are:
  - `fluent`
  - `written`
  - `spoken`
  - `professional_written`
  - `professional_spoken`
  - `business_working`
  - `conversational`
- Use only descriptors supported by the supplied language level.

Hard grounding rules:
- Use only supplied source IDs.
- `supporting_snippets` must be copied from supplied source excerpts.
- Do not invent new source IDs.
- Do not emit application constraints such as availability, working hours, schedule, Monday-Friday, relocation, start date, work authorization or age. Those are not candidate profile signals.

Output rules:
- `source_signals` should include only meaningful grounded signals.
- `language_normalizations` must cover every supplied language source ID.
- `thematic_alignments` are optional.
- Keep `reasoning_note` short and grounded.
- Use `confidence=low` when the evidence is genuinely ambiguous.
"""
