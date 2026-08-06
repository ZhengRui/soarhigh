# Hermes container

This directory runs the Hermes Gateway and WxPost HTTP controller as two
services in one Compose project. The Gateway exposes Hermes's authenticated
Agent API for focused editorial suggestions and `hermes serve` for persisted
workspace-scoped Draft sessions. Hermes state and article working files remain
in two separate host directories:

| Host setting           | Container path | Purpose                                                                 |
| ---------------------- | -------------- | ----------------------------------------------------------------------- |
| `HERMES_HOME_DIR`      | `/opt/data`    | Configuration, credentials, memory, sessions, skills, and gateway state |
| `HERMES_WORKSPACE_DIR` | `/workspace`   | WxPost article workspaces and their local source files                  |

The Compose file mounts only the small `wxpost_controller` package read-only at
`/opt/soarhigh/wxpost_controller`. The rest of the SoarHigh repository, the
complete host home directory, Docker socket, SSH credentials, and Git
credentials are not mounted into the container.

## Dedicated WxPost profile

Container startup builds a managed Hermes profile named `wxpost` under
`HERMES_HOME_DIR/profiles/wxpost`. Both the web Draft Assistant (`hermes
serve`) and the normal Feishu channel run through this same profile. This is a
plain Hermes Feishu connection; the abandoned WxPost card experiment is not
installed or loaded.

The profile inherits the configured model, provider credentials, and platform
settings from the default Hermes configuration, enables Hermes fast mode for
`gpt-5.6-luna`, then narrows the agent surface to:

- the tracked `soarhigh-wxpost-authoring` Skill;
- the full `soarhigh-wxpost` MCP server for Feishu;
- session-bound `wxpost_current` tools for the web Draft Assistant, which
  derive the exact workspace from the Controller-owned session directory and
  accept no model-supplied workspace ID;
- browser-based web access and image understanding;
- Tavily search and extraction when `TAVILY_API_KEY` is configured.

General terminal, filesystem, code-execution, delegation, memory, cron, and
unrelated plugin capabilities are explicitly disabled. The one tracked
navigation plugin exposes only Feishu conversation identity, workspace
navigation, configuration reports, native media display, and attachment
import; its toolset is absent from web sessions. The web surface cannot call
Materials import, inclusion, description, ordering, or deletion mutations.
Profile memory and user-profile injection are also disabled so workspace state
remains in the canonical controller rather than a second assistant-owned store.

Feishu conversations start in read-only mode. They retain the selected
workspace context and may inspect Materials and Drafts, answer questions,
search the web, and deliver previews, but every workspace, Materials, and Draft
write is rejected in code. Send `/editing` twice in separate messages to see
the warning and confirm editing mode; send `/readonly` to return immediately.
Selecting or creating a workspace and `/new` always reset the conversation to
read-only. The mode and its short-lived confirmation are stored by the
Controller in `controller.sqlite3`, independently from Hermes chat history.
The Feishu navigation layer checks the mode before its own mutations, while a
`pre_tool_call` hook guards the complete raw WxPost MCP write surface. Web Draft
Assistant sessions are not subject to this Feishu-only mode.
Images and files sent while read-only remain available for ordinary visual
questions and conversation. They are not imported into Materials unless the
member explicitly enters editing mode and resends them for import.

`wxpost_profile/configure.py` recreates the managed capability configuration
plus the tracked Skill and navigation plugin on every container start. It does
not modify the default profile beyond removing the superseded WxPost MCP, Skill
copy, and abandoned card plugin. `run_gateway.sh` stops any gateway restored
from stale profile state, makes `wxpost` the active profile, and leaves exactly
one supervised Feishu gateway plus one isolated backend on port 9119.

After changing the profile source, Skill, Compose mounts, or startup script,
recreate the services so the generated profile is refreshed:

```bash
docker compose \
  --env-file claws/hermes/.env.local \
  --file claws/hermes/compose.yaml \
  up --detach --force-recreate gateway controller
```

