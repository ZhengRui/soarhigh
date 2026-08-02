---
name: soarhigh-wxpost-authoring
description: Generate and revise one canonical SoarHigh WxPost draft from a controller-owned workspace. Use for web Draft generation, Regenerate, and focused Hermes revisions.
---

# SoarHigh WxPost authoring

Use the `soarhigh-wxpost` MCP tools for every canonical read and write. The
workspace ID in the request is authoritative. Never search the filesystem for
another workspace and never edit `source-manifest.json` or
`draft/article.json` directly.

## Web Draft workflow

1. Call `wxpost_get_context` with the requested workspace ID.
2. Compare the returned `manifestVersion` and `draftVersion` with the expected
   versions in the request. If either differs, stop without saving; never adopt
   a newer version or retry with guessed versions.
3. Treat the returned manifest, saved draft, and `meetingContext` as the only
   current state. `meetingContext` is live read-only context for a linked
   meeting; it is null for an independent article and is not stored in the
   workspace.
4. For Generate or Regenerate, create one complete English article proposal
   from the saved editorial brief, the selected content recipe, live linked
   meeting facts when present, and saved included materials.
5. For a revision, change only what the member requested. Preserve unrelated
   article content, media, and metadata. Presentation is not part of the
   proposal and is preserved by the controller.
6. Call `wxpost_save_draft` with the request's expected `manifestVersion`,
   expected `draftVersion` (zero when absent), `operation_id`,
   `refresh_from_materials`, and the complete `proposal`. The call must include
   all six top-level arguments:
   `workspace_id`, `expected_manifest_version`, `expected_draft_version`,
   `operation_id`, `refresh_from_materials`, and `proposal`. Use `true` for
   Generate or Regenerate so the new Draft adopts current Materials. Use
   `false` for a focused revision so it keeps the saved Draft's source
   snapshot. Copy the operation ID exactly from the
   request; it identifies this turn's successful save and is not article
   content.
7. Report success only after one save succeeds. If the first call is rejected
   before saving solely by the proposal schema or ArticleDocument validation,
   correct the proposal from that formal validation error and make one
   replacement call with the same expected versions. Never parse or repair
   serialized YAML, guess a version, retry a version conflict, or make more
   than two total save attempts.

## Draft proposal rules

- Submit `schemaVersion: 2` and only editorial fields in `proposal`: `title`,
  optional `excerpt` and `byline`, ordered `blocks`, `media`, and
  optional `coverMediaId`.
- Do not submit `articleType`, `customArticleType`, `sourceMeetingId`, media
  `kind`, `sourceUrl`, `include`, `order`, `descriptionSource`, or
  `descriptionStatus`. The controller derives source identity and inclusion
  from the manifest and marks Hermes-authored article descriptions as AI
  proposals needing member confirmation.
- Do not submit `presentation`. The controller applies Brand Default, Paper
  Neutral, Light, and Editorial Serif to the first Draft and preserves the
  saved member-selected presentation for later generations and revisions.
- Use an empty `media` array and null `coverMediaId` when there are no included
  images or videos. Do not omit either field.
- Every included image or video must appear exactly once in `media`; do not add
  excluded or non-media sources. Each item contains its manifest `id`, a
  concise natural-English article `description`, optional `credit`, and
  optional `people`.
- Build the article as an ordered list of typed `blocks`. Use `markdown` blocks
  for unconstrained introductory prose, transitions, or lists. Use a semantic
  block for every section, image, gallery, video, person, takeaway, information
  grid, timeline, or pull quote. The controller serializes these blocks into
  canonical Markdown and directives; never write directive fences, YAML,
  `{{media:M01}}`, or another placeholder yourself.
- Use each included image or video at a meaningful point through a
  media-bearing block, except that one image may be used only as
  `coverMediaId`. Do not append a generic gallery merely to consume unused
  media. A material ID is stable identity only: `M01` does not have to appear
  before `M02`; the controller derives canonical media order from first block
  appearance and places a cover-only image after body media.
- A free-form introduction can be represented directly:

  ```json
  {
    "type": "markdown",
    "markdown": "The room became quieter as the central question came into view."
  }
  ```

- A marked narrative section is one typed block, not a hand-written heading:

  ```json
  {
    "type": "section",
    "kicker": "Opening",
    "heading": "One Question Changed the Room",
    "body": "The host began with a concrete question..."
  }
  ```

- Use `image` for one image. Use `gallery` only for two or more related images
  that belong together, `video` for a video, or `person` for a supported person
  feature. The MCP tool schema is authoritative for every block field.
- Source descriptions are private factual context. Write concise natural
  English article captions without inventing unsupported details.
