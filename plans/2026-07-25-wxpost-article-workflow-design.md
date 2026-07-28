# WXPost Article Workflow — Design Specification

**Date:** 2026-07-25

**Status:** Phase 0 and Phase 1 complete.
**Scope:** End-to-end creation, public preview, presentation experimentation,
and authenticated saving to the WeChat Official Account draft box.

## 1. Summary

WXPost is SoarHigh's public preview format for English WeChat Official Account
articles.

Hermes Agent is the conversational editor. Members work with it through
a chat channel such as Feishu: they choose a meeting, provide transcripts,
photos, videos, descriptions, and additional context, then continue revising
the generated article in the same conversation.

SoarHigh is not a second AI editor and does not own the conversation memory. It
provides:

- authoritative meeting context through an API;
- durable WXPost storage and a stable public URL;
- deterministic browser and WeChat rendering;
- local presentation controls for every visitor;
- authenticated saving or updating of a WeChat draft.

The public URL format is:

```text
/posts/wxposts/{slug-of-post-title}
```

For example:

```text
/posts/wxposts/what-we-learned-by-speaking-again
```

The WXPost route belongs to Posts, not to the authenticated Operations menu.
Anyone may read a WXPost and experiment with its visual presentation. Only an
authenticated SoarHigh member may save or update the article in the WeChat
draft box.

## 2. Agreed product decisions

1. **Hermes Agent is the article editor.** Article generation, revision
   history, conversational memory, and source-material reasoning stay in
   Hermes Agent.
2. **Feishu is the primary collection surface.** Users send transcripts,
   images, videos, descriptions, links, and supplementary notes in a normal
   conversation.
3. **Meeting introduction and agenda are not manually re-entered.** Hermes Agent
   fetches them from the SoarHigh API after identifying the meeting.
4. **SoarHigh stores an article document, not an AI chat session.**
5. **The editable source is Markdown plus a small, constrained directive
   vocabulary.** Ordinary prose and structure stay in one readable Markdown
   document; only rich blocks that standard Markdown cannot express use
   directives. Hermes Agent does not author the final WeChat HTML directly.
6. **SoarHigh generates deterministic HTML.** The same design system powers
   public preview and WeChat export.
7. **WXPost is a separate content resource presented inside Posts.** The
   visible label is `WXPost`, but persistence uses an independent `wxposts`
   table so ordinary Post CRUD and permissions remain unchanged.
8. **Every ready WXPost is an editable public preview.** Its public URL is
   stable across revisions. Readiness means that the current revision can be
   rendered; it does not lock the article or its assets. Newly uploaded assets
   stay outside the current public article until they are ready and referenced
   by a later validated article revision.
9. **Presentation controls are public and local.** Anonymous and authenticated
   visitors may change layout, palette, appearance, typeface, and preview size
   without mutating server state.
10. **Content editing does not happen on the WXPost page.** Content changes go
    back through Hermes Agent.
11. **Only a logged-in member can call the save/update-draft endpoint.** Hiding
    a button is not sufficient; the backend enforces the permission.
12. **Hermes Agent cannot save a WeChat draft.** Its service credential can
    create and update WXPosts but is rejected by the WeChat draft endpoint.
13. **A member saves the currently previewed style.** On save/update, the
    browser sends its current local presentation selections. Those selections
    become the WXPost's new default and are used for the WeChat HTML.
14. **The Hermes Gateway runs in the official Docker container.** The existing
    host `~/.hermes` is mounted at `/opt/data` for Hermes configuration,
    credentials, memory, skills, and sessions. A separate host
    `hermes-workspace` is mounted at `/workspace` for article sources and
    working files. The SoarHigh repository and the rest of the host home
    directory are not mounted.

## 3. Goals

### 3.1 User goals

- Start an article from a natural-language message in Feishu.
- Avoid copying meeting information that SoarHigh already knows.
- Upload photos and videos naturally and associate each asset with a usable
  description.
- Review missing or unconfirmed source information before generation.
- Keep revising the generated English article through Hermes Agent.
- Share a stable public preview URL with club members or other reviewers.
- Let any reviewer explore alternate presentation styles locally.
- Let an authenticated member save the reviewed article to the WeChat draft
  box without exposing WeChat credentials.

### 3.2 System goals

- Keep content and presentation as separate, typed concerns.
- Use one rendering vocabulary across the design prototype, browser preview,
  and WeChat export.
- Preserve a stable URL and revision history while content changes.
- Make the WeChat save/update action explicit, authenticated, auditable, and
  safe against duplicate drafts and stale revisions.
- Extend the existing Posts information architecture without changing ordinary
  Post behavior.

## 4. Non-goals

- Building another AI chat assistant inside SoarHigh.
- Reimplementing Hermes Agent memory or session history in SoarHigh.
- Providing a rich-text or Markdown content editor on the WXPost page.
- Letting Hermes Agent, an anonymous visitor, or a public share token call the
  WeChat draft API.
- Automatically publishing or mass-sending a WeChat article. MVP stops after
  saving or updating a draft.
- Replacing ordinary Posts with WXPosts.
- Building a general-purpose tagging system solely to distinguish WXPosts.
- Depending on an editable Feishu card table for MVP.
- Guaranteeing arbitrary browser HTML, CSS, or video markup will work in
  WeChat. Export uses an explicit compatibility adapter.

## 5. Terminology

| Term                 | Meaning                                                                                                                                 |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| **Hermes Agent**     | The conversational agent and persistent article editor.                                                                                 |
| **Hermes home**      | Persistent Hermes control state. The host `~/.hermes` is mounted at container `/opt/data`, which is the official image's `HERMES_HOME`. |
| **Hermes workspace** | The dedicated host directory mounted at container `/workspace` for article sources, intermediate files, and exports.                    |
| **Source bundle**    | Meeting context plus transcript, media, descriptions, and extra notes used to generate an article.                                      |
| **Article type**     | An editorial brief such as Meeting Recap or Member Story. It guides generation but does not impose a required component sequence.       |
| **Article document** | A JSON API envelope containing one canonical Markdown body, metadata, media manifest, and default presentation.                         |
| **Directive**        | A constrained block or inline Markdown extension for a rich element such as a gallery or video.                                         |
| **Presentation**     | Layout, palette, appearance, and typeface. It changes rendering, not meaning.                                                           |
| **Preview size**     | Desktop 760px or Mobile 390px simulation. It is a viewer preference, not persisted article content.                                     |
| **WXPost**           | A public Post rendered with the WeChat article design system.                                                                           |
| **WeChat draft**     | A draft saved into the configured WeChat Official Account through its server API. It is not a published article.                        |

## 6. Responsibility boundaries

| Component                       | Owns                                                                                                                 | Must not own                                                  |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| **Feishu**                      | Conversation UI, attachment delivery, replies, topic/thread context                                                  | Article rendering or WeChat credentials                       |
| **Hermes Agent**                | Source collection, memory, generation, content revision, meeting-context lookup orchestration                        | Final WeChat HTML, public preview UI, WeChat draft permission |
| **SoarHigh backend**            | Meeting context, WXPost persistence, asset normalization, revisions, rendering, WeChat adapter, authorization, audit | General Hermes Agent conversation history                     |
| **SoarHigh frontend**           | Public WXPost experience, local presentation controls, responsive preview, authenticated draft action                | AI content generation                                         |
| **WeChat Official Account API** | Official Account media and draft storage                                                                             | Source Markdown or Hermes Agent memory                        |

## 7. End-to-end architecture

