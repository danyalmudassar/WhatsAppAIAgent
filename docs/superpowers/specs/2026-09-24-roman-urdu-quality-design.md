# Natural Balanced Roman Urdu Response Quality

## Goal

Improve the agent's Roman Urdu so responses sound natural, clear, and useful
without forcing every technical term into Urdu or changing the existing
Roman-Urdu-only product behavior.

## Approved approach

Use a stronger response-policy prompt and focused regression tests. Do not add
post-processing or automatic rewrites in the first iteration because those can
change meaning and hide model-quality problems.

## Response rules

- Write in Roman Urdu using Latin/ASCII characters; do not use Urdu script.
- Prefer short, natural sentences and familiar everyday wording.
- Use English only for technical terms, product names, commands, code, URLs,
  filenames, and unavoidable domain vocabulary.
- Keep one idea per sentence and avoid literal word-for-word translations.
- Match the user's tone while remaining respectful and direct.
- For WhatsApp, keep replies concise and easy to scan.
- Preserve exact values such as IDs, error codes, URLs, commands, and code.
- Do not add unnecessary headings, repeated conclusions, or filler.
- If a term is ambiguous, explain it briefly in natural Roman Urdu instead of
  inventing a translation.

## Scope

The policy applies to successful agent responses generated through the
LangGraph response path and WhatsApp-facing replies. Authentication, dashboard
status labels, API payloads, and stored configuration values are not translated
by this change.

## Validation

Add regression coverage for:

1. A casual greeting.
2. A technical explanation that retains necessary English terms.
3. An error or troubleshooting response.
4. A concise WhatsApp reply.
5. A response containing a URL, command, or identifier.

Tests should verify Roman Urdu policy behavior without requiring one exact model
sentence, and must continue passing with the existing response-language
configuration.

## Acceptance criteria

- New generated responses follow the rules above in representative tests.
- Existing tools, memory, WhatsApp delivery, and response contracts are
  unchanged.
- No Urdu-script characters are introduced by the response policy.
- Technical terms, commands, URLs, and identifiers remain intact.
- Backend test and lint suites pass.