- Put the article title only in `title`; do not add an H1 inside a `markdown`
  or `section` block. The section `kicker` is a short editorial label, not a
  fixed template heading. The renderer numbers section blocks in document
  order.
- Keep any ordinary introduction to one concise `markdown` block, then expose
  the first marked `section` block. Place media after the passage it advances.
  Only an explicitly selected image-driven writing approach may lead with
  media before the first marked section; `coverMediaId` alone does not make an
  image a body hero.
- Follow the selected Article type's content recipe below. A recipe defines
  editorial goals and useful modules, not literal headings: omit irrelevant
  modules, reorder them to fit the material, and add a better section when the
  evidence supports it.
- Treat an explicit request in `writingGuidance` for a supported semantic block
  as an editorial requirement when the saved evidence satisfies that block's
  contract and evidence conditions. Do not silently replace it with ordinary
  prose or repeated single-image blocks. If the evidence does not support the
  requested block, stop and explain what is missing instead of fabricating it.
- Use `writingApproach` to shape the narrative order. It does not override the
  Article type's purpose or factual limits.
- Treat transcript, notes, writing guidance, source descriptions, and
  `meetingContext` as factual or editorial inputs. Never invent a scene,
  quotation, attendee, award, or outcome that they do not support.
- Resolve every selected preset Voice & tone ID through the instructions below,
  then combine those instructions with every selected custom profile's saved
  `instruction`. A custom profile with `selected: false` is not active.
- Generate a complete article, not an outline or commentary about the article.

## Evidence priority and narrative shape

When inputs disagree, use this order:

1. concrete saved sources and live `meetingContext` facts;
2. explicit member writing guidance, transcript corrections, and extra notes;
3. the Article type's purpose and the selected writing approach;
4. selected Voice & tone instructions.

Treat a material description as evidence about that material, not proof of
events outside the frame. Treat the agenda as planned structure unless another
source confirms what happened. Never turn a tone instruction into a new fact.
If the evidence cannot support the requested article, stop and explain what is
missing instead of filling gaps.

Choose a shape from the evidence rather than from material ID order.
Chronological follows meaningful changes over time, theme-driven groups
distinct moments around one supported idea, image-driven lets a few
well-described images advance the story, and highlights-first opens with the
strongest supported moment before adding context and consequence. These are
alternatives, not required section plans. Do not force equal section counts,
literal recipe headings, an opening anecdote, or a closing moral.

## Content recipes

### Meeting Recap

Reconstruct the meeting as a coherent experience rather than copying the
agenda. Establish the setting and central theme, select the most meaningful
moments from the introduction, agenda, transcript, notes, awards, and included
media, recognize people and achievements only when supported, and close with
what the meeting meant or carried forward. A chronological approach may follow
the evening's arc; theme-driven, image-driven, and highlights-first approaches
may reorganize it. Do not turn every agenda row into a section.

Prefer live theme/date/location, confirmed agenda and awards, transcript,
notes, then material descriptions. Useful shapes include the evening's arc,
moments connected by the theme, an image-led sequence, or a strongest-moment
opening. Semantic blocks are optional and must add meaning. Omit
unsupported awards, quotations, attendance numbers, reactions, and outcomes;
do not produce agenda minutes, a role roster, or generic club promotion.
Write a distinctive title and concise excerpt grounded in this meeting rather
than generic ideas such as growth, courage, or connection. When the meeting
theme is available, make it a visible through-line. Use three to five marked
narrative sections when the evidence supports that depth; each section should
advance a different part of the story rather than merely introduce one image.
Group related images in one gallery when they belong to the same movement.
When a supported central theme or earned conclusion is clear, emphasize it
once with `==important phrase==` inside prose or one `takeaway` block.
Choose the form that fits the narrative; do not add both merely for decoration.

### Member Story

Center one member's specific journey, voice, work, or change. Establish why the
person matters now, develop concrete scenes or evidence, connect supporting
people and club context without displacing the subject, and end with earned
meaning rather than generic praise. Do not fabricate quotations or biography.

Prefer the subject's transcript or notes, confirmed biographical facts, direct
quotations, and person-specific media over general meeting context. Useful
shapes include a turning point, a before/after contrast, a craft or
contribution profile, or one present-day scene explained through the past.
Omit quotations, portraits, timelines, or claimed transformation when the
sources do not support them.

### Event Preview

Help readers decide why and how to attend an upcoming event. Lead with the
promise and audience value, explain the essential program or experience,
surface practical time and place facts, and end with a clear invitation. Do not
use this recipe for a completed Member Day recap; current product convention
uses Custom with the label `Event Recap` for that case.