## First startup

The first interactive `up` asks for the Hermes home, workspace, image,
container name, and the existing Backend WxPost service token:

```bash
./claws/hermes/hermes.sh up
```

It displays the resolved configuration for confirmation, creates the workspace
when necessary, writes `claws/hermes/.env.local`, and then starts the
container. It requires the Hermes home to exist already and never overwrites an
existing `.env.local`.

The default paths are:

```dotenv
HERMES_HOME_DIR=/Users/example/.hermes
HERMES_WORKSPACE_DIR=/Users/example/hermes-workspace
HERMES_IMAGE=nousresearch/hermes-agent:latest
HERMES_CONTAINER_NAME=soarhigh-hermes
SOARHIGH_WXPOST_SERVICE_TOKEN=use-the-value-from-backend-WXPOST_SERVICE_TOKEN
```

The setup accepts `~` in an answer but stores the resolved absolute path. It
rejects the filesystem root, the complete host home, the SoarHigh repository,
and overlapping Hermes home/workspace directories.

For non-interactive deployment, copy `.env.example` manually and use absolute
paths:

```bash
cp claws/hermes/.env.example claws/hermes/.env.local
```

Create both directories before a non-interactive startup. The Compose file
deliberately refuses to create missing bind-mount directories.

`HERMES_HOME_DIR` contains secrets and persistent Hermes state. Keep it outside
the repository and back it up before image upgrades. `.env.local` is ignored by
Git.

The mounted Hermes `config.yaml` should use the container-local terminal:

```yaml
terminal:
  backend: local
  cwd: /workspace
```

Stop any Hermes Gateway running directly on the host before starting this
container. Two gateways must not share the same Hermes home or Feishu
connection.

## Common commands

Run the wrapper from any working directory:

```bash
./claws/hermes/hermes.sh up
./claws/hermes/hermes.sh down
./claws/hermes/hermes.sh restart
./claws/hermes/hermes.sh shell
./claws/hermes/hermes.sh logs
```

The wrapper supplies the current host UID and GID, validates the Compose
configuration, and delegates to Docker Compose. `up` starts both the Gateway
and the HTTP controller. Only the first interactive `up` starts the
configuration prompt; the other commands never create configuration.

`shell` opens Bash as the non-root `hermes` user, sets `HOME=/opt/data`, and
starts in `/workspace`. The Gateway is already started by `up`; do not run a
second `hermes gateway run` from this shell.

`logs` displays the most recent 100 Gateway log lines and follows new output.
Press `Ctrl+C` to stop following logs; the Gateway continues running. Treat
the output as sensitive because platform connection URLs and identifiers may
appear in Gateway logs.

`down` removes the container and Compose network only. It never passes `-v`,
so the two host directories and all Hermes data remain untouched.

`restart` restarts the existing container. It does not reload a changed image,
mount, or environment setting. After changing `.env.local` or `compose.yaml`,
run `hermes.sh up` so Compose can recreate the container if necessary.

## Other Docker operations

Use Docker Compose directly for everything else:

```bash
docker compose \
  --env-file claws/hermes/.env.local \
  --file claws/hermes/compose.yaml \
  ps

docker exec soarhigh-hermes hermes gateway status
```

If `HERMES_CONTAINER_NAME` is changed, use that name with `docker exec`.

To update the configured image:

```bash
docker compose \
  --env-file claws/hermes/.env.local \
  --file claws/hermes/compose.yaml \
  pull

./claws/hermes/hermes.sh up
```

Back up `HERMES_HOME_DIR` before upgrading. Hermes may migrate its persistent
configuration when a newer image starts.

## WxPost workspace controller

The tracked `wxpost_controller` package is the shared boundary for one
canonical WxPost authoring workspace. Its full Feishu MCP surface implements
the complete material-controller and Draft operations:

```text
wxpost_get_context
wxpost_get_workspace_report
wxpost_update_workspace
wxpost_import_source
wxpost_set_source_included
wxpost_update_sources
wxpost_delete_source_preflight
wxpost_delete_source
wxpost_save_draft
wxpost_edit_draft
```

