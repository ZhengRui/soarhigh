# SoarHigh Toastmasters Club - Frontend Status

**Last updated:** 2026-08-06

**WxPost checkpoint:** `46d8d7e` is the committed Phase 2 baseline. The Phase 3
implementation described below completes WeChat Draft delivery. Slice 6
established one workspace-scoped Hermes session and formal
Skill generate and revise canonical Drafts through typed proposal schema v2,
while one pure TypeScript compiler renders the same backend-normalized input in
the browser and in an authenticated, stateless Next server route. Draft owns
Edit and Preview, in-place visual editing, explicit Save Draft, member-owned
presentation, and desktop/mobile canvas review. The controller applies the
agreed first-Draft presentation, preserves later member choices, derives
manifest-owned source fields, records generated captions as AI proposals, and
alone serializes canonical directives.
Representative Skill scenarios are retained as a manual review checklist;
they are not automated quality evaluations. Cross-runtime compiler tests, the
complete WxPost browser suite, and full Backend/controller suites cover the
deterministic behavior. Real Hermes generation succeeded for six linked
meeting/event workspaces plus one independent workspace, and signed-in Chrome
verified the complete rich-block and presentation matrix at desktop and 390 px.
Slice 7A adds explicit saved-Draft-to-public synchronization, one stable public
WxPost per workspace, revision/freshness status in Draft and Workspaces, and
atomic Supabase/OSS publication. Slice 7B adds explicit Hermes descriptions for
selected workspace images. Slice 7C completes the dedicated WxPost Assistant
runtime, observable persisted sessions, and deterministic fine-grained Draft
edits. Slice 7D completes conversational Feishu workspace/material authoring
with Feishu-only navigation and separate sessions. Phase 3 now publishes only
from an authenticated Public Revision to one confirmed, idempotent Official
Account draft; Hermes is not involved in that projection.

## Application Overview

This Next.js application serves as the web platform for the "SoarHigh Toastmasters Club," providing functionality for meeting management, growth tracking, awards recognition, posts, and voting. The application has both public-facing components and authenticated sections.

## Application Structure

### Public Routes

- **/** - Landing page with club introduction and information
- **/signin** - Authentication page with sign-in form
- **/meetings** - Public meeting listing page showing published meetings
- **/posts** - Public listing for ordinary Posts and WxPosts
- **/posts/[slug]** - Public post detail page for viewing specific content
- **/posts/wxposts/[slug]** - Public, read-only WxPost rendering and
  presentation controls
- **/meetings/workbook/[id]** - Public meeting agenda workbook preview page

### Protected Routes (under the (auth) group)

All routes in the (auth) group are protected by authentication middleware which redirects unauthenticated users to the homepage.

#### Meetings Management

- **/meetings/new** - Page for creating new meetings with two methods:
  - Template-based meeting creation
  - Image-based meeting creation (upload agenda image)
- **/meetings/edit/[id]** - Page for editing existing meetings
- **/meetings/workbook/[id]** - Page for viewing and downloading meeting agenda workbook (requires authentication for download)

#### Post Management

- **/posts/new** - Page for creating new posts
- **/posts/edit/[slug]** - Page for editing existing posts
- **/posts/wxposts/new** - Select a meeting/event or independent source and
  create a WxPost workspace
- **/posts/wxposts/edit/[workspaceKey]** - Resume an existing workspace
  directly in Materials
- **/posts/wxposts/workspaces** - List, paginate, resume, and delete shared
  workspaces

#### Operations

- **/growth** - Club growth metrics/management
- **/awards** - Management of club awards/recognition
- **/votes** - Management of meeting voting

## User Experience by Route

### Landing Page (/)

- Features the club name "SoarHigh Toastmasters Club" with a stylized header
- Contains introduction content about the club
- Accessible to all users (authenticated and unauthenticated)

### Sign In Page (/signin)

- Simple authentication form
- Redirects authenticated users appropriately

### Header Navigation

- Present across all pages
- Responsive design with mobile menu
- Dynamically changes based on authentication status
- Main navigation links: Introduction, Meetings, Posts
- Dropdown menu for Operations (Growth, Awards) for authenticated users
- Sign-out functionality

### Public Meetings Page (/meetings)

- Displays all meetings with different visibility rules:
  - For members: Shows both published and draft meetings with status indicators
  - For non-members: Shows only published meetings
- "Create Meeting" button displayed only for authenticated users
- Meeting cards show key meeting information including date, time, and theme
- Status indicators for draft/published meetings (visible to members)
- Link to edit draft meetings for authenticated users

### New Meeting Creation (/meetings/new)

- Three-tab interface for different creation methods:

  1. **Template-based creation**:

     - Three pre-defined templates (Regular Meeting, Workshop Meeting, Custom Meeting)
     - Visual cards with icons and descriptions
     - After selection, shows comprehensive meeting form

  2. **Image-based creation**:

     - Allows uploading of agenda images
     - Extracts meeting data from images using backend API

  3. **Text-based creation**:
     - Allows entering textual descriptions of meetings
     - Converts text descriptions into structured meeting data
     - Provides the same comprehensive meeting form for further editing

### Meeting Edit Page (/meetings/edit/[id])

- Loads existing meeting data from backend
- Reuses the meeting form component with populated data
- Save button to update changes
- Publish button to change meeting status from draft to published
- Full error handling and success notifications

### Posts Listing Page (/posts)

- Displays ordinary Posts and public WxPosts with All, Posts, and WxPost filters
- "New Post" and "Wx Workspaces" actions for authenticated users
- "New Post" opens a compact choice between Regular Post and WxPost
- Content cards show title, author, date, excerpt, and content type
- Visibility indicators for authenticated users
- Edit links for authenticated users

### Post Detail Page (/posts/[slug])

- Displays full post content with title and author information
- Edit button for authenticated users
- Access control based on post visibility

### WxPost Authoring

- Setup contains only the source choice and creates one workspace
- The source is immutable after creation; resumed workspaces open Materials
  directly instead of flashing Setup first