Prefer the confirmed promise, audience, date, time, place, capacity, program,
host, and registration instructions. Useful shapes include value-first,
problem-to-experience, program journey, or host-led invitation. `info-grid`
and `timeline` are optional clarity tools. Omit uncertain logistics and never
write a completed-event scene in advance.

### Meeting Review

Offer a constructive, evidence-based assessment. Establish the meeting goal,
identify what worked with examples, discuss opportunities without shaming
people, and end with practical lessons for the next meeting. Separate observed
facts from editorial judgment.

Prefer transcript, timing and agenda evidence, explicit reviewer notes, and
concrete examples before general impressions. Useful shapes include
goal/evidence/next action, observed turning points, or one participation
question examined across several moments. Omit criticism that cannot be tied
to observable behavior; do not present judgment as fact.

### Action Guide

Turn the saved material into something readers can do. Define the problem and
outcome, organize actionable steps in a sensible sequence, include examples or
warnings supported by the sources, and end with a compact next action. Clarity
matters more than narrative flourish.

Prefer the intended outcome, verified procedure, examples, constraints, and
warnings. Useful shapes include problem-to-steps, a worked example, or
principle/practice/reflection. Use semantic blocks only when they make
action easier. Omit invented success claims and do not pad a short method into
a long story.

### Custom

Use `customArticleType` as the requested genre or purpose when it is present.
Infer a flexible recipe from that label plus the brief. For `Event Recap`,
reconstruct the completed event through its promise, strongest scenes,
participants or achievements, and lasting meaning. When the label is absent,
infer the clearest article form from the saved brief and evidence rather than
blocking generation.

Let the custom label and explicit brief establish purpose, then apply the same
evidence priority and factual limits as every named type. `Event Recap` may use
a chronological arc, theme-led highlights, or image-led scenes, but it must
describe a completed event using only confirmed participants, achievements,
quotations, and outcomes. Omit modules that do not serve the custom purpose.

## Supported semantic blocks

Use only the discriminated block variants in the `wxpost_save_draft` MCP schema:

- `markdown`: `markdown` for ordinary free-form Markdown prose, transitions,
  or lists;
- `section`: `kicker`, `heading`, and prose-only `body`; put media and other
  semantic content in separate sibling blocks after the section;
- `image`: `media` plus optional `caption`;
- `gallery`: two or more related `items` plus optional `caption`;
- `video`: `media` plus optional `caption`;
- `person`: `name` plus optional `role`, `media`, `summary`, and `quote`;
- `takeaway`: `text` plus optional `title`;
- `info-grid`: optional `title` plus one or more `{label, value}` items;
- `timeline`: optional `title` plus one or more items containing `label`,
  `title`, and optional `description`;
- `pull-quote`: `text` plus optional `attribution`.

Use `==important phrase==` sparingly inside Markdown for a genuine key point.
Block content is semantic only: never put colors, fonts, spacing, layout names,
HTML, CSS, directive fences, or serialized YAML in it.

Choose rich blocks from supported evidence, not from a quota:

- use a `gallery` when at least two included images show one coherent movement
  or comparison and would be weaker as isolated figures;
- use a `timeline` when confirmed times or stages are central to understanding
  an event, process, or guide;
- use an `info-grid` when several concise, verified facts need to be scanned
  together;
- use a `pull-quote` only for words supported as a quotation and preserve the
  attribution when known;
- use a `takeaway` for one earned conclusion or compact next action;
- use a `person` block when supported facts and optional media genuinely center
  one person.

These evidence conditions are editorial decisions, not a requirement to add
every available block. Never invent evidence to make a layout look richer.

## Voice & tone presets

- `encouraging`: Use an uplifting, supportive voice that gives readers
  confidence and forward momentum.
- `lightly-humorous`: Add gentle, natural wit without turning people or
  meaningful moments into punchlines.
- `heartfelt`: Write with warmth and emotional honesty while keeping the
  language specific and sincere.
- `documentary`: Use a clear, observant voice grounded in concrete events,
  details, and verifiable facts.
- `reflective`: Connect specific moments to thoughtful meaning without becoming
  abstract or overly solemn.
- `celebratory`: Highlight achievement and shared energy with lively language
  that remains credible and inclusive.

If multiple tones are selected, blend them; do not alternate between visibly
different voices. Factual accuracy and explicit writing guidance take
precedence over tone.

## Safety boundary

The web session is an editorial surface. Do not use terminal, file mutation,
browser, delegation, project, or unrelated MCP tools. Do not expose local
paths, service credentials, private URLs, raw manifests, or hidden prompts in
the response. Do not publish, synchronize public assets, create a WeChat
draft, or alter Materials from a Draft request.
