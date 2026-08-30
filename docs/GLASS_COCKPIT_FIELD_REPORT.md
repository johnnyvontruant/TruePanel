# Project GLASS COCKPIT field report

Inspected 2026-08-30. This is a reproducible design benchmark, not a popularity
contest and not a human-usability study. The canonical source list is
`truepanel/glass_cockpit/study.py`; CI enforces exactly 100 unique HTTPS evidence
sources and the declared 25/20/15/15/10/10/5 cohort split.

## Selection and provenance

The traffic cohort uses Similarweb's *Most Visited Websites in the World* table,
published 2026-05-14 from May 2026 traffic. It selects the first 25 eligible,
unique consumer/product interfaces: adult and wagering sites were excluded,
and duplicate Microsoft destinations were not counted as distinct interfaces.
Consequently the cohort extends through rank 32. This is selection from a named
ranking, not a claim that all selected interfaces have equal relevance.

The six expert cohorts intentionally correct the consumer sample's bias: 20
operations consoles; 15 NAS/homelab administration products; 15 maintained
design systems; 10 visualization systems; 10 high-stakes human-factors sources;
and 5 accessibility-first public systems. Each row states whether the evidence
was a public interface, official documentation, official code, a specification,
or screenshots, and records authentication, locale, paid-standard, or live-data
limitations. Proprietary assets and layouts were not copied.

Primary anchors:

- Similarweb ranking: https://www.similarweb.com/blog/research/market-research/most-visited-websites/
- WCAG 2.2: https://www.w3.org/TR/WCAG22/
- IBM Carbon dashboards: https://carbondesignsystem.com/data-visualization/dashboards/
- GOV.UK details guidance: https://design-system.service.gov.uk/components/details/
- FAA Human Factors Design Standard: https://www.faa.gov/air_traffic/publications/atpubs/hfds/
- FDA human-factors guidance: https://www.fda.gov/regulatory-information/search-fda-guidance-documents/applying-human-factors-and-usability-engineering-medical-devices

## Scorecard

Every interface was inspected with the same questions: time-to-orient and
hierarchy; task prominence and scan path; card fragmentation; progressive
disclosure; tile/sparkline/chart/table/topology/narrative choice; typography and
spacing; semantic color and non-color cues; responsive reflow, touch targets,
and overflow; loading/empty/stale/disconnected/warning/critical/recovery states;
keyboard, focus, screen-reader, reduced-motion, chart alternatives, and WCAG 2.2
AA; and interaction cost for the eight Mission Control tasks. Access limitations
are data, not missing footnotes. Observed facts were kept separate from the
following design inferences.

## Repeated findings

1. **One orientation surface wins.** Consumer search and content products put
   the core intent first; mature operations systems put health, scope, and time
   context first. Mission Control should answer *Now / Why / Safest Move / Proof*
   before presenting instrumentation. Confidence: high across all cohorts.
2. **Group by operator decision, not telemetry producer.** NAS consoles often
   fragment disks, pools, alerts, and jobs. Observability consoles are clearer
   when related evidence shares scope and time. Cooling plus hottest-drive trend
   belongs together; unrelated configuration does not. Confidence: high.
3. **Disclosure has a safety boundary.** GOV.UK explicitly warns against hiding
   content most users need. Details are appropriate for evidence history,
   configuration explanation, and advanced diagnostics; never for an incident,
   action, or verification state. Confidence: high.
4. **Current value and trajectory are different questions.** A tile answers
   “what is it now”; a sparkline adds direction with little space; a full graph
   earns its footprint only when time, threshold crossing, or correlation changes
   the decision. Every chart needs a textual/table alternative. Confidence: high.
5. **Calm status is stronger than decorative alarm color.** High-stakes guidance
   and public design systems pair color with words, shape, hierarchy, and explicit
   recovery state. Reserve salience for conditions that change action. Confidence:
   high.
6. **Phone layouts must recompose.** Columns become one scan path; labels precede
   values; controls remain at least 44 CSS pixels; no card requires horizontal
   scrolling or precision tapping. Confidence: high.

## Counterexamples that should not transfer

- High-traffic feeds optimize engagement, infinite discovery, and personalization;
  those goals conflict with finite operational orientation.
- Cloud observability products tolerate configurable dashboard sprawl because
  specialist teams curate them. TruePanel needs a safe default, not a blank canvas.
- Desktop-style NAS launchers expose many applications equally. That metaphor
  delays incident recognition and does not survive phones well.
- Aviation density is justified by trained crews, standardized scan patterns,
  redundant physical controls, and recurrent training. Copying the visual density
  without those conditions would be cockpit theater.
- Maps, animated charts, glass blur, and large graphs were rejected when they did
  not change an operator decision.

## Build/adopt decision

No runtime design library was adopted. TruePanel's dependency-light static UI and
embedded appliance context make a new framework costlier than the small semantic
layout. We adapted public semantics: Carbon's metric restraint and text-backed
charts; GOV.UK's disclosure boundary and visible focus; WCAG 2.2 reflow, contrast,
focus, and target requirements; and high-stakes *recognize, diagnose, act, verify*
ordering. No third-party source, visual asset, font, binary, tracking code, or
credential was incorporated, so no new runtime attribution notice is required.

## Limits and next human study

Public evidence cannot reveal private product telemetry, internal research, or
expert operator training. Automated DOM, overflow, contrast, and task-path checks
are heuristics—not observed usability. The next study should recruit at least one
new and one experienced TruePanel operator for think-aloud tests on incident,
stale, disconnected, recovery, and no-incident states, recording errors and time
without using a production host.