- Article type, descriptions, inclusion, transcript, notes, and writing brief
  are one browser-local Materials working copy
- "Save Materials" persists that working copy atomically, confirms any local
  AI image-description suggestions, and does not change the last saved Draft
- Import, upload, and delete remain immediate file operations
- Import, upload, and delete persist only their structural workspace changes;
  they do not save unrelated local Materials form edits
- Every material mutation carries the current manifest version; stale writes
  open a confirmation dialog before server state replaces local edits
- The Workspaces list is shared by all members, paginated, ordered by creation
  time, and displays each workspace's latest update time
- Linked workspace cards resolve compact meeting metadata in one batch and
  remain usable if meeting metadata is temporarily unavailable
- Generate Draft and Regenerate submit only the saved Materials state to one
  persisted, workspace-scoped Hermes web session
- The formal `soarhigh-wxpost-authoring` Skill reads and saves through the
  existing MCP controller; generated documents are normalized by Backend
  validation before they become canonical
- Independent Custom workspaces may omit `customArticleType`; Hermes infers the
  clearest form from the saved brief instead of requiring a synthetic label
- Generate Draft is available only after Materials form changes have been
  saved; immediate import, upload, and delete operations do not conflict with
  that rule
- Direct rendered-block edits stay local until Save Draft; a successful
  Generate, Regenerate, Save Draft, or actual Hermes revision increments
  `draftVersion`. General questions and questions about the current article
  return a normal Draft Assistant reply without creating a Draft version
- A successful Draft Assistant revision prepares the returned document while
  the current article remains visible, then updates the rendered Draft and
  version together without replacing the workbench with its initial loader
- Entering `/new` and confirming starts a separate Draft Assistant
  conversation without changing Materials or the saved Draft. Refreshing
  before its first message keeps the new conversation empty; the old persisted
  Hermes session is retired through durable cleanup
- Draft and Materials retain separate browser-local working copies while their
  tabs remain mounted; a structural Materials update does not discard an
  unsaved Draft edit
- A saved Draft keeps its own article type and material references. Excluding a
  material does not hide it from an older Draft, deleted files render as missing
  placeholders, and only Generate or Regenerate adopts current Materials.
  Focused revisions may explicitly add any imported workspace-ready image or
  video without changing its Materials inclusion, and preserve unrelated media
  and cover state by default
- The media library means the complete workspace catalog. Reports split it
  into unimported meeting/event candidates and imported `workspaceReady`
  media. Draft operations can use only imported media; candidates must first
  be imported in Materials
- The Draft workbench maps each visible member-authored field back to its
  canonical source: article title/excerpt/byline, individual Markdown blocks,
  section kickers and headings, every directive text field, and media
  descriptions used as captions. Generated labels and section numbers remain
  read-only
- Direct editing uses explicit source keys rather than rendered-text matching;
  only the selected text block receives editor focus and its single outline
- Draft media-description edits change only the Draft document snapshot and do
  not write back to the Materials working copy
- Markdown remains the canonical storage format but is not exposed in the
  member-facing editor; this is not a general rich-text formatting toolbar
- Draft is the third and final authoring stage. Its `Edit` and `Preview` modes
  render the same current working copy; there is no standalone Preview stage
- Edit keeps direct title/block editing, selected-text Hermes context, and the
  focused Hermes panel. Preview removes editor chrome and Hermes so the member
  can review the current working copy cleanly before saving it
- Layout, palette, appearance, typeface, and Desktop/Mobile controls remain
  available in both Draft modes
- Draft save, generation, and Hermes revisions use manifest and draft versions;
  each Hermes chat turn carries a unique optional-save operation ID so another
  tab's direct save cannot be mistaken for that turn's success. The controller
  accepts either no Draft change or exactly one matching increment. Stale saves
  keep local edits, and failed operations leave the saved Draft unchanged
- Missing workspace media renders a controlled in-article placeholder instead
  of a broken private URL
- Regenerate replaces the current canonical Draft and advances its version;
  retained version history and rollback are not part of Slice 6
- Feishu active-workspace selection and attachment ingestion are not part of
  the Draft workbench and remain Slice 7D. Selected-image descriptions are
  complete in Slice 7B
- Explicit public sync always reads the saved Draft again on Backend; unsaved
  Draft edits disable synchronization and are never published accidentally
- First sync creates public revision 1 behind a confirmation dialog. A later
  saved Draft becomes `update available`; explicit update keeps the stable slug
  and advances the public revision
- Public synchronization fingerprints the normalized saved Draft plus ordered
  referenced media content hashes. Ready public assets are reused, retries are
  idempotent, and a failed or conflicting update preserves the previous ready
  public revision
- Workspace deletion does not retract an already public WxPost or delete its
  public assets. A signed-in member can separately delete the public revision
  and its public media from the public preview page

#### Draft and presentation contract

- Draft is the single authoring and review workbench with `Edit` and `Preview`
  modes instead of a separate Preview workflow stage
- Layout, palette, appearance, typeface, and Desktop/Mobile controls are
  available in both modes through one shared presentation working copy
- Layout, palette, appearance, and typeface are part of the Draft document;
  changing one makes the Draft dirty and explicit `Save Draft` persists it
- Desktop/Mobile is browser view state only. It is never written to the Draft
  and does not make the Draft dirty
- Public delivery is an explicit `Sync Public WxPost` action inside Draft. It
  owns public revisions, OSS synchronization, and the stable public URL; a
  generic standalone Preview stage is not retained for that work

#### Content-template contract

- Article type is more than metadata or a one-line writing hint. Each supported
  type resolves to a flexible content recipe that defines likely starting
  modules, editorial goals, useful metadata, and conditional sections
- Recipes are not fixed outlines. Hermes may omit irrelevant modules, reorder
  them, or add a better section when the saved Materials support it
- `Meeting Recap` should normally establish a scene, use the meeting context and
  selected highlights, place media beside the events they support, and close
  with meaning or a next step; it must not degrade into a generic article based
  only on the string `meeting-recap`