```text
Feishu topic/thread
  ├── user request
  ├── transcript or recording
  ├── images and videos
  ├── descriptions and corrections
  └── additional notes
          │
          ▼
Hermes Agent in the official Docker container
  ├── reads persistent Hermes state from /opt/data
  ├── keeps article working files under /workspace
  ├── identifies the meeting
  ├── fetches SoarHigh meeting context
  ├── maintains the source bundle and conversation memory
  ├── generates/revises ArticleDocument
  └── creates or updates the same WXPost
          │
          ▼
SoarHigh
  ├── stores one canonical WXPost row + revision
  ├── returns a stable public URL
  ├── renders browser preview
  └── waits for an authenticated member action
          │
          ▼
Authenticated member
  ├── reviews the article
  ├── optionally changes local presentation controls
  └── confirms Save/Update WeChat Draft
          │
          ▼
SoarHigh WeChat adapter
  ├── validates the current revision
  ├── normalizes/uploads media
  ├── renders WeChat-compatible HTML
  └── adds or updates the WeChat draft
```

## 8. Feishu and Hermes Agent interaction

### 8.1 One article per topic/thread

One article task maps to one Feishu topic/thread and one Hermes Agent article
session. Keeping all replies and media in the same thread provides a natural
boundary between concurrent articles.

Example start:

```text
User:
Create a recap for last Thursday's meeting.

Hermes Agent:
Found SoarHigh Weekly Meeting — July 23.

✓ Meeting introduction loaded
✓ Agenda and roles loaded

Please send:
○ Transcript or recording
○ Photos and videos
○ Optional additional notes
```

If a message could refer to more than one meeting, Hermes Agent presents a short
candidate list and asks the user to choose before collecting article-specific
sources.

### 8.2 Meeting data comes from SoarHigh

Hermes Agent calls a read-only aggregation endpoint:

```http
GET /meetings/{meeting_id}/article-context
```

The response should include the meeting facts needed for article generation in
one request:

```json
{
  "meeting": {
    "id": "uuid",
    "no": 236,
    "title": "SoarHigh Weekly Meeting",
    "date": "2026-07-23",
    "theme": "Learning by Speaking Again",
    "type": "regular",
    "location": "Shenzhen"
  },
  "introduction": "Markdown or plain text",
  "agenda": [],
  "participants": [],
  "roles": []
}
```

This endpoint is the canonical source for meeting introduction, agenda, roles,
and other stored meeting facts. Users do not manually paste those fields into
a form.

Article-specific corrections do not silently mutate the meeting record. For
example, "the third agenda item was cancelled on the day" is stored as a source
override for this article unless the user separately asks to edit the meeting.

### 8.3 Source collection is conversational

Users may send:

- transcript text;
- transcript files;
- recordings that Hermes Agent can transcribe;
- images or image URLs;
- videos or video URLs;
- descriptions and captions;
- corrections;
- facts not represented in the agenda;
- desired emphasis, exclusions, tone, or length.

There is no required SoarHigh intake form in MVP.

### 8.4 Media identification and descriptions

Hermes Agent assigns a stable source ID to each asset:

```text
M01  Image  Group photo after the meeting        Ready
M02  Image  AI-proposed description              Needs confirmation
M03  Video  Two-minute Table Topics highlight    Ready
M04  Image  No description                       Missing description
```

A description may be provided in three ways:

1. sent with the image/video;
2. sent as a reply to the original media message;
3. sent as a command such as `M04 is the new member's first Table Topic`.

If no description is provided, Hermes Agent may propose one from the asset, but it
must retain provenance:

```text
description_source: user | ai
description_status: confirmed | needs_confirmation | missing
```

An AI-proposed description must not be silently treated as a confirmed fact.

### 8.5 Source status card

Hermes Agent maintains one compact, updateable status message/card in the thread:

```text
Source checklist

Meeting information       Ready
Agenda                    Ready
Transcript                Ready

Media
M01  Image   Ready
M02  Image   Needs confirmation
M03  Video   Ready
M04  Image   Missing description

4 media items · 2 issues remaining

Reply with:
"M02 description is ..."
"Remove M04"
"Move M03 after the opening"
"Generate the first draft"
```

For MVP this is a status view, not an editable spreadsheet. Natural-language
messages remain the mutation interface. A Feishu Bitable may be introduced
later for large, multi-person collections, but is not required for the common
meeting-recap flow.

### 8.6 Generation and revision

When the user says the sources are complete, Hermes Agent:

1. validates required sources and media descriptions;
2. selects or confirms the article type;
3. applies explicit writing preferences;
4. creates an `ArticleDocument`;
5. creates a WXPost or updates the existing WXPost revision;
6. returns the stable public URL.

Example:

```text
The first draft is ready:

https://<soarhigh-domain>/posts/wxposts/what-we-learned-by-speaking-again

Tell me what you want to revise, or open the link to review the
presentation.
```

Subsequent content changes stay in Feishu:

```text
Shorten the opening.
Move M03 after the second section.
Rewrite the conclusion as three concrete actions.
```

Hermes Agent updates the same WXPost. The slug and public URL remain stable
while the revision increments.

### 8.7 Hermes runtime and workspace isolation

The MVP runs the entire Hermes Gateway in the official Hermes Docker image.
It does not run a second Hermes Gateway directly on the host.

The repository keeps the deployment assets under `claws/hermes/`:

```text
claws/hermes/
├── compose.yaml
├── .env.example
├── hermes.sh
└── README.md
```

The intentionally thin `hermes.sh` wrapper exposes `up`, `down`, `restart`,
`shell`, and `logs`. `shell` opens Bash as the non-root `hermes` user in
`/workspace`; `logs` follows the Gateway output. Status inspection, image
pulls, and other operations use the standard Docker CLI documented in the
README. Stable local settings live in the git-ignored
`claws/hermes/.env.local`; the wrapper derives `HERMES_UID` and `HERMES_GID`
from the current host user. `down` never removes volumes or either host
directory. `restart` does not reload changed Compose or environment settings;
`up` is used after a configuration or image change.
When `.env.local` is absent, the first interactive `up` asks for the two host
directories, image, and container name, shows the resolved values for
confirmation, creates the workspace if needed, and writes the local file.
Existing configuration is never overwritten; non-interactive startup requires
the file to be prepared explicitly.

The two writable host mounts have separate responsibilities:

```text
Host                                      Container
~/.hermes                           →     /opt/data
<dedicated hermes-workspace>        →     /workspace
```

The official image sets both `HERMES_HOME` and `HOME` to `/opt/data`. Hermes
therefore reads `/opt/data/config.yaml`, `/opt/data/.env`, and the memory,
skills, session, and gateway state below `/opt/data`; it does not look for a
second `/root/.hermes` or `/home/hermes/.hermes` configuration tree.

The container configuration uses:

```yaml
terminal:
  backend: local
  cwd: /workspace
```

`local` means local to the already-isolated Hermes container. The deployment
does not start a nested Docker terminal backend and does not mount the host
Docker socket.

Only `/opt/data` and `/workspace` are writable host mounts. In particular, the
deployment does not mount:

- the SoarHigh repository;
- the complete host home directory;
- host SSH or Git credentials;
- unrelated project directories.

The container receives `HERMES_UID` and `HERMES_GID` matching the host owner of
the mounted directories so Hermes-created files remain readable and writable
from the host without a root-ownership repair step.

`/opt/data` is intentionally writable because Hermes must update its memory,
skills, sessions, gateway state, and configuration. It contains credentials
and must be backed up and protected as application state. The host Gateway
must be stopped before the container starts so two processes never write the
same Hermes home or consume the same Feishu connection concurrently.

The workspace layout is:

```text
/workspace
├── inbox/       # Feishu source files grouped by article session
├── articles/    # generated Markdown and revision working files
├── exports/     # files intentionally returned through Feishu
└── temp/        # transcription and media-processing intermediates
```

When a Feishu attachment becomes part of a source bundle, the WXPost Skill
materializes or copies it into `/workspace/inbox/<article-session>/`, assigns
its stable source ID, and uploads accepted durable media through the scoped
SoarHigh asset endpoint. Container-local paths and Feishu download URLs are
never stored as durable article media URLs.