The web Draft Assistant receives only `wxpost_get_context`,
`wxpost_get_workspace_report`, `wxpost_save_draft`, and
`wxpost_edit_draft`. This is enforced by the configured platform tool surface,
not merely by prompt instructions. A request to change a Materials description
therefore receives an explanation and cannot mutate Materials or create a
Draft version. Feishu receives the full surface because Materials management
is part of its approved conversational workflow.

The HTTP and MCP servers are thin adapters over the same controller core and
return the same error and version-conflict details. HTTP exposes the Materials
operations, direct Draft saves, and focused Hermes Draft requests needed by the
authoring page; MCP exposes the canonical operations used by the formal
`soarhigh-wxpost-authoring` Skill.

`contracts.py` defines the single supported `source-manifest v4` shape plus the
operation inputs. A complete manifest example lives at
`tests/fixtures/source-manifest-v4.json`. Important invariants include:

- each collected source receives the next workspace-local material ID
  (`M01`, `M02`, and so on) when it enters the manifest; the ID is persisted,
  never recalculated from source order, and never reused after deletion;
  `nextMaterialNumber` persists that high-water mark;
- meeting-library provenance keeps the backend `fileKey`, while the local file
  path is derived as `sources/{sourceId}{originalSuffix}`;
- Hermes submits strict Draft proposal schema v2 containing only editorial
  fields, ordered typed content blocks, media references, and an optional cover
  reference. Generate and Regenerate derive source-owned fields from current
  Materials. Focused revisions start from the saved Draft and declare media
  additions, removals, and cover intent explicitly; imported workspace-ready
  media remains available even when it is not Materials-included.
  Hermes-authored article descriptions begin as AI proposals needing member
  confirmation;
- generated `ArticleDocument.media` keeps the same material IDs so its body and
  cover references point back to the corresponding manifest sources. Proposal
  media order expresses intended article order; `M01`, `M02`, and so on are
  stable identities and do not determine where media appears in the article.
  One workspace-ready image may be retained as cover-only media without a body
  directive;
- meeting-library sources may remain references with
  `workspaceReady=false, included=false`;
- workspace bootstrap is create-only and registers the meeting media visible at
  creation without downloading it; opening an existing workspace reads its
  context and never changes its sources;
- importing copies one meeting-library source to its derived local path;
  including a non-ready meeting source performs that import and inclusion in
  one versioned operation;
- web and article-scoped Feishu uploads are already materialized and must start
  workspace-ready;
- inclusion requires a workspace-ready source;
- description text, provenance, and confirmation status change atomically;
- source array position is the only stored Materials-page order; `moveToIndex`
  moves one source and shifts the surrounding entries without persisting a
  duplicate `order` field. This is separate from article media order;
- material changes advance only `manifestVersion`;
- every Materials mutation, including form saves, import, upload, and delete,
  requires the current `manifestVersion`; a stale operation changes nothing and
  returns a version conflict for the user to resolve;
- delete preflight reports references in the latest saved draft; deleting a
  referenced source requires explicit confirmation, direct uploads lose their
  manifest record, and meeting-library sources retain their `fileKey` so they
  can be imported again;
- `draft/article.json` is always the raw canonical `ArticleDocument`;
- draft version, source-manifest version, hash, and the optional Hermes save
  operation ID live in the manifest, outside the article document;
- draft saves use the backend-owned `/posts/wxposts/validate` endpoint instead
  of maintaining a second ArticleDocument validator in the controller; the
  normalized document returned by that endpoint is the one stored on disk;
- draft saves require both expected manifest and draft versions. Complete
  article saves accept only proposal schema v2; fine-grained revisions accept
  only the typed edit union. Both reject invalid material references and never
  ask Hermes to reproduce controller-owned media fields. Generate/Regenerate
  require every Materials-included medium; whole-article revisions preserve
  current Draft media unless an explicit delta changes it;
