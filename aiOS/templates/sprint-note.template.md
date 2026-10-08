---
up: []
tags:
  - sprint
related: []
coverage: {{start_date}}..{{end_date}}
created: {{start_date}}
updated: {{end_date}}
sources: []
aliases:
  - "Sprint {{n}}"
---

# {{quarter}} — Sprint {{n}} ({{start_date}} → {{end_date}})

<!-- One paragraph on THE SPRINT, not on this note. What was it about, what came of it, what didn't happen, and the next sprint's name. The merge is one closing clause at most ("The day notes and daily briefings of <range> were folded into this note and removed; their external sources are consolidated in the frontmatter."). Do not open with which files were merged — that is a work log, not a sprint overview. -->

## For stakeholders — sprint at a glance

<!-- Plain-language executive summary for POs/stakeholders. No stack traces, commit hashes, or code identifiers. 4-6 bullets covering: what shipped and why it matters, releases that went out, QA/blocker resolution, stability/engagement trend in plain terms, what's still open, what's next. -->

- 

<div style="break-after: page;"></div>

## Headline: {{theme}}

<!-- Name this for what changed, not for how the work went: "the app learns to start without the network", not "offline translations, decided and built in one sprint". Repeat this section per throughline if the sprint had several (Q32026 sprint 2 has three); delete the spare if it had one.

Prose tells the story — the problem in human terms, the finding that changed the plan, the decision that turned on a fact. Put any ticket-by-ticket inventory in a TABLE (# | the question | what was decided) rather than enumerating tickets inline; a wall of IDs reads as a data dump even to an engineer. A page-break div precedes every major section for PDF export. -->

<div style="break-after: page;"></div>

## Releases & deadlines

<!-- A release is a BUILD that went to an environment — confirm it against apps/*/CHANGELOG.md and the pubspec version, and ask the user; the day notes routinely miss end-of-day uploads. Do not confuse a mobile build upload with the company-wide dev -> staging BRANCH sync, which is owned outside mobile and can slip without holding the mobile build. State plainly which environments did and did not move, and name the versions. -->

- **PRODUCTION**: 
- **STAGING**: 
- **DEV**: 
- Other milestones/deadlines (met, at risk, or missed) with linked `[[project]]`.

## Feature & QA highlights

<!-- Design handoffs, QA sweeps, bugs found/fixed/deferred, feature requests filed. Rename this heading to fit the sprint's actual substance (e.g. "POD & QA"). -->

<div style="break-after: page;"></div>

## Decisions

<!-- Bullet per decision: what was decided, who decided it, and whether it's still open. Call out anything raised repeatedly but never resolved. -->

<div style="break-after: page;"></div>

## Reliability — Crashlytics & Analytics

<!-- Only include if Crashlytics/Analytics snapshots were pulled during the sprint (via day notes or briefings). Build one row per snapshot date. -->

| Snapshot date | Android crash-free (users / sessions) | iOS crash-free | Dominant non-fatal |
|---|---|---|---|
|  |  |  |  |

```mermaid
xychart-beta
    title "Crash-free users % (7-day rolling)"
    x-axis [ ]
    y-axis "Crash-free users %" 0 --> 100
    line "Android" [ ]
    line "iOS" [ ]
```

<!-- Narrative: the dominant failure cluster and its trend, blind spots in what is measured, anomalies worth flagging. -->

| Metric | | | | |
|---|---|---|---|---|
| DAU (Daily Active Users) | | | | |
| WAU (Weekly Active Users) | | | | |
| MAU (Monthly Active Users) | | | | |
| Avg. engagement / active user | | | | |
| Engaged sessions / active user | | | | |

```mermaid
xychart-beta
    title "Active Users (28-day rolling)"
    x-axis [ ]
    y-axis "Users" 0 --> 0
    line "DAU" [ ]
    line "WAU" [ ]
    line "MAU" [ ]
```

<div style="break-after: page;"></div>

## Engineering & conventions

<!-- Cross-cutting technical decisions, new shared components/atoms, new IdeaVerse conventions recorded this sprint, anything that should outlive the sprint. -->

<div style="break-after: page;"></div>

## Open, carried into {{next_sprint}}

**Design**

- [ ] 

**Backend**

- [ ] 

**Mobile**

- [ ] 

**Other**

- [ ] 
