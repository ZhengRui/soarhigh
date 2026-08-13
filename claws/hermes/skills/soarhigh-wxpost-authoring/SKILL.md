---
name: soarhigh-wxpost-authoring
description: Navigate Feishu WxPost workspaces, manage their Materials, generate selected-image descriptions, and author or revise one canonical Draft. Use for Feishu workspace operations, web Materials descriptions, Draft generation, Regenerate, and explicit Draft Assistant writing revisions.
---

# SoarHigh WxPost authoring

Use only the WxPost MCP tools exposed for the current platform for every
canonical read and write. Feishu receives the complete Materials-and-Draft
surface; the web Draft Assistant receives only read and Draft tools. The
workspace ID in the request is authoritative. Never search the filesystem for
another workspace and never edit `source-manifest.json` or
`draft/article.json` directly.

## Feishu conversational workflow

The `wxpost_navigation` tools are available only in Feishu. The plugin derives
the current member, message, and conversation scope from the Hermes gateway;
never ask the member for a chat ID, user ID, thread ID, or message ID and never
invent one.

### Feishu interaction modes

Every Feishu conversation starts in `readonly` mode. The selected workspace
remains available as context, so the assistant may read its configuration,
Materials, and saved Draft; answer workspace or general questions; search the
web; and deliver preview links or screenshots. It must not create, update, or
delete workspace, Materials, or Draft data in this mode. The plugin enforces
this boundary before every write tool, including raw MCP tools.

- `/editing` requests editing mode. The first message only explains the risk
  and stages the request. The same member must send `/editing` again in a later
  message to confirm it.
- `/readonly` immediately restores read-only mode.
- `/new`, selecting another workspace, and completing workspace creation all
  restore read-only mode.
- If a member requests a write while read-only, do not keep retrying tools.
  Explain that nothing changed and ask them to send `/editing` and confirm it.
- Files sent while read-only remain ordinary conversational inputs: inspect and
  discuss them normally without importing them. Only an explicit request to add
  those files to Materials requires editing mode and a later resend.
- Read-only mode is not a separate workspace or Hermes session. It preserves
  current conversation context while preventing canonical writes.
- For any factual question about the selected Workspace, Materials, or Draft,
  read `wxpost_get_active_workspace_report` before answering. Never reuse a
  version, title, media list, or other workspace fact from earlier chat
  history. General conversation does not require a workspace read.

1. Use `wxpost_list_workspaces` for global discovery and
   `wxpost_get_active_workspace` to resolve the workspace selected for this
   Feishu conversation. Use `wxpost_select_workspace` before any workspace
   operation when the member chooses a different one. A Hermes `/new` command
   clears conversation history but intentionally preserves this selection and
   restores read-only mode. Selecting a workspace also restores read-only mode.
2. Workspace creation requires editing mode. Before creation, collect the fixed
   Source, linked meeting/event when
   applicable, Article type, and optional custom Article type. Use
   `wxpost_search_meetings` to present real choices. Restate those choices and
   call `wxpost_create_workspace` with `confirmed=false` to register the exact
   pending proposal before asking for explicit confirmation. Only a later
   member message may call the same proposal with `confirmed=true`. Source,
   linked meeting/event, Article type, and custom Article type cannot be
   changed after creation.
3. Workspace deletion requires editing mode and always targets the workspace
   selected for the current Feishu conversation. Before deletion, name the exact
   selected workspace and ask for explicit
   confirmation, and call `wxpost_delete_workspace` with `confirmed=false` to
   register that exact pending deletion. Only a later member message may call
   the same deletion with `confirmed=true`.
4. Materials imports and updates require editing mode. A linked meeting/event
   may expose unimported meeting-library options in the
   Materials stage. Call `wxpost_import_source` to import a selected option.
   After import, call it imported media. The media library is the complete
   catalog, so distinguish unimported candidates from imported media whenever
   listing or counting it.
5. When the current Feishu message contains files and an active workspace is
   selected, call `wxpost_import_feishu_attachments` with the exact cache paths
   shown in the message. New attachments are workspace-ready and excluded from
   generation by default unless the member explicitly asks to include them.
   Never repeat or expose those private cache paths in the member-facing reply.
   If no workspace is selected, ask the member to select or create one and then
   resend the files; do not queue file paths across turns.
6. In editing mode, pass the selected workspace ID explicitly to the normal
   authoring tools for
   Materials and Draft operations. Feishu may update Materials, generate a
   Draft, answer questions about the saved Draft, and make typed Draft edits.
   It must not create, update, or delete a public WxPost revision.
7. When the member asks for the workspace configuration, call
   `wxpost_get_active_workspace_report`. When the member asks to view the media
   library, call `wxpost_show_material_library`; it sends the complete catalog
   as native Feishu media and labels candidates separately from imported media.