- `Custom · Event Recap` remains the default for linked meeting numbers beginning
  with `10000`; the older visual study's `Event Preview` example does not
  override that product decision
- Content recipes belong in the formal WxPost Skill. The per-turn Generate
  prompt remains a small orchestration protocol, while `wxpost_get_context`
  supplies the saved Materials and the Skill interprets them
- For linked workspaces, the agent context loads theme, introduction, agenda,
  awards, date, time, and location live from Backend. This `meetingContext` is
  read-only generation input and is not duplicated in workspace JSON
- The formal Skill resolves all six preset Voice & tone IDs to their complete
  instructions. Selected custom profiles contribute their saved instructions
- Article content remains free-form Markdown. Recipes guide purpose and likely
  modules without limiting Hermes to a fixed set of headings or a rigid order

#### Canonical rendering and delivery contract

- `ArticleDocument` remains the canonical editable document: free-form
  `bodyMarkdown`, media metadata, and saved `presentation` settings
- Ordinary prose stays ordinary Markdown. Fenced YAML directives represent
  semantic structures that Markdown cannot express. `section` marks a major
  narrative section, `image` places one image without gallery chrome, and
  `gallery`, `video`, and `person` cover richer media structures. Directives
  identify content intent and media; they do not contain layout, color, font,
  or other theme styling. `==important phrase==` is the confirmed semantic
  key-point inline extension; its visual treatment is selected by the renderer
  theme
- the version 1 registry contains nine block directives: `section`, `image`,
  `gallery`, `video`, `person`, `takeaway`, `info-grid`, `timeline`, and
  `pull-quote`. It is an extensible, versioned registry rather than a permanent
  closed list; future directives may be added when they have a defined
  semantic purpose, payload schema, renderer behavior, Skill guidance, and
  tests
- Content recipes and Voice & tone belong to the Hermes Skill. They influence
  what the article says. The renderer owns how the saved document looks and
  must not infer article structure from particular headings or phrases
- The target is one canonical rendering pipeline:

  ```text
  ArticleDocument -- Backend validation --> WxPostRenderDocument
                                             + presentation
                                             + RenderContext
                                                   |
                                                   v
          shared pure TypeScript compiler
                 /                 \
        browser runtime       trusted Next runtime
        instant Draft UI      authoritative HTML
                                  |
                                  v
                         Backend publish / sync
  ```

- the compiler is one framework-independent TypeScript implementation built
  for two runtimes. Browser and trusted server execute the same source; this is
  not a React renderer plus a separate export renderer
- the browser imports it directly so title/block edits, directive changes, and
  presentation switches render immediately from local state without a render
  API request
- a stateless trusted Next server route imports the same compiler and returns
  authoritative HTML for a backend-normalized `WxPostRenderDocument`. Backend
  continues to own authentication, versions, material validation, persistence,
  public sync, and WeChat delivery
- browser-generated HTML is preview-only and is never accepted as publication
  authority. Backend passes validated render input to the trusted route and
  consumes its output; renderer failure changes no saved or public state
- the trusted route accepts backend service calls through the existing
  server-side WxPost service credential. It introduces no renderer-specific
  token, and no service credential is exposed to browser JavaScript. Backend
  resolves the route from the existing `WXPOST_PUBLIC_BASE_URL` and authenticates
  with the existing `WXPOST_SERVICE_TOKEN`; no renderer-specific environment
  variable or credential value is introduced. The Next server receives that
  existing token as server-only configuration
- local development therefore needs the existing `WXPOST_SERVICE_TOKEN` in
  `frontend/.env.local` as well as Backend; restart `bun dev` after adding it.
  This is the same credential value, not a new renderer token, and it remains
  unavailable to browser JavaScript
- Feishu temporary Draft links use the same compiler through
  `/posts/wxposts/draft-preview/[token]`. Backend owns the short-lived,
  version-bound token and media authorization; the route is read-only,
  unindexed, and refuses stale Draft versions instead of creating a public
  revision or falling forward to newer content
- Preview may retain editor-only node identifiers and signed preview URLs.
  Delivery may replace media URLs, remove editor-only attributes, sanitize the
  result, and validate platform limits. These are output post-processors, not
  separate renderers
- The compiler directly emits the constrained inline HTML that
  WeChat accepts. Tailwind remains appropriate for the surrounding authoring
  UI, but Tailwind classes, CSS variables, pseudo-elements, JavaScript, and
  browser-only responsive behavior cannot be publication dependencies
- Layout, palette, appearance, and typeface select deterministic layout
  templates and presentation tokens inside the one renderer. They must not
  change article meaning or require Hermes to rewrite the Draft
- Local Preview can be visually identical to the outgoing HTML, but only
  WeChat upload/readback and a WeChat mobile preview can verify platform
  filtering. The product must not claim exact WeChat fidelity before that
  boundary is tested
- the renderer also needs a small host-owned `RenderContext` for visual
  metadata that is not article prose: resolved asset URLs, context/folio label,
  display date, and publisher identity. The article body must not encode or
  infer these values from headings or prose. Missing context is omitted rather
  than invented. The paper display date is the first public-sync timestamp
  stored as the public WxPost record's `created_at`; it remains stable across
  later revisions. An unsynchronized Draft has no public date and omits it

## WxPost Future Phases and Slices

The original plan remains Phase 2 with seven implementation slices, followed by
the WeChat integration in Phase 3. Clarifying the canonical renderer does not
create two extra slices: it closes the presentation responsibility already
owned by Slice 6.

The implementation boundary is settled: one pure TypeScript compiler runs
locally in the browser and authoritatively in a trusted, stateless Next server
route. Backend owns Markdown/directive validation and produces the normalized
`WxPostRenderDocument` consumed by both runtimes. The trusted route reuses the
existing server-side WxPost service credential and introduces no new token.
`RenderContext` remains request-scoped. Asset URLs come from the validated
media mapping for the current target, context/folio copy comes from already
resolved workspace/public metadata, publisher identity comes from the
configured publisher fallback unless the document has a byline, and the paper
date follows the public-sync rule above.

