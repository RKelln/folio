# extract-webpage-concepts.md
# Conservative extraction — one primary concept per webpage.
# Override this in .folio/sage-wiki/prompts/ for per-project tuning.
#
# Available variables: {{.ExistingConcepts}}, {{.Summaries}}
# See: https://github.com/xoai/sage-wiki

You are extracting the PRIMARY topic from each source for a knowledge wiki about a non-profit arts organization.

## Existing concepts (do not duplicate):
{{.ExistingConcepts}}

## Source summaries:
{{.Summaries}}

## Rules

For each source, extract at most **ONE concept** — the main subject of the page:

- An **event** (artist talk, panel, lecture, performance, screening) → the event title
- A **workshop** → the workshop title
- An **exhibition or festival** → the exhibition/festival name
- A **news announcement** → the subject (hiring notice, AGM, award, policy change)
- A **call for submissions or residency** → the call/program title
- A **named person** → the person's name (only if the page is primarily ABOUT them, not just mentioning them as a speaker/organizer)
- If no clear primary topic → skip the source (do not create a concept)

Do NOT extract secondary entities as separate concepts. Speakers, venues, funders, partner organizations, and dates belong as wikilinks *inside* the primary article — not as standalone concept pages.

Do NOT extract:
- Broad categories (visual-arts, media-arts)
- Generic descriptors (non-profit, artist-run-centre)
- Abstract nouns (accessibility, community-engagement)
- Single passing mentions with no actionable information

## Consolidation

Before outputting, check for duplicates. Same entity under different names → ONE concept with aliases.

Output ONLY a JSON array of objects. No markdown, no explanation.
