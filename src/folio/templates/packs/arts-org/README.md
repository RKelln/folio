# arts-org — sage-wiki pack for arts organizations

An ontology, prompt templates, and config presets for building a knowledge wiki from an arts organization's documents: grant applications, exhibition records, program descriptions, governance docs, financial statements, personnel records, web pages, and events.

## What this pack provides

- **23 entity types** tuned for arts orgs: `funder`, `donor`, `grant_program`, `financial_fact`, `organizational_role`, `statistic`, `deadline`, `exhibition`, `program`, `person`, `artist`, `venue`, `equipment`, `policy`, `membership`, `volunteer`, `partner_organization`, `event`, `workshop`, `call_for_submissions`, `residency`, `festival`, `news_announcement`
- **19 relation types** for knowledge graph connections: `funded_by`, `reports_to`, `employs`, `scheduled_for`, `measured_in`, `exhibited_at`, `participates_in`, `governs`, `curated_by`, `partnered_with`, `donated_by`, `member_of`, `board_member_of`, `volunteers_for`, `speaks_at`, `teaches`, `part_of`, `submitted_to`, `announces`
- **6 prompt templates** for summarizing documents, extracting concepts, and writing wiki articles — all tuned to preserve exact figures, named entities, and institutional context
- **Compiler and search defaults** optimized for arts archive documents

## Version history

| Version | Changes |
|---------|---------|
| 1.0.0 | Initial release — 17 entity types, 14 relation types, 4 prompts |
| 1.1.0 | Added 6 entity types (`event`, `workshop`, `call_for_submissions`, `residency`, `festival`, `news_announcement`), 5 relation types (`speaks_at`, `teaches`, `part_of`, `submitted_to`, `announces`), and 2 new prompt templates for webpage content (`extract-webpage-concepts.md`, `summarize-webpage.md`). Updated existing relations with new valid sources/targets. |

## Install

```bash
sage-wiki pack install <path-to-pack>
sage-wiki pack apply arts-org --mode merge
```

## Entity summary

| Entity | Description |
|--------|-------------|
| funder | Grant-making organization or funding body |
| donor | Private donor, sponsor, or foundation |
| grant_program | Specific funding program, stream, or award |
| financial_fact | Dollar amount, budget item, or grant figure |
| organizational_role | Staff position, board role, personnel category |
| statistic | Demographic percentage, attendance, membership count |
| deadline | Application, reporting, or compliance deadline |
| exhibition | Art exhibition, show, screening, or public presentation |
| program | Educational program, workshop series, residency, mentorship |
| person | Individual — board, staff, contractor, volunteer, member |
| artist | Artist, collective, curator, or creative practitioner |
| venue | Physical space, gallery, facility, or site |
| equipment | Technical equipment, tools, hardware, studio resources |
| policy | Organizational policy, fee schedule, governance rule |
| membership | Membership structure, category, tier, program |
| volunteer | Volunteer position, hours, program |
| partner_organization | Collaborating organization, co-presenter, partner |
| event | Panel, artist talk, lecture, performance, screening |
| workshop | Hands-on educational session |
| call_for_submissions | Open call for artists, curators, or participants |
| residency | Artist-in-residence program |
| festival | Multi-event program (e.g., Vector Festival) |
| news_announcement | Organizational news (hiring, AGM, policy, award) |

## Relation summary

| Relation | Connects |
|----------|---------|
| funded_by | Concepts → funders/grant programs |
| reports_to | Organizations → funders |
| employs | Organizations → personnel |
| scheduled_for | Concepts → deadlines |
| measured_in | Statistics/financial data → sources |
| exhibited_at | Exhibitions/events → venues |
| participates_in | Artists/orgs → programs/exhibitions |
| governs | Roles → orgs/programs |
| curated_by | Exhibitions/events → artists |
| partnered_with | Orgs/events → partners |
| donated_by | Concepts → donors/sponsors |
| member_of | Individuals → memberships |
| board_member_of | Individuals → board roles |
| volunteers_for | Individuals → programs/events |
| speaks_at | People/artists → events/festivals |
| teaches | People/artists → workshops/programs |
| part_of | Events/workshops → festivals/programs |
| submitted_to | Artists → calls/grant programs |
| announces | Organizations → news announcements |

## License

MIT