- ordinary article prose remains free-form Markdown inside typed `markdown` and
  `section.body` blocks. Hermes selects typed semantic blocks and never writes
  fenced YAML. The controller deterministically serializes those blocks into
  the backend-supported ArticleDocument v1 directives. Each included medium
  must be referenced by a supported media block; unsupported placeholders are
  rejected, not repaired heuristically.

`section` gives every major narrative section an explicit kicker and ordering
boundary. `image` places one image without gallery chrome; `gallery`, `video`,
and `person` cover richer media structures. The confirmed
`==important phrase==` inline extension marks a semantic key point; its visual
treatment belongs to the renderer theme rather than Hermes. Version 1 also
retains the structural `takeaway`, `info-grid`, `timeline`, and `pull-quote`
directives. The registry is versioned and extensible: a future directive may be
added when its semantic purpose, payload schema, renderer behavior, Skill
guidance, capabilities response, fixtures, and tests are added together.
Arbitrary or unknown directives remain invalid.

## Draft generation and content templates

The current Draft-generation turn intentionally uses a small orchestration
prompt. It names the `soarhigh-wxpost-authoring` Skill, workspace, operation,
expected manifest and Draft versions, and a unique save operation ID. It does
not interpolate the complete Materials state into a Python prompt template.
Hermes loads the mounted Skill, calls `wxpost_get_context`, authors proposal
schema v2 from that tool result, and saves it through `wxpost_save_draft`.
The controller accepts success only when the resulting Draft carries that same
operation ID, so a concurrent direct save cannot be adopted as Hermes output.
Turns are serialized per workspace; unrelated workspaces do not wait behind
one another.

Draft Assistant chat uses the same session but does not force every message
through a save. A general question may be answered without reading the
workspace; a question about the article reads `wxpost_get_context` and answers
without saving. A small editorial request uses `wxpost_edit_draft` with typed,
version-bound node, directive, media, description, or cover edits; a genuine
whole-article restructure or rewrite still uses `wxpost_save_draft`. The
controller reports whether the Draft changed and accepts only an unchanged
version or one operation-ID-matched increment. A chat failure does not make the
Hermes connection unavailable.

`wxpost_get_context` exposes a Draft-only `editContext.body` to Hermes. Its
ordered node indexes belong to the returned Draft version and are never stored
in browser state or matched heuristically by text. Backend applies the typed
operations against that exact canonical document, re-derives the media
dependency snapshot from body references plus `coverMediaId`, validates the
result, and only then lets the controller perform the version-checked atomic
save. Materials `included` state is not changed by Draft edits. Any imported
workspace-ready image may be a cover without appearing in the body.

If the first save is rejected before persistence solely by the formal proposal
or ArticleDocument validator, Hermes may correct the typed proposal once from
that exact error and make one replacement save with the same expected versions.
It never parses or repairs YAML, guesses media IDs, retries version conflicts,
or retries runtime failures. The versioned session title prevents a breaking
proposal revision from reusing an older protocol conversation.

The authoring session protocol is version 7. Its mutation calls include the
turn-specific operation ID. Fine-grained revisions use the typed edit contract;
whole-article revisions retain the proposal-v2 media delta contract. Generate
and Regenerate still select their source snapshot from current Materials. The
editorial proposal itself remains schema v2.
The strict proposal deliberately omits `presentation`. The controller applies
the agreed default for the first Draft and preserves the saved/current
presentation on Generate, Regenerate, and normal editorial revisions.

This keeps responsibilities separate:

- the turn prompt controls the operation and version protocol;
- MCP supplies the current saved Materials and Draft;
- the Skill controls editorial behavior and supported proposal syntax;
- the controller derives manifest-owned fields and performs the canonical save;
- Backend validates and normalizes the final `ArticleDocument`.

