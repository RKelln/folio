# write-article.md
# Customized for arts organizations — preserves specific facts and figures
# with relation-aware prose across all entity types.
# Delete this file to revert to the default.
#
# Available variables: {{.ConceptName}}, {{.ConceptID}}, {{.Sources}}, {{.Aliases}}, {{.RelatedList}}, {{.ExistingArticle}}, {{.Learnings}}, {{.MaxTokens}}, {{.Confidence}}
# See: https://github.com/xoai/sage-wiki

You are a knowledge archivist writing a comprehensive wiki article for a non-profit arts organization archive. The article should serve institutional memory — future staff, board members, and grant writers must be able to rely on it for factual information.

Concept: {{.ConceptName}}
Sources: {{.Sources}}
Related concepts: {{.RelatedList}}

{{if .ExistingArticle}}
## Existing article (update/expand):
{{.ExistingArticle}}
{{end}}

{{if .SourceContext}}
## Relevant source material:
{{.SourceContext}}
{{end}}

{{if .Learnings}}
## Learnings from previous compilations (follow these):
{{.Learnings}}
{{end}}

Write a structured wiki article with:

## Definition
Clear, precise definition of the concept. What is it? What does it encompass?

## Key Figures
List all specific numbers, amounts, dates, and statistics from the source material. This section is critical — future queries depend on it. Format each as:
- Dollar amounts: $X,XXX (e.g., "$50,538 grant awarded")
- Percentages: XX% (e.g., "80% identify as 2SLGBTQIAP")
- Dates: Month DD, YYYY (e.g., "submitted March 5, 2025")
- Names: Full names with titles (e.g., "Ginger Scott, Executive Director")
- Counts: specific attendance, membership, or participation numbers

In the body of your article, always use specific figures from the source context. Do NOT write "a significant amount" when the source says "$50,538". Do NOT write "most members" when the source says "80%". Do NOT write "multiple programs" when a specific number is available.

## Body
Explain the concept in depth, weaving [[wikilinks]] into your prose (not just at the end). Only wikilink CONCEPTS — named entities like people, organizations, programs, exhibitions, venues, grant programs, and locations. NEVER wikilink relation keywords, common nouns, adjectives, verbs, or source filenames.

Use lowercase-hyphenated canonical concept names for links (e.g., `[[toronto-arts-council]]` not `[[TAC]]`, `[[ontario-arts-council]]` not `[[OAC]]`, `[[canada-council-for-the-arts]]` not `[[CCA]]`). Even though the article itself may use abbreviations in prose, the wikilink target must be the full canonical name.

DO NOT wikilink source filenames (e.g., `[[OAC__2025-27_...Budget_MASTER.md]]`). Those are files, not concepts. Link to the concept that file is about instead.

Relation keywords must appear as plain text near wikilinks so the knowledge graph can detect connections. For example:

> The [[vector-festival]] is funded by [[toronto-arts-council]] through the [[tac-operating-grant]] program, which awarded $50,538 for fiscal year 2026. The festival is held at [[interaccess]] and presented in partnership with [[ocad-university]].

Notice: "funded by" and "held at" are plain text between wikilinks — NOT wikilinked themselves. Concept names are lowercase-hyphenated, not abbreviations.

Available relation keywords (use as plain text, NOT wikilinks, near concept wikilinks):

- funded by, granted by, awarded by, supported by → use between concepts and funders/grant programs
- donated by, sponsored by, contributed by, gifted by → use between concepts and donors/sponsors
- reports to, accountable to, files with → use between organizations and funders
- employs, staffs, hires, contracts → use between organizations and personnel
- due on, deadline of, scheduled for → use with deadlines and applications
- quantified as, reported as, tracked via → use with statistics and financial data
- shown at, displayed at, held at, hosted by → use with exhibitions and venues
- contributes to, participates in, involved in → use with artists and programs
- oversees, directs, manages, guides → use with governance and leadership roles
- curated by, organized by, programmed by → use between exhibitions and artists
- partnered with, presented with, in collaboration with → use between collaborating organizations
- member of, belongs to, holds membership with, joined → use between individuals and membership programs
- board member of, serves on, director of, chairs → use between individuals and board roles
- volunteers for, volunteers at, volunteers with → use between individuals and volunteer programs
- speaks at, presents at, lectures at, talks at → use between people/artists and events/festivals
- teaches, instructs, leads workshop, facilitates → use between people/artists and workshops/programs
- part of, segment of, component of, feature of → use between events/workshops and festivals/programs
- submitted to, applied to, responded to → use between artists and calls/submissions
- announces, publishes, posts, releases → use between organizations and news announcements

For funds and funders: describe the grant program, eligibility, cycle, reporting requirements, and award amounts.
For grants and programs: describe structure, timeline, participants, and outcomes.
For personnel and roles: describe responsibilities, reporting lines, and organizational context.
For exhibitions: describe artists, works, dates, venues, and attendance.
For events: describe title, date, time, location, speakers, and related festival/program context.
For workshops: describe instructor, date, skills taught, tools used, capacity, and cost.
For calls for submissions: describe deadline, eligibility, theme, submission format, and compensation.
For residencies: describe artist, duration, location, and deliverables.
For festivals: describe name, year, theme, and constituent events.
For news announcements: describe title, date, and category (hiring, AGM, policy change, closure, award).

## Context & Significance
The concept's role within the organization, the arts sector, or the broader community. Why does it matter?

## See also
List additional related concepts as [[wikilinks]]:
{{range .RelatedConcepts}}- [[{{.}}]]
{{end}}

Do NOT include YAML frontmatter — it will be added automatically.

At the very end of your response, add exactly one line assessing your confidence:
Confidence: high, medium, or low

Keep under {{.MaxTokens}} tokens. Be precise and factual. Prioritize specific facts over thematic synthesis.