SoarHigh Storage is the durable media source after upload. Workspace cleanup
may remove temporary derivatives and already-uploaded local copies according
to a configurable retention policy; it must never delete the corresponding
SoarHigh asset.

## 9. Article types and Markdown authoring model

### 9.1 Semantic article types

| ID               | Label          | Typical use                                                                 |
| ---------------- | -------------- | --------------------------------------------------------------------------- |
| `meeting-recap`  | Meeting Recap  | Default post-meeting story and club recap                                   |
| `member-story`   | Member Story   | Character-led profile with turning points and quotes                        |
| `event-preview`  | Event Preview  | Value proposition, details, schedule, and registration                      |
| `meeting-review` | Meeting Review | Operational or editorial debrief with observations and feedback             |
| `action-guide`   | Action Guide   | Practical, stepwise guidance with actions and checklists                    |
| `custom`         | Custom         | An article whose editorial intent does not fit the standard starting points |

The article type is an editorial brief used by the Hermes Agent authoring Skill. It
may recommend a narrative approach, but it does not impose required blocks,
block counts, or a fixed sequence.

Selection precedence is:

1. an explicit user request;
2. Hermes Agent's inference from the requested outcome and sources;
3. `meeting-recap` for a normal post-meeting article;
4. `custom` when none of the standard briefs fits.

Hermes Agent asks the user only when ambiguity would materially change the article.
Changing article type after generation normally requires content revision in
Hermes Agent; it is not a local presentation control.

### 9.2 Markdown is the primary and only body source

Ordinary article writing stays as ordinary Markdown:

- section headings (`##` and below);
- paragraphs;
- emphasis;
- lists and task lists;
- blockquotes;
- links;
- thematic breaks;
- ordinary images when no richer media behavior is needed.

Opening, prose sections, transitions, and closing paragraphs are writing, not
JSON components. Their order and length remain free.

Example:

```md
The meeting did not begin with a speech. It began with a question.

## One Question Changed the Room

For several seconds, nobody answered. Then one member raised her hand...
```

`bodyMarkdown` is the canonical body. There is no parallel `modules[]` array
that can drift from or duplicate it.

`ArticleDocument.title` is the only article title. `bodyMarkdown` begins with
prose or an H2 section heading; an H1 is rejected with a structured validation
error so browser and WeChat renderers never produce duplicate titles.

### 9.3 Directives are limited escape hatches for rich blocks

Only elements that standard Markdown cannot express reliably use a constrained
directive. The initial vocabulary is:

- `gallery`;
- `video`;
- `takeaway` or another strongly styled callout;
- `person` for a profile card;
- `info-grid`;
- `timeline`;
- `pull-quote` when a normal blockquote is insufficient;
- semantic key-point emphasis as a small inline extension.

Example:

```md
## Three Moments from the Evening

The photographs show something the agenda could not: people leaning forward,
waiting for the speaker to continue.

:::gallery
items:

- M01
- M02
- M03
  caption: Three moments from the evening
  :::

## What Changed the Second Time

After receiving feedback, she tried again.

:::takeaway
text: |
Feedback becomes useful when it gives someone a visible next move.
:::
```

The backend directive parser converts registered directives into the versioned
`WxPostRenderDocument` body-node contract. Browser and WeChat renderers consume
that backend-owned contract; neither target reparses directive YAML. Unknown
directives, malformed payloads, invalid media kinds, and missing media
references are rejected with structured validation errors.

The implementation plan must finalize and version the exact directive grammar.
It must remain readable in raw Markdown and must not allow arbitrary scripts,
styles, event handlers, or unregistered HTML.

#### Directive grammar version 1

Every block directive uses one uniform, line-oriented form:

```md
:::directive-name
field: YAML value
anotherField:

- item
  :::
```

- the opening fence is an unindented `:::directive-name` line;
- the closing fence is an unindented `:::` line;
- the content between them must be a non-empty YAML mapping;
- directives cannot nest;
- each directive accepts only its registered fields;
- raw HTML is not allowed in Markdown or directive text.

The version 1 payloads are:

| Directive    | Required fields                           | Optional fields                     | Media constraint                                    |
| ------------ | ----------------------------------------- | ----------------------------------- | --------------------------------------------------- |
| `gallery`    | `items: string[]`                         | `caption`                           | every item references an included image             |
| `video`      | `media: string`                           | `caption`                           | references an included video                        |
| `takeaway`   | `text`                                    | `title`                             | none                                                |
| `person`     | `name`                                    | `role`, `media`, `summary`, `quote` | `media`, when present, references an included image |
| `info-grid`  | `items: { label, value }[]`               | `title`                             | none                                                |
| `timeline`   | `items: { label, title, description? }[]` | `title`                             | none                                                |
| `pull-quote` | `text`                                    | `attribution`                       | none                                                |

Semantic key-point emphasis uses `==important phrase==`. It is an inline
annotation for the renderer, not a requirement: ordinary Markdown with no
key points or block directives remains valid.

### 9.4 Article type does not constrain composition

The Hermes Agent Skill may recommend:

```text
Meeting Recap
  memorable moments → reflection → useful next move

Member Story
  person → change over time → attributable quote or observed turning point

Event Preview
  value → practical details → schedule → next action
```

These are editorial recipes, not server validation rules:

- a Meeting Recap may be written as a character-led story;
- a Member Story does not require a quote when none is attributable;
- a Gallery appears only when suitable images exist;
- a Video directive appears only when an included video exists;
- a Timeline may appear in any article when chronology helps;
- no article must contain a takeaway, gallery, video, or special closing;
- directives have no required count or order.

The server validates syntax, references, registered capabilities, and safety.
It does not validate taste by requiring a template-shaped sequence.

### 9.5 Skill guidance versus code enforcement

Hermes Agent uses a versioned WXPost authoring Skill for soft editorial behavior:

- selecting an article type;
- choosing a useful narrative shape;
- deciding whether available sources justify a rich directive;
- writing the English Markdown;
- preserving source attribution;
- calling the create/update tool;
- repairing structured validation failures.

SoarHigh code owns hard constraints:

- `ArticleDocument` schema;
- registered article-type identifiers;
- directive parser and directive registry;
- media-reference validation;
- presentation options;
- sanitization;
- rendering and WeChat compatibility.

Hermes Agent submits the article through a schema-constrained Tool. SoarHigh
validates it again. A validation failure returns paths and error codes that the
Skill may repair in a bounded retry; Hermes Agent may not bypass the error by
submitting arbitrary final HTML.

## 10. Presentation system

### 10.1 Layouts

| ID                  | Label             | Intent                                                |
| ------------------- | ----------------- | ----------------------------------------------------- |
| `brand-default`     | Brand Default     | Restrained and dependable for most club articles      |
| `field-notes`       | Field Notes       | Emphasizes chronology, moments, and being in the room |
| `editorial-feature` | Editorial Feature | Stronger hierarchy and magazine-like reading rhythm   |

### 10.2 Color palettes

| ID                | Label           | Intent                                                |
| ----------------- | --------------- | ----------------------------------------------------- |
| `brand-blue`      | Brand Blue      | Blue-purple accents matching the SoarHigh frontend    |
| `paper-neutral`   | Paper Neutral   | Charcoal, stone, and warm paper for long-form reading |
| `warm-terracotta` | Warm Terracotta | Warm, people-centered, inviting stories               |

### 10.3 Appearance

- `light`
- `dark`

### 10.4 English typefaces

| ID                | Label           | Fallback strategy                                      |
| ----------------- | --------------- | ------------------------------------------------------ |
| `modern-sans`     | Modern Sans     | Avenir Next, Segoe UI, Roboto, Helvetica, sans-serif   |
| `editorial-serif` | Editorial Serif | Baskerville, Iowan Old Style, Palatino, Georgia, serif |
| `humanist-mix`    | Humanist Mix    | Expressive serif headings with a clean sans-serif body |

Fonts must use device-safe fallback stacks. The WeChat exporter must not depend
on a remote webfont loading successfully inside the WeChat article.