### Phase 2 - Complete the shared authoring workflow

#### Slice 6 complete - Skill quality and canonical Draft presentation

Slice 6 now combines two completed tracks:

1. strengthen the Skill from concise baseline recipes into a detailed,
   testable editorial playbook while keeping the resulting article free-form;
2. replace the browser-only React/Tailwind article renderer with the shared
   pure TypeScript Markdown/directive-to-inline-HTML compiler and its trusted
   Next server execution path.

The Skill decides what makes a strong article and where evidence-backed media
supports it. The renderer decides how that document looks. Draft Preview reuses
the renderer's exact output, while visual editing uses stable editor-only node
IDs or an overlay instead of a second styled renderer.

Implemented order for this cut:

1. freeze the normalized render input/output and request-scoped
   `RenderContext` contracts;
2. implement the pure TypeScript compiler and cross-runtime fixtures;
3. add the stateless trusted Next route and backend client using the existing
   URL and service credential;
4. move Draft Edit/Preview to the shared compiler, reach the agreed visual and
   editing fidelity, then delete the superseded React/Tailwind article-renderer
   styling and obsolete tests;
5. make presentation controller-owned, expand the Skill recipes, and add
   manual Skill review scenarios without a compatibility layer or content
   heuristics;
6. run contract, compiler, UI, and real signed-in desktop/mobile browser smoke.

Acceptance:

- every article-type recipe defines its editorial purpose, source priorities,
  useful narrative shapes, optional modules, omission rules, and common failure
  modes without prescribing literal headings or a fixed section count
- Meeting Recap, Member Story, Meeting Review, Action Guide, Event Preview, and
  Custom/Event Recap have representative manual-review scenarios grounded in
  saved Materials and, when linked, live meeting context
- the Skill follows explicit precedence: factual sources and meeting context,
  user writing guidance, article-type purpose and writing approach, then
  selected Voice & tone; it never invents scenes, quotations, attendees,
  awards, or outcomes
- media placement follows meaning and descriptions rather than material ID
  order; included media uses only supported semantic directives and is not
  dumped into a generic end gallery
- Generate and Regenerate may choose a fresh evidence-supported narrative
  shape; focused revisions preserve unrelated content, and every operation
  preserves the member's saved presentation unless the member explicitly
  changes it
- presentation is controller/member-owned rather than a creative Skill choice:
  first generation receives the agreed default, later generations preserve the
  saved Draft presentation, and normal editorial revisions do not choose a new
  layout, palette, appearance, or typeface
- Hermes proposal schema v2 omits `presentation` and exposes typed ordered
  blocks instead of asking the model to hand-author fenced YAML; the controller
  applies the first default or preserves the saved/current presentation,
  serializes canonical ArticleDocument v1 directives, and the proposal
  contract, controller assembly, Skill, and tests agree
- the only bounded correction is one replacement save after a first attempt is
  rejected before persistence solely by formal proposal or ArticleDocument
  validation; version conflicts and runtime failures are not retried
- manual Skill review verifies that different evidence can produce different
  structures for the same article type; no hard-coded heading sequence or
  content-specific repair heuristic is introduced
- the version 1 syntax supports all nine registered block directives plus the
  key-point inline extension; capabilities, frontend types, fixtures, Skill
  guidance, renderer behavior, and tests agree
- a future directive is added only as a versioned registry extension with a
  semantic purpose and the same end-to-end contract coverage; unknown or
  arbitrary directives remain invalid
- the agreed default presentation is `brand-default`, `paper-neutral`, `light`,
  and `editorial-serif`
- local title/block/directive edits and presentation changes invoke the shared
  compiler in the browser without a render API request
- the trusted Next runtime produces byte-identical HTML for the same normalized
  input, and Backend never accepts browser-generated HTML as authoritative
- the trusted renderer route is stateless, does not read workspaces or hold
  publication credentials, and fails closed without changing saved state
- every successful Generate, Regenerate, direct Save Draft, or Hermes revision
  passes backend normalization and trusted-server compilation; failure
  preserves the previous saved Draft and the browser's local working copy
- the old React/Tailwind article renderer is not retained as a second
  implementation after parity; the surrounding application UI may continue to
  use Tailwind
- every supported Markdown node and every retained directive has deterministic
  WeChat-compatible inline HTML and preserves its semantic Markdown when edited
- Layout, Palette, Appearance, and Typeface visibly change the same article
  without changing its Markdown
- Desktop and Mobile preview display the same canonical HTML at different
  canvas widths; canvas size is not saved into the document
- Draft Edit and Preview no longer disagree on typography, spacing, media
  placement, or presentation
- event-number sources beginning with `10000` display as `Event` throughout the
  WxPost header, selector, and meeting context while retaining flexible Custom
  `Event Recap` editorial behavior
- at 390 px all presentation controls wrap without horizontal overflow, Ask
  Hermes opens from the normal toolbar instead of covering the article, and
  Draft loading explicitly identifies preview and media preparation
- the Paper Neutral + Editorial Serif default is visually checked against the
  agreed Style Lab direction for paper surface, headline/deck hierarchy,
  byline/date treatment, section rhythm, captions, and whitespace; this is a
  design-fidelity acceptance, not a request for pixel-identical colors
- clicking a rendered title or block edits in place without exposing raw
  Markdown or expanding into a differently sized form; clicking outside any
  editable title or block exits editing consistently
- gallery media uses the full available article width, preserves intrinsic
  aspect ratio, remains centered, and has no arbitrary maximum height or crop
- multi-image galleries use horizontal touch/trackpad scrolling and snapping
  without previous/next arrow controls
- Draft Edit provides a responsive cover picker over all workspace-ready
  images. A cover may remain outside the article body; cover changes stay local
  until Save Draft, and Materials deletion remains blocked while the saved
  Draft still references the image as its cover or body media