8. When the member asks for an AI description for an imported image, call
   `wxpost_describe_material` with `confirmed=false`. Present its exact English
   suggestion and ask whether to save it. This first call does not change
   Materials. Only after the same member explicitly confirms in a later message
   call the tool for the same source with `confirmed=true`; that saves the
   staged suggestion as an AI-authored, confirmed Materials description. Do not
   call `wxpost_update_sources` for this workflow and never describe an
   unimported candidate directly.
9. After Generate, Regenerate, or any successful Draft save/edit, call
   `wxpost_get_draft_preview` for the version just saved. The tool sends the
   complete temporary preview link and authenticated web editor link directly
   to Feishu; do not repeat, shorten, or reconstruct either URL in the
   member-facing reply. Do the same when the member explicitly asks to preview
   the saved Draft. The temporary link is read-only, short-lived, and
   version-bound; it does not create or update a public WxPost revision. The
   editor link opens the same workspace in Draft Edit so a signed-in member can
   continue editing. Remind the member that the signed-in web Draft
   Assistant uses an independent Web session and does not inherit the current
   Feishu conversation, although both operate on the same workspace and Draft.
   A successful `sent: true` result completes delivery:
   do not call the tool again and do not attempt to open the member's local URL.
   It also means both the temporary preview and Draft Edit links were delivered;
   do not call `wxpost_send_web_editor_link` in that turn. In the final reply,
   confirm delivery without writing any URL or reusing a link from chat history.
   If link delivery fails, report that preview delivery
   failed without changing or retrying the Draft save.
10. Call `wxpost_send_draft_preview_image` only when the member explicitly asks
   for a screenshot, full-page image, or “整篇预览图”. It renders the saved
   Draft through the same canonical renderer as the web editor and sends one
   native Feishu image. Do not send the image automatically after ordinary
   Draft edits. A screenshot failure must not mutate Draft, Materials, or public
   revision state, and must never be replaced with an older workspace image.
11. When the member explicitly asks to edit Materials on the web, call
   `wxpost_send_web_editor_link` with `target=materials`. When the member asks
   to edit the Draft on the web, call it with `target=draft`. The tool sends the
   authenticated route directly to Feishu; do not repeat, shorten, or
   reconstruct the URL. For Draft editing, remind the member that the web Draft
   Assistant session is independent from this Feishu conversation, while both
   still operate on the same workspace and Draft. A `sent: true` result
   completes delivery and must not be retried.
   Do not call this tool when the same request includes a temporary Draft
   preview; `wxpost_get_draft_preview` already sends the Draft Edit link beside
   the temporary preview.

## Materials image-description workflow

The Controller-owned description service inspects only the selected imported
image. It writes one short, natural English sentence that captures the main
human moment and its visible mood. This is an editorial caption, not an
inventory of everything visible: incidental furniture, refreshments, signage,
clothing, and background objects are omitted unless essential to the moment.
When a current description exists in any language, the service preserves its
supported meaning while translating, compressing, and polishing it. The image
and current description are authoritative; linked meeting theme, introduction,
and agenda are supporting context only. The service never invents a person,
role, award, quotation, reaction, or event. The web Materials page keeps the
result local until `Save Materials`, which confirms and persists it. Feishu
uses the explicit two-turn `wxpost_describe_material` confirmation workflow
above. Neither suggestion step changes Materials or the Draft.

## Web Draft workflow

1. For Generate, Regenerate, a question about the saved article, or a Draft
   revision, call `wxpost_get_context` with the requested workspace ID. A
   general question that does not depend on the workspace can be answered
   directly without calling a workspace tool.
2. When context is read, compare its `manifestVersion` and `draftVersion` with the expected
   versions in the request. If either differs, stop without saving; never adopt
   a newer version or retry with guessed versions.
3. Treat the returned manifest, saved draft, and `meetingContext` as the only
   current state. `meetingContext` is live read-only context for a linked
   meeting; it is null for an independent article and is not stored in the
   workspace.
4. For Generate or Regenerate, create one complete English article proposal
   from the saved editorial brief, the selected content recipe, live linked
   meeting facts when present, and saved included materials.
5. For a question about the saved article, answer from the context without
   saving. For a small revision, change only what the member requested through
   `wxpost_edit_draft`. Its body node indexes must come from the current
   `draft.editContext`; never guess or relocate a target by matching text. Use
   `wxpost_save_draft` only for whole-article restructuring or rewriting.
   Presentation is preserved by the controller.
6. For `wxpost_edit_draft`, pass the request's expected `manifestVersion`,
   expected `draftVersion`, and the smallest explicit typed edit list. Include
   the exact `operation_id` only where the tool schema requires it: the Web
   bound tool (`wxpost_edit_current_draft`) binds the operation identity
   server-side and takes no `operation_id` argument.
   A title, excerpt, byline, body node, directive field or
   item, media occurrence, media description, or cover change is a fine-grained
   edit. `setCover` may directly select any imported workspace-ready image; it
   does not insert that image into the body or change Materials inclusion.
   `replaceMediaDescription` changes only the caption stored in the Draft. It
   never changes a Materials description. If the requested source is not in the
   Draft body or cover, explain that there is no Draft caption to edit and that
   its Materials description must be changed on the Materials page. Do not call
   a Draft save tool for that request.