### 10.5 Defaults

The initial default is:

```json
{
  "layout": "brand-default",
  "palette": "paper-neutral",
  "appearance": "light",
  "typeface": "editorial-serif"
}
```

The default preview size is `mobile-390`. Preview size is a viewer setting and
is not stored as part of the article's canonical presentation.

### 10.6 Selection precedence

When Hermes Agent first creates a WXPost:

1. use an explicit presentation request from the Feishu conversation;
2. otherwise use an article-type recommendation if configured;
3. otherwise use the global defaults above.

Presentation selection must never be a mandatory pre-generation questionnaire.
A user can simply ask for an article and accept the defaults.

## 11. Public WXPost information architecture

### 11.1 Route

The Next.js route is:

```text
frontend/src/app/posts/wxposts/[slug]/page.tsx
```

The resulting public URL is:

```text
/posts/wxposts/{slug}
```

It is not placed under the `(auth)` route group.

### 11.2 Slug rules

- Generate from the initial English title.
- Lowercase and kebab-case.
- Remove unsupported punctuation.
- Add a short uniqueness suffix only when a collision occurs.
- Freeze the slug after first creation, even if the title changes.
- Treat the slug as a locator, not an authorization token.

### 11.3 Posts index

The existing `/posts` page gains:

```text
All | Posts | WXPost
```

Each WXPost card displays a `WXPost` badge and uses its summary/excerpt and
cover image when available. Ordinary Post rendering and visibility rules
remain unchanged.

The backend normalizes rows from the independent `posts` and `wxposts` tables
into one list contract:

```ts
type ContentListItem = {
  kind: "post" | "wxpost";
  id: string;
  title: string;
  slug: string;
  excerpt: string | null;
  author: Author; // member for Post; configured Official Account for WXPost
  createdAt: string;
};
```

`All` merges both sources before applying the final ordering and pagination;
`Posts` and `WXPost` query only their corresponding source. A future SQL view
or RPC may optimize the union without making WXPost a subtype of `posts`.
The WXPost author is synthesized from the configured Official Account; it is
not loaded from an `wxposts.author_id` column or a member relationship.

No WXPost or WeChat Preview item is added to the Operations menu.

### 11.4 Public page structure

```text
Header / Posts navigation
WXPost label + article metadata
Presentation controls
Article stage
  └── WxPostRenderer
Member-only draft action area
Footer
```

The page is article-first. It reuses the visual comparison design system but
does not show several articles or variants side by side.

## 12. Public presentation controls

### 12.1 Available to everyone

Every visitor may change:

- layout;
- color palette;
- light/dark appearance;
- typeface;
- preview size (`Desktop 760px` or `Mobile 390px`).

These controls affect only the current browser preview.

### 12.2 Local-state behavior

- Initial state comes from the WXPost's stored default presentation.
- Changes live in client state.
- `sessionStorage` may retain changes for the current tab/session, keyed by
  WXPost ID or slug.
- Local changes do not call a write API.
- Local changes do not alter what another visitor sees.
- `Reset to Article Style` restores the stored default presentation.
- MVP does not encode local selections in the public URL.

### 12.3 Anonymous visitor

An anonymous visitor:

- can read the complete WXPost;
- can use every presentation control;
- can use the mobile/desktop preview switch;
- cannot modify article content;
- cannot persist a new default style;
- cannot save or update a WeChat draft.

The page may show a restrained message:

```text
Sign in as a member to save this article to WeChat Drafts.
```

### 12.4 Authenticated member

An authenticated member has the same local presentation controls plus:

```text
Save to WeChat Drafts
```

or, when an existing WeChat draft is behind the current WXPost revision:

```text
Update WeChat Draft
```

Changing presentation controls alone is still local. Server state changes only
after the member explicitly confirms the draft action.

## 13. Article document contract

Hermes Agent sends content and structured metadata. It does not send trusted,
arbitrary final HTML.

```ts
type ArticleDocument = {
  schemaVersion: 1;
  title: string;
  slug?: string;
  excerpt?: string;
  byline?: string;
  articleType:
    | "meeting-recap"
    | "member-story"
    | "event-preview"
    | "meeting-review"
    | "action-guide"
    | "custom";
  customArticleType?: string; // required when articleType is custom
  sourceMeetingId?: string; // opaque association ID; never display directly
  bodyMarkdown: string;
  media: MediaAsset[];
  coverMediaId?: string;
  presentation: Presentation;
};

type WxPostRenderDocument = Omit<ArticleDocument, "bodyMarkdown"> & {
  renderVersion: 1;
  body: Array<MarkdownBodyNode | DirectiveBodyNode>;
};

type MarkdownBodyNode = {
  kind: "markdown";
  source: string; // already safety-validated standard Markdown
  line: number;
};

type DirectiveBodyNode = {
  kind: "directive";
  name:
    | "gallery"
    | "video"
    | "takeaway"
    | "person"
    | "info-grid"
    | "timeline"
    | "pull-quote";
  payload: object; // normalized against the registered payload schema
  line: number;
};

type Presentation = {
  layout: "brand-default" | "field-notes" | "editorial-feature";
  palette: "brand-blue" | "paper-neutral" | "warm-terracotta";
  appearance: "light" | "dark";
  typeface: "modern-sans" | "editorial-serif" | "humanist-mix";
};

type MediaAsset = {
  id: string; // M01, M02, ...
  kind: "image" | "video";
  sourceUrl: string;
  posterUrl?: string;
  description: string;
  credit?: string;
  people?: string[];
  include: boolean;
  order: number;
  descriptionSource: "user" | "ai";
  descriptionStatus: "confirmed" | "needs_confirmation";
};
```

### 13.1 Markdown and directive role

`bodyMarkdown` is the authoritative body and remains readable outside
SoarHigh. It contains ordinary prose plus only the constrained directives
defined in Section 9.3.

On ingestion, SoarHigh:

1. parses Markdown and directives into `WxPostRenderDocument v1`;
2. validates directive attributes and media references;
3. rejects unsafe or unregistered constructs;
4. stores the unchanged canonical Markdown;
5. gives the same ordered render body to browser and WeChat targets.

The render document is derived data and may be cached, but it is not a second
editable representation. Only the backend constructs it; create/update APIs do
not accept a caller-authored component tree, `modules[]`, arbitrary scripts,
arbitrary styles, or model-authored final HTML.

### 13.2 Source bundle ownership

The full transcript, raw conversation, and generation memory remain in
Hermes Agent. SoarHigh stores only the information required to:

- render the article;
- preserve its media;
- associate it with a meeting;
- revise the WXPost deterministically;
- save/update a WeChat draft.

This prevents SoarHigh from becoming an accidental second memory layer.

## 14. Persistence model

### 14.1 Independent WXPost resource

Do not add `post_type` to `posts` and do not create a one-to-one details table.
WXPost has a different writer, permission model, media manifest, revision
lifecycle, and future WeChat state, so it is persisted independently:

```sql
CREATE TABLE public.wxposts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT NOT NULL CHECK (title ~ '[^[:space:]]'),
  slug TEXT NOT NULL UNIQUE CHECK (slug ~ '[^[:space:]]'),
  content TEXT NOT NULL CHECK (content ~ '[^[:space:]]'),
  is_public BOOLEAN NOT NULL DEFAULT TRUE,
  schema_version INTEGER NOT NULL DEFAULT 1
    CHECK (schema_version = 1),
  article_type TEXT NOT NULL
    CHECK (
      article_type IN (
        'meeting-recap',
        'member-story',
        'event-preview',
        'meeting-review',
        'action-guide',
        'custom'
      )
    ),
  custom_article_type TEXT NULL,
  source_meeting_id UUID NULL REFERENCES meetings(id) ON DELETE SET NULL,
  excerpt TEXT NULL,
  byline TEXT NULL,
  media_manifest JSONB NOT NULL DEFAULT '[]'::jsonb
    CHECK (jsonb_typeof(media_manifest) = 'array'),
  cover_media_id TEXT NULL,
  default_presentation JSONB NOT NULL
    CHECK (jsonb_typeof(default_presentation) = 'object'),
  article_revision INTEGER NOT NULL DEFAULT 1
    CHECK (article_revision >= 1),
  render_version INTEGER NOT NULL DEFAULT 1
    CHECK (render_version = 1),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT wxposts_custom_article_type_check CHECK (
    (
      article_type = 'custom'
      AND COALESCE(custom_article_type ~ '[^[:space:]]', FALSE)
    )
    OR (
      article_type <> 'custom'
      AND custom_article_type IS NULL
    )
  )
);
```