The formal Skill implements flexible content recipes for Meeting Recap, Member
Story, Event Preview, Meeting Review, Action Guide, and Custom. A recipe
describes likely modules, editorial goals, useful metadata, and conditional
sections without forcing fixed headings or a fixed order. `Meeting Recap`, for
example, normally uses a grounded opening, relevant meeting highlights and
recognition, contextual media placement, and a meaningful close, while Hermes
may omit, reorder, or add modules when the saved evidence supports it. Custom
`Event Recap` is explicitly treated as a completed-event story rather than an
Event Preview.

The recipes include explicit source priorities, alternative narrative shapes,
semantic-block selection rules, optional-module and omission guidance, failure
modes, media-placement rules, and representative manual-review scenarios.
Those scenarios are a human review checklist, not an automated quality
evaluation. Proposal `blocks[]` is a typed transport contract, not a fixed
article outline: Generate and Regenerate may choose any evidence-supported
sequence. Focused revisions preserve unrelated content, and every operation
preserves the member's saved presentation unless the member explicitly changes
it. Presentation defaults and persistence are controller/member-owned: normal
editorial generation must not creatively choose a new layout, palette,
appearance, or typeface.

For linked workspaces, the MCP agent context augments the saved workspace with
live, read-only `meetingContext` from Backend: meeting number and type, theme,
manager, introduction, date, time, location, agenda, and awards. This context
is available to Hermes for generation but is not duplicated in
`source-manifest.json`. Independent workspaces receive null meeting context.
Failure to load context for a linked meeting is explicit instead of silently
generating with incomplete facts.

The Skill also resolves every selected preset Voice & tone ID to its complete
instruction. Selected custom profiles already carry their own saved
instructions. Article type, writing approach, voice and tone, free-form brief,
transcript, notes, material descriptions, and linked meeting facts therefore
reach generation through one saved Materials snapshot plus the live meeting
context, rather than a second interpolated prompt schema.

Presentation remains separate from content recipes. Layout, palette,
appearance, and typeface are saved Draft fields. Desktop/Mobile is browser-only
view state. The frontend exposes all five controls in Draft-local Edit and
Preview modes, removes the redundant standalone Preview stage, and reserves a
later Publish/Sync stage for public revisions and asset synchronization.

## Canonical rendering boundary

Hermes authors content; it does not author presentation HTML. The canonical
editable input remains `ArticleDocument`: free-form Markdown, a small set of
semantic fenced YAML directives, media metadata, and presentation settings.
The nine registered block directives express rich structures that ordinary
Markdown cannot represent reliably: `section`, `image`, `gallery`, `video`,
`person`, `takeaway`, `info-grid`, `timeline`, and `pull-quote`. They must not
carry colors, fonts, spacing, or other theme decisions. The
`==important phrase==` extension carries only key-point meaning; the renderer
owns whether that becomes an underline or another theme-appropriate emphasis.

The target rendering flow is:

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

There is one framework-independent TypeScript compiler built for two runtimes,
not an independently styled web renderer plus a later exporter. Browser Draft
imports it directly for immediate local editing and presentation changes. A
stateless trusted Next server route imports the same source to produce
authoritative HTML from the backend-normalized `WxPostRenderDocument`.
Browser-generated HTML is never accepted for persistence or publication. The
server route holds no workspace access or publication credentials; Backend
retains authentication, versions, material validation, persistence, public
sync, and WeChat delivery. The route reuses the existing server-side WxPost
service credential and adds no renderer-specific token; no credential reaches
browser JavaScript. Backend resolves the route from the existing
`WXPOST_PUBLIC_BASE_URL` and authenticates with the existing
`WXPOST_SERVICE_TOKEN`. The Next server receives that same token as server-only
configuration; the renderer introduces no new variable name or credential
value. For local development, put that same value in `frontend/.env.local` and
restart `bun dev`; it is read only by the trusted Next route and is never
exposed as a `NEXT_PUBLIC_` variable.

Draft Preview may retain editor-only node IDs and signed preview URLs.
Publish/Sync replaces media URLs, removes editor-only attributes, sanitizes,
and validates the same output. Those steps are post-processors, not alternative
renderers. A renderer failure changes no saved or public state.