- renderer fixture tests cover all supported nodes, themes, missing media, and
  sanitization, followed by real signed-in desktop and mobile browser smoke

#### Slice 7A complete - saved Draft to public WxPost synchronization

The saved workspace Draft remains the editorial authority. Supabase and OSS
are a public projection, not another editor: Backend reloads and version-checks
the saved Draft, resolves every included workspace material, uploads or reuses
content-addressed public assets, runs the canonical trusted renderer, and only
then swaps the complete public row with one guarded update.

Implemented contract:

- `source_workspace_id` enforces one public WxPost per workspace;
  `source_draft_version` and `source_draft_sha256` identify the exact published
  bundle
- first publication remains hidden in `assembling` until every asset and the
  canonical render are ready; updates leave the previous `ready` revision
  public until finalization
- status is derived as `not-synced`, `up-to-date`, or `update-available`; the
  Draft and Workspaces UI display the same Backend result, while an unavailable
  Supabase status does not block private workspace listing
- member confirmation is required for first sync and update, version conflicts
  reuse the existing load-latest dialog, and ordinary failures use the existing
  toast pattern
- public content contains only public OSS URLs; after a new revision becomes
  ready, public assets it no longer references are removed from OSS and the
  asset table. Private workspace poster URLs are never exposed
- public reads require both `status = ready` and `is_public = true`; the stable
  route remains anonymously accessible
- workspace-linked public rows cannot be edited through the older direct WxPost
  update endpoint; changes must return to the saved Draft and explicit sync
- deleting the private workspace leaves its durable public WxPost and assets
  unchanged; signed-in members can separately delete that public revision from
  its public page without deleting the workspace or saved Draft

Acceptance completed with backend service/DB/route tests, Draft and Workspaces
browser tests, TypeScript/Ruff/mypy checks, a dry-run plus applied Supabase
migration, and real signed-in/anonymous Chrome smoke. The real public-media
run synchronized workspace `wxpost-a086a9e56a7e` Draft v5 to revision 1 at one
stable slug, copied all three included images to `public/wxposts/...` OSS keys,
rendered those public assets in Chrome, and exposed no private workspace URLs.
Repeating the same synchronization kept revision 1 and exactly three ready
asset rows. A separate revision run exercised two-tab conflict handling,
failed-network retry, and the previous-ready-revision guarantee through Draft
v18/public revision 5. Workspaces and Draft were also checked in real Chrome
at desktop, 820 px, and 390 px with no horizontal document overflow; the
private test workspace `wxpost-31a400fcfce7` was then permanently deleted and
the public `/posts/wxposts/regenerate-conflict-source-v14` remained available
at revision 5.

#### Slice 7B - Hermes image descriptions (complete)

The web Materials editor can explicitly ask Hermes to describe one selected
workspace image. Hermes returns one concise English editorial description,
polishing an existing description in any language when present. The operation
uses linked meeting context only as supporting evidence, stays independent of
other Materials mutations, and writes through the versioned controller.

Acceptance:

- image-description generation is explicit and scoped to one selected image
- the result is an editable English suggestion rather than a silent overwrite
- `Save Materials` is the explicit confirmation action and persists the
  suggestion as an AI-authored, confirmed description
- an existing description is translated, compressed, and polished rather than
  discarded
- upload, import, delete, and other local Materials edits remain usable while
  Hermes is working

#### Slice 7C - Draft Assistant and Controller hardening (complete)

This slice turns the initial Draft chat into a focused, observable, durable
WxPost assistant without changing the canonical authoring boundary. The saved
workspace Draft remains authoritative; Hermes chooses tools, Backend validates
typed edits, and Controller remains the only workspace writer.

Implemented contract:

- web Draft chat and the future Feishu channel use one managed `wxpost` Hermes
  profile with the formal WxPost Skill and MCP surface, fast model mode,
  browser/image access, and optional Tavily search. General terminal, coding,
  delegation, cron, plugin, and assistant-owned memory capabilities remain
  disabled
- ordinary questions may be answered directly; questions about the article
  read saved context; only explicit editorial requests load writing guidance
  and mutate the Draft
- local title, metadata, body-node, directive, media-description, body-media,
  and cover changes use version-bound typed operations. Whole-article
  restructuring continues to use the complete proposal contract
- imported media form the Draft editing pool. Materials `included` state
  affects Generate/Regenerate only; later Draft body and cover choices are
  independent, while Materials deletion still refuses saved Draft references
- genuine Hermes tool milestones stream beneath the pending member message,
  expose normalized tool and fine-grained edit names, collapse above the final
  response, follow the conversation while the member remains at the bottom,
  and survive refresh
- `/new` atomically switches the workspace to a fresh future Hermes session,
  retires the previous session asynchronously, and remains empty across a
  refresh before the first new message
- Hermes conversation history stays in the managed profile's `state.db`.
  Controller stores only workspace/session pointers, retryable deletion work,
  and exact UI milestone metadata in transactional SQLite; legacy JSON is
  imported once and removed
- a successful canonical Draft save is not reported as failed merely because
  auxiliary session or milestone metadata could not be persisted
- Draft updates replace the changed Draft data without blanking the workbench,
  and the frontend keeps one message-owned source of truth for completed steps

Acceptance completed with typed-edit Backend tests, controller session/store
and concurrency tests, frontend lint/type checks, and real signed-in Chrome
smoke. The final smoke changed one title through Hermes from Draft v68 to v69,
showed live fine-grained milestones without a whole-workbench loading state,
then refreshed and restored the final response plus all four completed steps.
The Controller SQLite integrity check returned `ok`.

#### Slice 7D - Conversational Feishu integration (complete)

This slice extends the existing plain Feishu channel without cards, Bitable,
or another rendering path. The managed `wxpost` profile is shared, but its tool
surface is selected by platform: Feishu receives workspace navigation plus the
canonical WxPost authoring tools, while the web Draft Assistant remains bound
to its current workspace and cannot list or switch workspaces.

Implemented contract:

- Feishu can list, select, and create linked or independent workspaces. Source,
  meeting/event, and Article Type are chosen during creation and become
  immutable, matching the web setup contract
- active Feishu workspace bindings and exact pending create/delete
  confirmations live transactionally in Controller SQLite. A confirmation must
  arrive in a later Feishu message, and duplicate delivery remains idempotent
- linked meeting candidates can be listed and imported; Feishu file/image
  attachments are imported from approved profile cache roots, content-hash
  deduplicated, assigned stable material IDs, and excluded by default
- Feishu can update saved Materials, generate a Draft, and apply the same typed
  Draft operations as the web assistant. Public synchronization remains an
  explicit authenticated web action
- the web Draft Assistant is physically bound to a read/Draft-only MCP surface;
  it cannot import, include, reorder, describe, or delete Materials. A request
  to change a Materials description explains the boundary without saving a
  Draft, incrementing its version, or opening a false Draft-conflict dialog
- the shared read-only workspace report deterministically separates the full
  media catalog into meeting/event candidates, imported media, Included media,
  and current Draft body/cover use while also reporting source, editorial,
  Draft, and public-revision state
- Feishu media-library requests display the complete catalog with stable M
  identifiers and state labels. Images use native image messages; videos use
  native video delivery and fall back to file attachments when needed
- Feishu and web keep different Hermes sessions even when they address the same
  workspace. Platform-specific tools cannot leak into the web session. Feishu
  can send canonical authenticated Materials or Draft Edit links, but the
  handoff explicitly warns that the web Draft Assistant does not inherit the
  Feishu conversation
- the integration uses the public Hermes profile/plugin lifecycle only; it does
  not patch the private Feishu adapter or restore the abandoned card flow

Deployment remains split by responsibility. Frontend and Backend may run on
Vercel; Backend reaches the Controller/Hermes deployment on DigitalOcean over
HTTPS with the existing service token. The new report path uses that same
contract and does not require these services to be deployed together.

Acceptance completed on 2026-08-04:

- a real Feishu DM listed and selected workspaces, reset its Hermes conversation
  while preserving the active binding, created a Meeting 463 workspace, listed
  ten linked candidates, imported and included M01, generated Draft v1, and
  changed its title through a typed edit to Draft v2
- a real Feishu attachment imported once as M11 and remained excluded; signed-in
  Chrome then displayed M11 with `Use material`, the saved Draft v2, and locked
  Source, meeting, and Article Type controls
- the Feishu single-confirmation flow created one independent Custom workspace;
  the same channel rejected public publication as out of scope
- Chrome proved session and tool isolation: Feishu turns did not appear in the
  web Draft Assistant, and the web assistant refused global workspace listing
- automated coverage includes group/thread binding, absent bindings, duplicate
  events, confirmations, candidate import, attachment safety/deduplication, and
  platform tool isolation. The complete Hermes/controller suite passed 187/187
  and the complete Backend suite passed 620/620; frontend TypeScript and lint
  checks passed with only the four pre-existing `TimePickerModal` hook warnings

### Phase 3 - WeChat Official Account Draft integration

This is a completed publishing integration, not another Phase 2 authoring
slice. Backend-owned credentials and token caching, WeChat media upload, cover
and metadata validation, and create/update Draft operations all consume the
same saved Draft and canonical inline HTML. No agent regenerates or restyles
the article during delivery.

Acceptance:

- the exact canonical HTML reviewed in the product is submitted after only
  deterministic media-URL replacement and platform sanitization
- create/update operations are confirmed, retryable, and idempotent so repeated
  clicks do not create duplicate WeChat drafts
- WeChat draft readback and a WeChat mobile preview are compared with the
  outgoing HTML; filtering differences are surfaced rather than repaired with
  article-specific heuristics

### Phase 4 - Optional hardening

Retained Draft history/rollback, true simultaneous collaborative editing,
analytics, bulk operational tooling, shareable style presets, and Bitable are
optional follow-ups. They are not required to complete the current
WxPost + Hermes + Feishu goal.

### Meeting Form

- Comprehensive form for meeting details including:
  - Meeting type, theme, manager
  - Date, start/end times
  - Location
  - Segments editor for managing meeting agenda
- Save functionality that preserves meeting as draft
- Validation rules with appropriate UI feedback

### Role Taker Input Component

- Custom input component for selecting or creating role takers
- Supports both members and guests as attendees
- Auto-suggests existing club members
- Allows creating guest attendees with custom names
- Provides visual distinction between member and guest selections

### Meeting Awards Form Component

- Component for managing meeting awards
- Add/remove functionality for awards
- Category selection with standard options and custom input
- Winner selection with member auto-suggestion
- Validation with appropriate UI feedback
- Save functionality to submit all awards at once

### Meeting Voting Component

- Component for meeting voting functionality
- Categorized voting options (Best Speaker, Best Table Topics, Best Evaluator, etc.)
- Support for both members and guests to cast votes
- Visual status indicator for open/closed voting
- Vote count tracking
- Admin controls to open/close voting for a meeting

### Meeting Agenda Workbook Page (/meetings/workbook/[id])

- Browser-based preview of the Excel-compatible agenda
- Download button for authenticated users
- Preview mode for draft meetings
- Proper section formatting for all meeting components

## Data Model

The application uses several key interfaces:

- **UserIF** - User information (uid, username, full_name)
- **AttendeeIF** - Meeting participant information
- **SegmentIF** - Meeting segments/agenda items with role taker references to attendees
- **MeetingIF** - Complete meeting data structure with status field ("draft" or "published")
- **MediaFile** - Media file structure with filename, url, fileKey, and uploadedAt fields
- **AwardIF** - Award structure with meeting_id, category, and winner fields
- **PostIF** - Post structure with title, slug, content, visibility, and author information
- **WxPost** interfaces - Public article documents, workspace manifests,
  versioned material sources, editorial state, and paginated workspace
  summaries