Add indexes for the public creation-time listing and optional meeting lookup.
The migration uses the existing unique 14-digit timestamp convention under
`backend/supabase/migrations/`.

### 14.2 Data ownership and revision safety

`wxposts.content` is the only stored, editable Markdown body. The backend
derives `WxPostRenderDocument` from that content plus the row metadata; it does
not store a second editable body or caller-authored render tree.

Creation is a single validated insert. Update is a single conditional statement
that changes the row only when `article_revision = expected_revision`, then
increments the revision. A zero-row update becomes `409 Conflict`. The slug is
excluded from content updates after creation, keeping the public URL stable.

The `posts` table, its Pydantic `Post` model, CRUD helpers, routes, and existing
RLS policies remain unchanged.

Enable RLS on `wxposts`. Anonymous and authenticated readers may select only
rows where `is_public = true`. Do not add direct browser insert, update, or
delete policies: the backend writes with its service role after enforcing the
scoped Hermes credential. Hermes never receives Supabase credentials.

### 14.3 Publisher identity and optional byline

`wxposts` has no member owner or author foreign key. SoarHigh membership
controls who may perform protected operations, but it does not define the
article author. The WeChat publisher/author identity comes from the configured
Official Account and its draft adapter.

The optional `wxposts.byline` is article content, such as "SoarHigh Editorial
Team". It is not an account identity or an ownership field.

### 14.4 Deferred WeChat draft persistence and audit

Phase 1 does not add WeChat draft columns. Phase 3 adds nullable
`wechat_draft_media_id`, `wechat_draft_revision`, `wechat_draft_saved_at`, and
`wechat_draft_saved_by` columns in a separate migration when the provider
adapter exists.

That phase also records each attempted draft write in an append-only
`wxpost_draft_events` table or equivalent structured audit log:

```text
wxpost_id
member_id
action: add | update
article_revision
presentation
idempotency_key_hash
result: success | failure
wechat_media_id
error_code
created_at
```

Do not log AppSecret, access tokens, raw Authorization headers, or complete
third-party responses containing credentials.

## 15. API contract

The paths below are backend resource paths. Deployment may place them under the
configured API base URL.

### 15.1 Fetch article context

```http
GET /meetings/{meeting_id}/article-context
```

Auth policy should match the sensitivity of the included meeting. Published
meeting context may be public; draft/private meeting context requires a scoped
service or member credential.

### 15.2 Discover authoring capabilities

```http
GET /posts/wxposts/capabilities
```

Response:

```json
{
  "schemaVersion": 1,
  "renderVersion": 1,
  "documentSchema": {
    "...": "the complete ArticleDocument JSON Schema"
  },
  "renderDocumentSchema": {
    "...": "the complete WxPostRenderDocument JSON Schema"
  },
  "articleTypes": [
    "meeting-recap",
    "member-story",
    "event-preview",
    "meeting-review",
    "action-guide",
    "custom"
  ],
  "directives": [
    "gallery",
    "video",
    "takeaway",
    "person",
    "info-grid",
    "timeline",
    "pull-quote"
  ],
  "inlineExtensions": ["key-point"],
  "presentation": {
    "layouts": ["brand-default", "field-notes", "editorial-feature"],
    "palettes": ["brand-blue", "paper-neutral", "warm-terracotta"],
    "appearances": ["light", "dark"],
    "typefaces": ["modern-sans", "editorial-serif", "humanist-mix"]
  },
  "defaultPresentation": {
    "layout": "brand-default",
    "palette": "paper-neutral",
    "appearance": "light",
    "typeface": "editorial-serif"
  }
}
```

SoarHigh is the protocol authority. The Hermes Agent Skill may contain editorial
guidance and examples, but it must not become an independently drifting copy of
the renderer capability registry. The schema version is included in every
create/update request. The live response also includes the exact payload schema
and example for every directive, in addition to the compact directive list
shown above.

### 15.3 Validate an ArticleDocument without storing it

```http
POST /posts/wxposts/validate
```

The request body is the raw `ArticleDocument`. The endpoint validates the
versioned document contract, parses Markdown and directives, validates media
references and safety, and returns no persistence side effect.

A successful response summarizes the detected directive order, source line,
referenced media IDs, and inline key-point count, and includes the
backend-generated `renderDocument`. A `422` response contains a stable error
code, machine-readable path, source line when applicable, and directive name so
Hermes Agent can repair the document and retry.

### 15.4 Create a WXPost

```http
POST /posts/wxposts
Authorization: Bearer <hermes-service-token>
Content-Type: application/json
```

Request:

```json
{
  "document": {
    "schemaVersion": 1,
    "title": "What We Learned by Speaking Again",
    "articleType": "meeting-recap",
    "sourceMeetingId": "uuid",
    "bodyMarkdown": "The meeting began...\\n\\n## What Changed",
    "media": [],
    "presentation": {
      "layout": "brand-default",
      "palette": "paper-neutral",
      "appearance": "light",
      "typeface": "editorial-serif"
    }
  }
}
```

Response:

```json
{
  "id": "uuid",
  "slug": "what-we-learned-by-speaking-again",
  "article_revision": 1,
  "preview_url": "https://<domain>/posts/wxposts/what-we-learned-by-speaking-again"
}
```

Creation is atomic. The public record is not exposed before the complete
ArticleDocument and its required media references validate.

### 15.5 Update content

```http
PATCH /posts/wxposts/{wxpost_id}
Authorization: Bearer <hermes-service-token>
Content-Type: application/json
```

Request:

```json
{
  "expected_revision": 4,
  "document": {}
}
```

The stable slug is not regenerated. On success, the article revision
increments. A stale `expected_revision` returns `409 Conflict` rather than
silently overwriting a newer revision.

Hermes Agent content updates must preserve the current server-side default
presentation unless the update explicitly includes a presentation change.
This prevents a later text revision from erasing a presentation chosen during
the WeChat draft review.

### 15.6 Read a public WXPost

```http
GET /posts/wxposts/{slug}
```

No authentication is required for a ready public WXPost.

### 15.7 Save or update the WeChat draft

```http
POST /posts/wxposts/{wxpost_id}/wechat-draft
Authorization: Bearer <soarhigh-member-token>
Content-Type: application/json
```

Request:

```json
{
  "expected_revision": 4,
  "presentation": {
    "layout": "field-notes",
    "palette": "brand-blue",
    "appearance": "light",
    "typeface": "humanist-mix"
  },
  "confirmation": true,
  "idempotency_key": "client-generated-opaque-value"
}
```

This endpoint:

1. accepts only an authenticated SoarHigh member credential;
2. rejects the Hermes Agent service credential;
3. checks `expected_revision`;
4. validates title, byline, summary, cover, media, Markdown directives, and
   target compatibility;
5. creates or reuses a pending operation keyed by `idempotency_key`;
6. renders the final WeChat HTML with the submitted presentation;
7. uploads or normalizes required WeChat media;
8. adds a draft when no draft media ID exists, or updates the existing draft
   when a draft media ID exists;
9. after a successful provider write, transactionally persists the selected
   presentation as the new article default and updates the article/draft
   revisions;
10. finalizes the operation record with the member, revision, selected
    presentation, provider result, and timestamp.