Tailwind remains the styling system for the surrounding web application. The
article output itself cannot depend on Tailwind classes, CSS variables,
pseudo-elements, JavaScript, CSS Grid, or browser-only responsive behavior.
Layout, palette, appearance, and typeface instead select deterministic renderer
templates and inline presentation tokens.

This boundary avoids asking Hermes to reproduce visual boilerplate, keeps
presentation switches independent from article meaning, and prevents Preview
and publication from drifting. Exact platform fidelity still requires WeChat
asset upload, draft readback, and a WeChat mobile preview because WeChat may
filter otherwise valid HTML or styles.

The compiler also needs a small host-owned `RenderContext` for values that
belong to the publishing surface rather than article prose: resolved asset
URLs, context/folio label, display date, and publisher identity. Hermes must not
write those values into headings so the renderer can recover them later, and
the renderer must not guess them from prose. Missing values are omitted rather
than invented. The paper display date comes from the public WxPost record's
first-sync `created_at`, stays stable across later revisions, and is omitted
before public synchronization. `RenderContext` is assembled per render request;
it does not add another workspace JSON field or persistence model. Asset URLs
come from the validated media mapping for the active target, context/folio copy
comes from resolved workspace/public metadata, and publisher identity uses the
configured publisher fallback unless the document supplies a byline.

The completed Slice 6 boundaries are covered by deterministic controller,
Skill, compiler, trusted-route, and UI tests. The 2026-07-30 acceptance run
also completed a live
container-backed Generate and follow-up revision through a real signed-in
Chrome session. The generated media-free Meeting Recap used live theme, date,
location, agenda, roles, and speech details; Backend validation, Draft version
increments, presentation saving, Edit/Preview, mobile Hermes, and
test-workspace cleanup all succeeded. The 2026-07-31 closeout adds
cross-runtime byte-equality, all registered presentation combinations,
inline-HTML safety, representative Skill cases, and Draft editing regressions.

The core accepts opaque workspace IDs below `/workspace/inbox`, rejects symlink
and path traversal, limits collected files to 50 MiB, checks every
workspace-ready file and declared size, uses a per-workspace file lock,
validates stored and incoming data, and writes by atomic replacement.
All material operations and draft saves require operation-specific expected
versions. A short-lived pending record makes the two-file draft/manifest update
recoverable if the process stops between the two atomic replacements.

Linked workspaces read `/meetings/{meetingId}/media` from
`SOARHIGH_API_BASE_URL`. Compose maps
`SOARHIGH_WXPOST_SERVICE_TOKEN` to `WXPOST_SERVICE_TOKEN` inside both
containers; its value must equal Backend's existing `WXPOST_SERVICE_TOKEN`.
The same value is also mapped to the Gateway's `API_SERVER_KEY` and
`HERMES_DASHBOARD_SESSION_TOKEN`; it is sent only from Backend to the
controller or Hermes, never to the browser or an asset URL.

Feishu Draft replies use a temporary preview flow rather than a public WxPost
revision. Backend signs a 24-hour link bound to the selected workspace and the
exact saved Draft version; the public-facing Next route renders that version
with the canonical TypeScript compiler. If the Draft changes, the old link
stops instead of silently showing newer content. Generate, Regenerate, and
successful Draft edits send that link beside the authenticated web Draft
Edit URL, so a signed-in member can continue editing the same workspace. The
message explicitly notes that the authenticated web Draft Assistant uses an
independent session from the current Feishu conversation. When a member asks to
edit Materials or Draft on the web, the Feishu-only navigation plugin sends the
corresponding canonical authenticated editor route directly instead of asking
the model to reconstruct it. An explicit screenshot request
calls `wxpost_send_draft_preview_image`, opens the same link with Hermes'
bundled headless browser, and sends one compressed full-page image through the
native Feishu sender. It is read-only and never changes Materials, Draft, or
public revision state. Local Docker sets
`WXPOST_PREVIEW_BROWSER_BASE_URL=http://host.docker.internal:3000`; deployment
must set it to the externally reachable frontend origin.