7. Call `wxpost_save_draft` with the request's expected `manifestVersion`,
   expected `draftVersion` (zero when absent), `operation_id`,
   `refresh_from_materials`, and the complete `proposal`. Generate and
   Regenerate use the six top-level arguments:
   `workspace_id`, `expected_manifest_version`, `expected_draft_version`,
   `operation_id`, `refresh_from_materials`, and `proposal`. Use `true` for
   Generate or Regenerate so the new Draft adopts current Materials. A focused
   whole-article revision also includes `media_changes` and uses
   `refresh_from_materials=false`. Where the schema includes `operation_id`,
   copy it exactly from the current request, never from an earlier turn; the
   Web bound tool (`wxpost_save_current_draft`) binds the operation identity
   server-side and takes no `operation_id` argument.
   Never call a Materials mutation tool during a Draft Assistant turn.
8. Report success only after one save succeeds. If the first call is rejected
   before saving solely by the proposal schema or ArticleDocument validation,
   correct the proposal from that formal validation error and make one
   replacement call with the same expected versions. Never parse or repair
   serialized YAML, guess a version, retry a version conflict, or make more
   than two total save attempts.

## Media terminology and operation boundary

- “素材库” or “media library” means the complete workspace catalog: both
  linked-meeting candidates and imported media. When asked for its size or
  contents, report the total and split it into candidates and imported media.
- “候选素材” or “candidate media” means linked meeting/event media that has
  not been imported. Candidates are visible in Materials but cannot be used by
  the Draft until they are imported.
- “已导入素材” or “imported media” means uploaded or imported
  `workspaceReady` media. This is the only physical media the Draft can use.
- “Included 素材” means imported media selected for the next Generate or
  Regenerate. Inclusion does not control later focused Draft edits.
- “Draft 素材” means imported media currently referenced by the saved Draft
  body or cover.
- A focused Draft revision may add any imported medium, including one that is
  not Included. It must never add an unimported candidate.
- The Web Draft Assistant cannot mutate Materials. Materials descriptions,
  inclusion, import, and deletion remain Materials-stage operations even when
  the same source is referenced by the Draft.

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
- For Generate or Regenerate, every Materials-included image or video must
  appear exactly once in `media`; do not add excluded or non-media sources.
- For a focused revision, Materials inclusion no longer controls the Draft.
  The available pool is every imported `workspaceReady` image or video. Keep
  existing Draft media unless the member explicitly requests a removal. An
  imported source may be added even when its Materials `included` value is
  false. Never add a source that has not been imported.
- Clearing a cover does not move that image into the article body. If the
  current cover is cover-only, clear `coverMediaId` and declare that source in
  `removedMediaIds`; it remains imported and available in the workspace media
  library. Keep it in Draft media only when the article body already references
  it, or when the member explicitly asks to place it in the body.
- Each media item contains its manifest `id`, a concise natural-English article
  `description`, optional `credit`, and optional `people`.
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

## Focused revision media changes

Prefer `wxpost_edit_draft` for a focused media or cover change:

- `setCover` selects any imported workspace-ready image. The controller derives
  the cover-only dependency; the image does not need to appear in the body or
  have Materials `included: true`.
- `clearCover` removes only the cover relationship. A body occurrence remains.
- `insertImage` inserts an imported image at one explicit body index without
  changing Materials inclusion.
- `deleteMediaOccurrence` removes the occurrence at one explicit body node.
  `removeMediaFromBody` removes the canonical body occurrence by source ID
  without requiring its node index. Neither operation clears the cover.
- Never delete a workspace source or mutate Materials during Draft editing.

The complete `media_changes` contract below applies only when a whole-article
focused revision genuinely requires `wxpost_save_draft`:

Every focused revision save includes `media_changes` alongside the proposal:

```json
{
  "addedMediaIds": [],
  "removedMediaIds": [],
  "cover": {"action": "preserve"}
}
```

- For an unrelated text edit, leave both ID lists empty and preserve the cover.
- `addedMediaIds` and `removedMediaIds` describe membership in the Draft media
  array, not where an existing medium appears in the body. Add an ID only when
  it is absent from the saved Draft and the member asks to insert that imported
  medium or use it as the cover. If a cover-only medium is moved into the body,
  leave both lists unchanged.
- Remove an ID only when the member asks to remove it from the Draft entirely.
  If a body medium remains as the cover, leave both lists unchanged. Draft
  membership changes do not delete the workspace source or change its
  Materials inclusion.
- Use `{"action":"set","sourceId":"M02"}` to select a cover and
  `{"action":"clear"}` to remove one. Otherwise use `preserve`.
- The proposal and declared changes must agree. A removed medium must no longer
  be referenced by a block or cover. An added medium must be represented in the
  proposal and referenced by a media-bearing block or cover.

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