The endpoint returns a safe application-level result, not WeChat credentials:

```json
{
  "status": "saved",
  "action": "update",
  "article_revision": 5,
  "wechat_draft_revision": 5,
  "saved_at": "2026-07-25T12:00:00Z"
}
```

### 15.8 Asset ingestion

Hermes Agent may reference already-stable media URLs or upload assets through a
scoped SoarHigh asset endpoint. Asset upload permission does not imply WeChat
draft permission.

For Feishu uploads, Hermes sends file bytes from `/workspace`, not a
container-local path or temporary Feishu download URL. A successful ingestion
response returns the stable asset identifier and URL that may be referenced by
`ArticleDocument`.

Every stored asset must have:

- stable source URL;
- MIME type and size;
- media kind;
- description;
- ownership/source metadata sufficient for debugging;
- optional poster for video;
- upload/validation status.

## 16. Authentication and authorization

| Operation                          | Anonymous |           Hermes Agent service |           Logged-in member |
| ---------------------------------- | --------: | -----------------------------: | -------------------------: |
| List public WXPosts                |       Yes |                            Yes |                        Yes |
| Read public WXPost                 |       Yes |                            Yes |                        Yes |
| Change local presentation          |       Yes |                            Yes |                        Yes |
| Create/update WXPost content       |        No |                    Yes, scoped | No through the public page |
| Persist style without draft action | No in MVP | Only when explicit in document |                  No in MVP |
| Save/update WeChat draft           |        No |                         **No** |                        Yes |
| Read WeChat credentials            |        No |                             No |                         No |

The WeChat AppID/AppSecret and access-token cache remain backend-only secrets.
The browser and Hermes Agent receive neither.

Phase 1 uses three backend environment values:

- `WXPOST_SERVICE_TOKEN`: scoped bearer token for Hermes create/update calls;
  an empty value disables ingestion with `503`;
- `WXPOST_PUBLIC_BASE_URL`: origin used to construct stable preview links
  (`http://localhost:3000` for a local env file, otherwise
  `https://soarhigh.top` by default);
- `WXPOST_PUBLISHER_NAME`: Official Account display name synthesized for the
  shared Posts index.

Of the SoarHigh credentials, the Hermes container receives only the scoped
service credential required for article context, asset ingestion, and WXPost
create/update calls. It does not receive Official Account draft credentials.
The Feishu Gateway uses an explicit sender allowlist during testing and
production rollout.

Authentication must be enforced in the draft endpoint even though the frontend
also hides or disables the action for anonymous visitors.

If club policy later requires a narrower publisher role, add a
`wechat_publish` permission without changing the public WXPost contract. MVP
uses the agreed member gate.

## 17. Rendering architecture

### 17.1 Productionizing the visual comparison

The gitignored visual-comparison artifact is a design and interaction
reference. Production must not iframe it or copy the entire static page into a
route.

The temporary `/posts/wxposts/renderer-preview` lab and
`WxPostRendererShowcase` were removed after the formal
`/posts/wxposts/[slug]` route reached renderer, presentation-control, fixture,
and browser-acceptance parity. Reusable `WxPostRenderer` components and fixture
documents remain as production and regression-test assets.

Reusable presentation controls stay under
`frontend/src/components/wxpost/`. `sourceMeetingId` is an opaque relationship
field; the public page resolves a separate context or folio label before
passing it to the renderer.

Extract or reimplement its proven concepts as typed frontend and renderer
components:

```text
WxPostRenderer
├── presentation tokens
│   ├── layouts
│   ├── palettes
│   ├── appearances
│   └── typefaces
├── backend-owned WxPostRenderDocument v1
├── standard Markdown renderers
│   ├── heading
│   ├── paragraph
│   ├── list
│   ├── blockquote
│   └── link/image
├── directive renderers
│   ├── takeaway
│   ├── gallery
│   ├── video
│   ├── person
│   ├── info-grid
│   ├── timeline
│   └── pull-quote
└── responsive rules
    ├── desktop
    └── mobile
```

The comparison page, WXPost browser renderer, and WeChat exporter should share
one token/directive definition wherever their runtime constraints allow. Avoid
three independently maintained style implementations.

### 17.2 Browser rendering

- English-first typography.
- Full article scroll, not a small local sample.
- Real responsive behavior.
- Desktop supports the layout's wider/asymmetric compositions.
- Mobile collapses multi-column content into a readable single column.
- Mobile galleries scroll horizontally with touch-friendly snapping.
- Browser video uses a poster, controls, duration/label, and caption.
- Key points may use the proven underline treatment without copying the exact
  reference colors.
- The renderer accepts only the backend-generated render document; raw
  `ArticleDocument` directive YAML is never parsed in the browser.

### 17.3 WeChat rendering

WeChat export is a separate adapter over the same `WxPostRenderDocument`:

1. validate the ArticleDocument and produce the render document;
2. resolve the selected presentation;
3. render standard Markdown nodes and registered directives;
4. convert styles to the constrained inline form required by the target;
5. upload/replace article-body image URLs as required;
6. resolve the cover media identifier;
7. validate length and required fields;
8. submit the draft payload.

The exporter must never pass through arbitrary scripts, stylesheets, iframes,
or model-generated event handlers.

### 17.4 Video compatibility

The browser WXPost supports a real video directive. WeChat compatibility must be
explicit:

- use a supported native/platform representation when the configured Official
  Account API and asset type allow it;
- otherwise render a poster, caption, duration, and a clearly labeled fallback
  rather than silently dropping the video;
- show a compatibility warning before draft save when the browser preview and
  WeChat output differ materially.

The exact native-video API path must be verified against the configured
Official Account before implementation is considered complete.

## 18. Revisions, idempotency, and state transitions

### 18.1 Revision rules

- First complete create: `article_revision = 1`.
- Each accepted Hermes Agent content update increments the article revision.
- Anonymous/local presentation changes do not increment it.
- A successful member draft action with presentation changes persists the new
  default and increments the article revision.
- `wechat_draft_revision` records the revision last saved to WeChat.

### 18.2 Button states

| State                                                                                   | Member action                                        |
| --------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| No WeChat draft media ID                                                                | `Save to WeChat Drafts`                              |
| Draft revision equals current revision and local presentation equals the stored default | `Saved to WeChat Drafts` (disabled or informational) |
| Current article revision is newer                                                       | `Update WeChat Draft`                                |
| Local presentation differs from the stored default                                      | `Update WeChat Draft`                                |
| Validation failure                                                                      | `Fix issues before saving`                           |
| Request in progress                                                                     | Spinner; disable duplicate submission                |

### 18.3 Stale page

If a member loaded revision 4 but Hermes Agent has already produced revision 5,
the draft endpoint returns `409 Conflict`. The UI reloads the current article
and asks the member to review again. It must not save stale content.

### 18.4 Duplicate submission

The client sends an idempotency key. Replaying the same confirmed request does
not create another WeChat draft. The server creates a pending operation before
the provider call and stores the completed result for the required idempotency
window.

If the provider succeeds but local finalization fails, the pending operation
retains enough non-secret provider result data to reconcile the state. A retry
with the same idempotency key resumes/finalizes that operation instead of
issuing another provider add request.

## 19. Validation and error behavior

### 19.1 Generation-time source validation

Before generation, Hermes Agent checks:

- meeting context resolved;
- transcript or explicit user decision to proceed without one;
- every included media item has a stable source;
- every included media item has a confirmed or explicitly accepted
  description;
- duplicate media is flagged;
- failed/unreachable URLs are reported;
- article type is known.

### 19.2 WXPost validation

Before exposing a newly created WXPost:

- title and Markdown are non-empty;
- `articleType` is supported and `customArticleType` is present for `custom`;
- every directive is registered and syntactically valid;
- presentation values are registered;
- referenced media IDs exist;
- cover reference resolves when provided;
- unsafe HTML is rejected or sanitized;
- schema version is supported.