Configure the stdio MCP server once in the dedicated SoarHigh Hermes home:

```bash
docker exec \
  --user hermes \
  --env HOME=/opt/data \
  --workdir /workspace \
  soarhigh-hermes \
  hermes mcp add soarhigh-wxpost \
    --command /opt/hermes/.venv/bin/python \
    --env \
      PYTHONPATH=/opt/soarhigh \
      WXPOST_WORKSPACE_ROOT=/workspace \
      'SOARHIGH_API_BASE_URL=${SOARHIGH_API_BASE_URL}' \
      'WXPOST_SERVICE_TOKEN=${WXPOST_SERVICE_TOKEN}' \
    --args -m wxpost_controller.mcp_server
```

The `${...}` values above are references, not copied secrets. Hermes resolves
them from the Gateway environment when it starts the filtered MCP subprocess.
Both references are required for `wxpost_save_draft` and `wxpost_edit_draft`:
the controller either assembles a complete canonical `ArticleDocument` from a
strict proposal or asks Backend to apply typed operations, then validates the
result before writing it.

Then verify discovery:

```bash
docker exec \
  --user hermes \
  --env HOME=/opt/data \
  soarhigh-hermes \
  hermes mcp test soarhigh-wxpost
```

The `controller` Compose service runs the HTTP adapter automatically, mounts
the same workspace at `/workspace`, and publishes it only on
`127.0.0.1:8787`. Local Backend uses that address by default and authenticates
with its existing `WXPOST_SERVICE_TOKEN`; no separate controller credential is
configured.

The Gateway's OpenAI-compatible Agent API is enabled on
`127.0.0.1:8642`. Backend uses it for the editable custom Voice & tone
instruction proposal and authenticates with that same existing token. The
controller remains deterministic and never invokes a model. No Hermes
credential is returned to the frontend.

Workspace manifests use schema version 4. Editorial settings include up to
three selected Voice & tone profiles. Custom profile names, instructions, and
selection state are workspace-local and persist only through Save Materials;
there is intentionally no parser or migration for cleared development
workspaces from older schema versions.

HTTP routes are:

```text
GET    /workspaces?page=1&page_size=10
POST   /workspaces
PATCH  /workspaces/{workspaceId}
DELETE /workspaces/{workspaceId}
GET    /workspaces/{workspaceId}/context
GET    /workspaces/{workspaceId}/draft/session
DELETE /workspaces/{workspaceId}/draft/session
POST   /workspaces/{workspaceId}/draft/save
POST   /workspaces/{workspaceId}/draft/generate
POST   /workspaces/{workspaceId}/draft/chat
PATCH  /workspaces/{workspaceId}/sources
POST   /workspaces/{workspaceId}/sources/{sourceId}/import
PUT    /workspaces/{workspaceId}/sources/{sourceId}/inclusion
GET    /workspaces/{workspaceId}/sources/{sourceId}/content
POST   /workspaces/{workspaceId}/uploads?filename=...
GET    /workspaces/{workspaceId}/sources/{sourceId}/delete-preflight
DELETE /workspaces/{workspaceId}/sources/{sourceId}
```

Workspace pages are ordered by `createdAt` descending so material edits do not
move cards, while each summary still exposes `updatedAt` for display.

The upload route accepts the source bytes as its body, the MIME type in
`Content-Type`, and the compare-and-swap version in
`X-Expected-Manifest-Version`.

Source deletion is dependency-safe. The preflight reports
`blockedByDraft: true` when the saved Draft still references the source, and
the delete route rejects the same condition even if it changes after
preflight. A member must remove the media block in Draft Edit, save the new
Draft version, and then delete the Materials file.

