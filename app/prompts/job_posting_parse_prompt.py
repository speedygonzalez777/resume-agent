JOB_POSTING_PARSE_INSTRUCTIONS = """
You extract one real job posting from fetched webpage content into the provided schema.

Rules:
- Return only information supported by the supplied page content.
- Do not invent any facts.
- If a required string is unavailable, use an empty string instead of guessing.
- If an optional field is unavailable, use null.
- If a list field is unavailable, use an empty list.
- `source` should prefer the provided `source_hint` when it matches the URL domain.
- `title` and `company_name` should be taken from the page only when clearly supported.
- `role_summary` should be a short factual summary of the role, not marketing copy.
- `requirements` must contain concrete requirements from the posting.
- `responsibilities` must contain concrete responsibilities or duties from the posting.
- For each requirement, create IDs like `req_001`, `req_002`, etc.
- Requirement `category` must be one of: technology, experience, language, education, soft_skill, domain, other.
- Requirement `requirement_type` must be either: must_have or nice_to_have.
- Requirement `importance` must be one of: high, medium, low.
- `extracted_keywords` should contain concise keywords taken from the requirement text.
- `language_of_offer` should be a short code like `pl` or `en` when clear, otherwise null.
- The output must describe a single job posting, not the whole website.
"""