- **VoteIF** - Vote structure with meeting_id, category, name, segment (optional), and count fields
- **VoteStatusIF** - Vote status structure with meeting_id and open (boolean) fields

## Technical Implementation

- Uses Next.js App Router for routing
- Authentication with token-based system
- React Query for data fetching
- Jotai for state management
- Tailwind CSS for styling
- Mobile-responsive design

## Development Status

### Completed Features

- User authentication
- Meeting template selection
- Meeting form with segment editing
- Template transformation with UUID generation
- Responsive UI
- Meeting listing with status indicators
- Meeting creation (saving as draft)
- Meeting edit functionality
- Status management (draft/published)
- Role taker input component with member/guest handling
- Time picker components for meeting segments
- Segments editor with add/edit/delete operations
- Media upload and management for meetings
- Success/error notifications for user actions
- Attendee handling for role assignments
- Meeting awards management
- Post management with create, read, update, and delete capabilities
- Public WxPost rendering and filtering inside Posts
- Source-only WxPost Setup and immutable workspace creation
- Browser-local Materials editing with explicit Save Materials
- Version-conflict confirmation for every Materials mutation
- Responsive, paginated shared Workspaces list with semantic edit routes
- Meeting voting system with category-based voting
- Meeting media display with image gallery and lightbox
- Vote status management (open/close voting)
- Voting permissions for members and non-members
- Meeting agenda workbook generation with Excel compatibility
- Browser-based preview with responsive Excel-like styling

### Current Implementation Details

The meeting management workflow is now fully implemented:

1. **Meeting Creation**

   - Users can create meetings using templates, image upload, or text descriptions
   - All new meetings are saved as drafts by default
   - Multiple validation options with appropriate feedback

2. **Meeting Listing**

   - Responsive meeting card design
   - Different visibility based on authentication status
   - Clear status indicators for draft meetings

3. **Meeting Editing**

   - Full editing capabilities for existing meetings
   - Status management (draft/published)
   - Validation before publishing

4. **Meeting Form Components**

   - Rich form controls with validation
   - Segments editor for detailed agenda management
   - Time management with visual pickers

5. **User Feedback**

   - Loading states during API operations
   - Success notifications after operations complete
   - Error handling with appropriate messages

6. **Awards Management**

   - UI for adding and managing meeting awards
   - Support for both standard and custom award categories
   - Winner selection with member auto-suggestion
   - Validation before submitting awards
   - Success/error notifications for award operations

7. **Post Management**

   - Posts are markdown based
   - Complete CRUD operations for posts
   - Visibility controls (public/private)
   - Access control based on visibility and user authentication