The HTTP controller is connected to the authoring page's Materials and Draft
stages. Draft contains both Edit and Preview modes; Generate and Chat resume a
workspace-scoped `hermes serve` session. Generate requires one version-checked
MCP save, while Chat may answer without saving or perform one verified focused
revision. The deterministic workspace core remains the only writer.

Entering `/new` in Draft Assistant and confirming atomically points the
workspace at a fresh conversation before retiring the previous persisted
Hermes session. The new session is created by Hermes only when its first
message is sent; refreshing before that message keeps the new conversation
empty. Draft, Materials, and workspace files are unaffected. Session pointers
also record the Draft protocol version so a future protocol bump retires an
incompatible conversation instead of resuming it by stored ID.

Hermes and the Controller own separate persistent databases. Hermes keeps the
conversation itself in the dedicated profile's `state.db`. The Controller
keeps only workspace-to-session pointers, retryable session deletions, and the
web UI's exact completed-step metadata in
`/workspace/.wxpost-controller/controller.sqlite3`. Completed steps are keyed
by the existing turn-specific Draft operation ID, not matched by reply text.
The Controller database uses WAL transactions and never copies chat messages
or Draft content. On first startup after this change it transactionally imports
the former `draft-sessions.json`, reconciles its legacy completed steps when
that Hermes history is next opened, then removes the JSON file.

The remaining implementation order preserves the existing plan. Phase 2 Slice
7A public synchronization is complete: Backend projects one saved Draft into
one stable public WxPost, uploads or reuses public OSS assets idempotently, and
exposes derived publication status to Draft and Workspaces.

1. **Phase 2, Slice 7B - Hermes image descriptions (complete):** the web
   Materials stage can ask Hermes for a selected image's English description,
   using the image and any current description as factual authority and linked
   meeting theme, introduction, and agenda as supporting context. The
   suggestion stays local until `Save Materials`, which confirms and persists
   it as an AI-authored description.
2. **Phase 2, Slice 7C - Draft Assistant and Controller hardening (complete):**
   use the managed fast WxPost profile, route general/read-only/editorial turns
   deliberately, expose and persist genuine tool milestones, support atomic
   `/new`, keep session metadata in Controller SQLite, and apply small Draft
   changes through typed version-bound operations without conflating Materials
   inclusion, Draft body media, or cover state.
3. **Phase 2, Slice 7D - conversational Feishu integration (complete):** keep
   the existing plain Feishu channel on the managed `wxpost` profile while
   exposing a Feishu-only workspace-navigation toolset. Members can list,
   select, and create workspaces, search linked meetings, import linked
   candidates or deduplicated Feishu attachments, manage Materials, and
   generate or edit typed Drafts. A read-only configuration report presents
   source, editorial settings, candidates/imported/Included/Draft media, cover,
   Draft version, and public status from canonical state. “素材库” means the
   complete catalog; candidates must be imported before Draft use. Feishu can
   display every catalog image natively and every video natively with a file
   fallback. Its dedicated image-description tool stages the same
   Controller-owned suggestion used by the web, then saves it only after a
   later explicit member confirmation. Controller SQLite owns active Feishu
   bindings and pending confirmations. Web and Feishu sessions remain
   separate, setup is immutable after creation, and public synchronization
   remains web-only.
4. **Phase 3 - WeChat Draft integration (Backend/Frontend complete; production
   fixed-egress gateway pending):**
   publish only from an authenticated Public Revision, upload WeChat media,
   replace rendered image URLs, submit the same canonical inline HTML,
   create/update one Draft idempotently, and verify platform readback plus the
   official mobile preview. Hermes has no role in this projection and cannot
   regenerate, rewrite, or re-layout content during publication. Production
   deployment will route only the WeChat API transport through a thin VPS
   gateway; Backend remains the sole projection orchestrator and database
   writer, while the gateway has no Draft, Revision, Supabase, or renderer
   authority.
5. **Phase 4 - optional hardening:** version history/rollback, simultaneous
   collaborative editing, analytics, bulk operations, shareable style presets,
   and Bitable.