### 19.3 WeChat draft validation

Before calling WeChat:

- authenticated member exists;
- expected revision is current;
- explicit confirmation is present;
- Official Account credentials and access token are available;
- title, configured WeChat author identity/byline, summary, and cover satisfy
  the adapter contract;
- all image/media transformations succeeded;
- the final HTML passes size and compatibility checks;
- draft add/update mode is unambiguous.

Failures before a successful provider write leave the WXPost unchanged except
for safe operation/audit information. A presentation does not become the new
default when the corresponding provider write fails. If the provider succeeds
but local finalization fails, the operation enters a recoverable state and is
reconciled through the same idempotency key; the backend must not issue a
second draft-add request.

## 20. Frontend behavior details

### 20.1 Loading

- Render a stable page shell while fetching.
- Fetch only the dedicated WXPost read API; never pass a WXPost through the
  ordinary Post renderer while loading.
- Initialize controls from `default_presentation`.
- Initialize preview size to Mobile 390px unless an in-session preference
  exists.

### 20.2 Presentation controls

- Accessible labels and keyboard interaction.
- Current choice summary.
- Immediate visual update without a network request.
- Reset action.
- Desktop keeps the complete presentation card above the preview.
- Mobile is preview-first: a compact, sticky current-style summary opens a
  bottom drawer containing the complete controls, `Reset`, and `Done`.
- Opening and closing the mobile drawer preserves the article scroll position.
- The drawer remains presentation-only. A future authenticated content editor
  uses a separate mode or route rather than adding content fields to this
  drawer.
- Changing article type is not offered.

### 20.3 Draft confirmation

The member sees a confirmation dialog containing:

- title;
- current revision;
- add versus update action;
- selected layout, palette, appearance, and typeface;
- cover;
- compatibility warnings;
- explicit confirmation button.

The dialog should make clear that the operation saves a draft and does not
publish or mass-send the article.

## 21. Backend and data migration impact

Expected implementation surfaces:

- Supabase migration for the independent `wxposts` table, constraints, indexes,
  and RLS policies without altering `posts`;
- Pydantic persistence/read models for WXPost plus the normalized
  `ContentListItem` list contract;
- versioned `ArticleDocument` validation and capabilities route;
- Markdown/directive parser, sanitized AST, and structured validation errors;
- database helpers for create/read/update/revision checks;
- meeting article-context service and route;
- scoped Hermes Agent service authentication;
- public WXPost read route;
- member-only WeChat draft route;
- media and WeChat rendering services;
- append-only audit logging;
- containerized Hermes Gateway deployment with distinct `/opt/data` and
  `/workspace` mounts;
- workspace lifecycle and Feishu-attachment materialization rules;
- frontend `ContentListItem` union and `WxPostIF` detail contract;
- `/posts` filtering and badges;
- `/posts/wxposts/[slug]` public page;
- reusable presentation controls and `WxPostRenderer`;
- draft confirmation and member mutation hook.

Ordinary Post CRUD and rendering must remain backwards compatible.

## 22. Delivery phases

### Phase 0 — Contracts and renderer extraction

- Finalize `ArticleDocument`, the Markdown directive grammar, and the parsed
  AST contract.
- Port the visual comparison's token and rich-block concepts into testable
  Markdown/directive renderers.
- Render representative Meeting Recap, Member Story, and Event Preview fixture
  ArticleDocuments through every layout in desktop and mobile modes.
- Define deterministic browser and WeChat render outputs.

**Exit criterion:** representative Meeting Recap, Member Story, and Event
Preview fixtures render through all three layouts at Mobile 390 and Desktop
760, while one complete fixture also covers every agreed presentation
combination.

### Phase 1 — Public WXPost vertical slice

- Add the independent `wxposts` migration and models without changing
  ordinary `posts`.
- Add create/update/read APIs without WeChat integration.
- Add `/posts/wxposts/[slug]`.
- After that route reaches presentation-control and renderer-test parity,
  delete the temporary `/posts/wxposts/renderer-preview` lab route and
  showcase shell while retaining reusable fixtures.
- Add Posts index `WXPost` filter and badge.
- Add public local presentation controls and reset behavior.
- Return a stable preview URL from create/update.

**Exit criterion:** a fixture or API-created WXPost is publicly readable,
locally restylable, and remains at the same URL across content revisions.

### Phase 2 — Hermes Agent and Feishu source flow

- Add the minimal `claws/hermes` Compose deployment, local environment example,
  lifecycle/shell/log wrapper, and operator documentation.
- Run the Hermes Gateway in the official container with the host Hermes home
  mounted at `/opt/data` and only the dedicated article workspace mounted at
  `/workspace`.
- Stop and disable the host Gateway before starting the containerized Gateway.
- Configure container-local terminal execution with `cwd: /workspace`; do not
  mount the host Docker socket or SoarHigh repository.
- Add meeting article-context endpoint.
- Define the versioned Hermes Agent WXPost authoring Skill.
- Define the schema-constrained Hermes Agent tool/API adapter for create/update.
- Load/check SoarHigh capabilities before emitting an ArticleDocument.
- Implement the one-thread-per-article protocol.
- Implement Feishu attachment materialization into the workspace, media IDs,
  descriptions, status summary, upload, and validation.
- Prove a real meeting recap created from meeting API data plus Feishu
  transcript/media.

**Exit criterion:** a user starts in Feishu, provides sources, receives a
public WXPost link, requests a revision, and sees the same link update; the
container cannot read any unmounted host project.

### Phase 3 — Authenticated WeChat draft integration

- Configure backend-only Official Account credentials and access-token cache.
- Implement media normalization and compatibility validation.
- Implement add/update draft behavior.
- Add member confirmation UI, stale-revision guard, idempotency, and audit.

**Exit criterion:** an anonymous visitor cannot invoke the endpoint; a logged-in
member can save once, update after a newer revision, and cannot accidentally
create duplicates by retrying the same request.

### Phase 4 — Polish and operational hardening

- Bitable escalation for unusually large collaborative source sets if real
  usage justifies it.
- Better publication audit/history UI.
- Shareable presentation query parameters only if reviewers request them.
- Compatibility diagnostics and richer media status.

## 23. Acceptance criteria

### Public discovery and preview

- [x] `/posts` can filter `All`, `Posts`, and `WXPost`.
- [x] WXPost cards are visibly labeled.
- [x] `/posts/wxposts/{slug}` loads without authentication.
- [x] The URL remains stable after a content revision.
- [x] Full articles scroll naturally on desktop and mobile.
- [x] Mobile galleries scroll horizontally.
- [x] Browser video renders with poster, controls, and description.

### Presentation

- [x] Every visitor can change layout, palette, appearance, typeface, and
      preview size.
- [x] These changes make no server write.
- [x] A second visitor is unaffected.
- [x] Reset restores the stored article presentation.
- [x] Article type/content structure cannot be changed from the presentation
      controls.
- [x] Defaults are Brand Default, Paper Neutral, Light, Editorial Serif, and
      Mobile 390px preview.
- [x] Mobile shows the article before its settings and exposes all presentation
      controls through a bottom drawer without losing the reading position.

### Hermes Agent workflow

- [ ] Meeting introduction and agenda are fetched from SoarHigh.
- [ ] The user can attach images, videos, transcript, and extra notes through
      Feishu.
- [ ] Every included media item has an ID and description status.
- [ ] The submitted body has one canonical `bodyMarkdown` source and no
      parallel `modules[]` tree.
- [ ] Article type guides generation but does not impose directive order or
      count.
- [ ] A valid long-form article with no directives is accepted.
- [ ] Hermes Agent checks the current schema/capabilities contract before
      create or update.
- [ ] Invalid directives return structured errors that the Skill can repair
      without falling back to arbitrary HTML.
- [ ] Hermes Agent returns the stable WXPost URL after generation.
- [ ] Later content edits update the same WXPost and increment its revision.
- [ ] Hermes Agent cannot invoke the WeChat draft endpoint.