8. **WxPost Workspace Authoring**

   - Creates linked or independent workspaces from immutable Source and Article
     Type choices on the Setup page
   - Opens existing workspaces directly in Materials
   - Keeps ordinary form edits local until "Save Materials"
   - Keeps the saved Draft isolated from Materials edits
   - Executes import, upload, and delete immediately with manifest-version
     protection
   - Lists shared workspaces with pagination, stable creation-time ordering,
     compact linked-meeting metadata, and resilient loading/error states
   - Keeps workspace cards visible during deletion and background refreshes;
     only the first load replaces the list with the centered spinner
   - Implements a workspace-local, multi-select `Voice & tone` brief with six
     presets, up to three selections, and optional custom profiles with a
     user-editable Hermes-proposed instruction
   - Generates or regenerates a strict editorial Draft proposal through one
     workspace-scoped `hermes serve` session and the formal WxPost Skill;
     Controller derives manifest-owned source fields and AI caption provenance
     before backend validation
   - Keeps material IDs independent from article position, assigns canonical
     media order from the proposal, and requires included media to use the
     supported image, gallery, video, or person body directives
   - Renders the Draft beside its focused Hermes conversation on desktop and
     opens Hermes in a bottom sheet on mobile
   - Supports local title/block edits, selected-text context, and explicit Save
     Draft
   - Supports structural media removal in Draft Edit without changing
     Materials; Materials deletion is blocked until every saved Draft reference
     is removed and the Draft is saved
   - Keeps authoring and review in Draft-local Edit/Preview modes with shared
     layout, palette, appearance, typeface, and Desktop/Mobile controls
   - Persists presentation choices with Save Draft while keeping Desktop/Mobile
     canvas selection browser-local
   - Preserves the saved Draft on generation/chat failure or version conflict;
     stale direct edits remain local for the member to recover
   - Keeps full workspace editing in the web workbench while Slice 7D exposes
     Feishu-only workspace navigation and conversational Materials/Draft
     operations; public synchronization remains the explicit Slice 7A web action
   - Shows a member-only circular WeChat action immediately left of Public
     Revision deletion; it freezes the selected layout, palette, appearance,
     and typeface for explicit confirmation before creating or updating a
     WeChat draft
   - Treats the WeChat result as a publication projection rather than another
     editor: the dialog blocks Video and lets an uncertain first create retry
     the server-owned recovery path; after a draft exists, a separate
     member-only action remains visibly reserved to the left of publishing,
     stays disabled until a draft exists, and then fetches and opens the
     official temporary preview
   - Leaves the WeChat draft in the Official Account when a Public Revision is
     deleted and states that behavior in the deletion confirmation

   Validation recorded on 2026-08-03:

   - A signed-in Chrome smoke test exercised a real Meeting 463 workspace across
     general questions, focused Draft revision, live milestones, partial Draft
     refresh, `/new` cancel/confirm, refresh before and after the first new
     message, assistant identity, and cover removal/restoration.
   - The smoke test found and corrected one cover-only regression: clearing a
     cover must return that imported image to the workspace library without
     inserting it into the article body. The same live operation then passed,
     and M08 was restored as the cover-only image in the test workspace.
   - The full WxPost Playwright surface passed 80/80 serially. Focused repeats
     passed 5/5 for streamed milestones and 5/5 for chat auto-scroll behavior.
   - Hermes/controller tests passed 151/151 and backend WxPost contract,
     persistence, proxy, directive, Hermes, and publication tests passed
     105/105. The only remaining output is the existing pytest-asyncio fixture
     loop-scope deprecation warning.

   Phase 3 validation recorded on 2026-08-06:

   - TypeScript, changed-file Prettier, and ESLint passed; ESLint still reports
     only the existing `TimePickerModal.tsx` hook warnings.
   - The authenticated flow passed in the user's current Chrome: the green
     outline WeChat icon uses the same white circular treatment as deletion,
     remains between the separate preview and deletion actions, and opens the
     create/update confirmation immediately without publishing or repeating
     the page-load status request on the first click. The confirmation keeps
     the selected Revision/presentation and draft-only explanation without the
     obsolete Dark/Gallery mobile-preview warning.
   - The full WxPost Playwright surface passed 81/82 after two unrelated
     parallel-only failures passed when rerun alone. The Phase 3 renderer and
     publication tests passed; the sole failure is the pre-existing,
     untouched Workspace test for refreshing a cached empty list after an
     independent workspace is created. It also fails alone and is not treated
     as a Phase 3 regression.
   - After explicit approval, the real Meeting 463 Saved Draft changed only its
     excerpt (v18 to v19), synchronized Public Revision 2, and passed the
     120-character WeChat digest boundary with an exact 118-character value.
   - Real WeChat body/cover upload and `draft/add` created one draft. An
     identical retry was `unchanged`; a Modern Sans update and restoration to
     the final Brand Default / Paper Neutral / Light / Editorial Serif setting
     all kept the same media ID and real draft count of one.
   - Real readback preserved the text and tag sequence while WeChat performed
     bounded platform filtering on image loading attributes and selected inline
     styles. The standalone preview action opened the real `mp.weixin.qq.com`
     temporary preview in the user's Chrome with the title, digest, article
     structure, and both body images loaded.
   - Media captions now use the canonical renderer's smaller 14px / 1.65 line
     height treatment instead of matching 16px body copy. The v6 WeChat image
     wrapper compatibility remains in place; the real submitted HTML and
     `draft/get` readback retained both the compact wrapper and all four caption
     styles on the diagnostic draft without creating a new media ID.
   - The v9 WeChat projection removes only the selected palette's ordinary
     foreground color after deterministic appearance mapping. This lets
     WeChat supply readable body and heading text in its current Light or Dark
     surface while preserving muted copy, accents, borders, and component
     surfaces. A real dark diagnostic update reused the existing media ID, and
     `draft/get` retained the expected bounded color set. Computer Use then
     reopened the official preview at 390 x 844 and confirmed that ordinary
     body and heading text resolve through WeChat's native dark foreground.
   - The v10 WeChat projection removes the canonical article header only for
     WeChat delivery, avoiding a second title, byline, and digest beneath the
     platform's native metadata. The real diagnostic draft updated in place;
     submitted HTML, `draft/get`, and the refreshed 390 x 844 official preview
     all begin with the actual opening paragraph. Public Revision rendering is
     unchanged.
   - The v11 WeChat projection preserves the canonical header's top rule after
     removing its repeated metadata, including the original Brand Blue
     gradient, and halves the combined whitespace before the opening paragraph.
     The real 390 x 844 official preview shows the rule directly above the
     compact opening copy; Web rendering remains unchanged.
   - The v12 WeChat projection removes its remaining article top padding and
     caps thick WeChat header rules at 2px without widening palettes that use a
     1px rule. Submitted HTML, readback, and the real 390 x 844 preview preserve
     the thinner gradient and leave only WeChat's native metadata gap above it.
   - Projection version 13 confines dark-to-adaptive palette conversion to
     inline `style` values, so matching color tokens in prose, alt text, URLs,
     and other attributes remain byte-for-byte content. Uncertain creation can
     now retry server recovery after a page reload; recovery candidates must
     also match deterministic body text/tag/image signatures. If no unique
     candidate can be recovered, a separate warning confirmation lets a member
     reset only the local uncertain state after checking that no matching
     Official Account draft exists.
   - The Public Revision footer now states that its presentation choices are
     used by the next WeChat draft publication instead of incorrectly claiming
     they affect only the web preview.
   - Computer Use verified the revised footer and ordinary update confirmation
     in the user's current 390px Chrome view. An explicitly confirmed update of
     the existing diagnostic draft completed with `WeChat draft updated!`; the
     Backend returned success only after its real WeChat `draft/get` readback.
   - Physical-phone checks confirmed the content-controlled list, Quote,
     Takeaway, image, caption-spacing, and light-surface behavior. No
     publication code truncated, regenerated, rewrote, or re-laid out content;
     the final production smoke follows deployment of the fixed-egress gateway.
   - Production rollout still requires fixed outbound IP for Vercel-originated
     WeChat API work. The next deployment slice will route only those API calls
     through a thin VPS gateway; the Backend remains the sole projection
     orchestrator and Supabase writer, and the frontend contract does not
     change.

9. **Voting System**

   - Category-based voting for meetings (Best Speaker, Best Table Topics, etc.)
   - Voting status management (open/close)
   - Vote counting with atomic operations
   - Different permissions for members and non-members
   - Admin controls for managing voting
   - Real-time vote count updates

10. **Meeting Agenda Workbook**

- Excel-compatible workbook generation with proper formatting
- Browser-based preview with responsive design
- Support for complex Excel features (merged cells, styling)
- Embedded images (club logos and QR codes)
- Preview mode for draft meetings
- Authentication-gated download functionality
- Proper section formatting for all meeting components

11. **Meeting Media Management**

- Image upload functionality for meetings
- Media display in expandable meeting cards with tabbed interface
- Responsive image gallery with grid layout
- Interactive lightbox for full-size image viewing
- Image navigation with prev/next controls in lightbox
- Environment-aware handling of HTTP/HTTPS URLs

The application follows a clean, modern UI design with gradient accents, responsive layouts, and thoughtful user interactions. The meeting creation workflow is particularly sophisticated, offering multiple creation methods and detailed customization options.