### Hermes runtime and source handling

- [ ] The host Hermes Gateway is stopped while the containerized Gateway runs.
- [ ] Container `HERMES_HOME` and `HOME` resolve to `/opt/data`.
- [ ] The existing host Hermes home is available at `/opt/data` without a
      second nested `.hermes` directory.
- [ ] Hermes commands and file operations start in `/workspace`.
- [ ] The container has no mount for the SoarHigh repository, complete host
      home directory, host SSH credentials, or host Docker socket.
- [ ] A Feishu image, video, and transcript can each be materialized in the
      workspace and uploaded to the scoped SoarHigh asset endpoint.
- [ ] The resulting `ArticleDocument` references stable SoarHigh assets, never
      container paths or temporary Feishu URLs.
- [ ] Restarting or recreating the Hermes container preserves `/opt/data` and
      the host-mounted workspace.
- [ ] `hermes.sh down` removes no volumes or host data, and `hermes.sh restart`
      retains Docker's normal restart semantics.
- [ ] Files created under both mounts remain owned by or writable to the
      intended host user.
- [ ] Workspace cleanup cannot delete durable SoarHigh assets.

### Authentication and draft saving

- [ ] Anonymous requests to the draft endpoint return an authentication error.
- [ ] Hermes Agent service credentials are rejected by the draft endpoint.
- [ ] A logged-in member sees Save/Update Draft controls.
- [ ] The current local presentation is shown in the confirmation dialog.
- [ ] Successful draft save persists that presentation as the new article
      default.
- [ ] A newer Hermes Agent revision changes the action to Update Draft.
- [ ] Stale expected revisions return `409`.
- [ ] Repeated idempotent requests do not create duplicate drafts.
- [ ] WeChat secrets never reach the browser or Hermes Agent.

### Regression

- [x] Ordinary Post routes and Markdown rendering remain unchanged.
- [x] Existing public/private Post visibility continues to work.
- [x] No WXPost item is added to the Operations menu.

## 24. Test strategy

### Backend

- Model validation for every article type and presentation value.
- Directive parser tests for every registered directive, malformed payload,
  unknown directive, invalid media kind, and missing media reference.
- Slug generation, collision, and stability tests.
- Public versus private read tests.
- Service-scope create/update tests.
- Explicit tests proving the service token cannot call the draft endpoint.
- Member authentication and anonymous rejection tests.
- Optimistic-concurrency and stale-revision tests.
- Idempotency tests.
- Add-versus-update WeChat adapter tests with mocked provider calls.
- Media failure and partial-operation rollback tests.
- Ordinary Post regression tests.

### Hermes runtime

- Inspect the running container and assert `HERMES_HOME=/opt/data`,
  `HOME=/opt/data`, and terminal working directory `/workspace`.
- Verify the host Hermes Gateway is not running concurrently.
- Verify expected read/write behavior in `/opt/data` and `/workspace`.
- Assert representative unmounted host paths and the SoarHigh repository are
  not visible from inside the container.
- Exercise Feishu attachment receipt, workspace materialization, SoarHigh
  upload, stable asset replacement, and local cleanup end to end.
- Recreate the container and verify configuration, memory, sessions, source
  workspace, and already-uploaded WXPost media survive as designed.

### Frontend

- Component tests for presentation controls and reset.
- Assert anonymous changes never call mutation APIs.
- Assert anonymous users do not receive an enabled draft action.
- Assert authenticated members receive the correct Save/Saved/Update state.
- Renderer fixtures for every layout/palette/appearance/typeface combination.
- Computed-style assertions proving palette, appearance, typeface, and layout
  rules actually apply rather than checking control attributes alone.
- Markdown/directive rendering tests, especially key-point underline, gallery,
  video, timeline, and long-form prose without directives.

### Browser acceptance

- Desktop 760px and Mobile 390px visual checks.
- Actual responsive narrow viewport, not only CSS class simulation.
- Horizontal touch/trackpad gallery behavior.
- Long-form scrolling with a complete article.
- Anonymous public access in a clean browser session.
- Authenticated save confirmation and error recovery.
- Visual comparison against the agreed prototype for hierarchy and rhythm,
  without requiring pixel-identical colors or spacing.

### Provider acceptance

- Real Official Account credential and IP/access configuration smoke test.
- Upload representative images.
- Save a new draft.
- Revise the WXPost and update the same draft.
- Inspect the resulting draft in the WeChat backend on mobile and desktop.
- Verify video fallback/native handling before declaring video export complete.

## 25. Risks and mitigations

| Risk                                                                    | Mitigation                                                                                                               |
| ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Hermes Agent and SoarHigh both become editors                           | Content writes only through the scoped Hermes Agent API; WXPost page has presentation controls but no content editor.    |
| Local style experiments accidentally mutate public state                | No presentation write API is called until an authenticated member confirms a draft action.                               |
| A later Hermes Agent revision overwrites a member-selected presentation | Content update preserves server presentation unless explicitly supplied.                                                 |
| Anonymous or service-token draft writes                                 | Dedicated member-only dependency and explicit rejection tests.                                                           |
| Duplicate WeChat drafts                                                 | Existing draft media ID, idempotency key, and add/update state machine.                                                  |
| Stale article saved after a concurrent revision                         | Required `expected_revision` with `409` on mismatch.                                                                     |
| Browser and WeChat output drift                                         | Shared Markdown AST, directive registry, and presentation tokens plus target-specific renderer tests.                    |
| Article output becomes a rigid component tree                           | Markdown remains the only body source; article-type recipes are advisory and no directive order/count is enforced.       |
| Remote fonts fail in WeChat                                             | Device-safe fallback stacks; no load-bearing webfont dependency.                                                         |
| Video renders in browser but not in WeChat                              | Compatibility check and explicit poster/fallback behavior; never silently omit.                                          |
| AI invents a media description                                          | Preserve description provenance and require confirmation/acceptance.                                                     |
| Large collaborative media sets overwhelm chat                           | Add Bitable escalation later based on usage; keep common flow conversational.                                            |
| Host and container Gateways consume the same Feishu connection          | Stop and disable the host Gateway before starting the container; verify only one process in operations checks.           |
| Hermes modifies unrelated host files                                    | Mount only the dedicated Hermes home and article workspace; do not mount the host home, SoarHigh repo, or Docker socket. |
| Container recreation loses Hermes state                                 | Persist the host Hermes home at `/opt/data` and back it up before migration or image upgrades.                           |
| Mounted files become root-owned                                         | Pass the host `HERMES_UID` and `HERMES_GID` to the official image and verify mount ownership.                            |
| Feishu attachment path is invisible or temporary                        | Materialize accepted sources under `/workspace/inbox` and upload durable media to SoarHigh before article submission.    |
| Workspace grows without bound                                           | Apply a configurable retention policy to temporary and already-uploaded local files without deleting SoarHigh assets.    |
| Existing Posts regress                                                  | Independent `wxposts` persistence, normalized list items, and ordinary Post regression coverage.                         |

## 26. Implementation-planning prerequisites

Before writing the implementation plan:

1. confirm the target Official Account has the required draft and media API
   permissions and deployment-network access;
2. confirm the Hermes Agent service authentication mechanism with SoarHigh;
3. finalize and version the Markdown directive grammar and parsed AST;
4. verify the WeChat video export path and lock the fallback behavior;
5. decide the exact renderer-version string and fixture set;
6. inspect the effective Supabase schema and write the migration against the
   current production migration history;
7. confirm Docker Desktop/Engine is available and choose the exact host
   `hermes-workspace` path in `claws/hermes/.env.local`;
8. back up the host Hermes home, stop the host Gateway, and verify the official
   container reads the mounted state at `/opt/data`;
9. define workspace retention, size limits, and cleanup behavior for Feishu
   source files and media-processing intermediates.
