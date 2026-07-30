# Hermes container

This directory runs the Hermes Gateway and WxPost HTTP controller as two
services in one Compose project. The Gateway also exposes Hermes's authenticated
Agent API for focused editorial suggestions. Hermes state and article working
files remain in two separate host directories:

| Host setting           | Container path | Purpose                                                                 |
| ---------------------- | -------------- | ----------------------------------------------------------------------- |
| `HERMES_HOME_DIR`      | `/opt/data`    | Configuration, credentials, memory, sessions, skills, and gateway state |
| `HERMES_WORKSPACE_DIR` | `/workspace`   | WxPost article workspaces and their local source files                  |

The Compose file mounts only the small `wxpost_controller` package read-only at
`/opt/soarhigh/wxpost_controller`. The rest of the SoarHigh repository, the
complete host home directory, Docker socket, SSH credentials, and Git
credentials are not mounted into the container.

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
canonical WxPost authoring workspace. Its MCP surface implements the complete
material-controller and draft operations:

```text
wxpost_get_context
wxpost_bootstrap_workspace
wxpost_update_workspace
wxpost_import_source
wxpost_set_source_included
wxpost_upload_source
wxpost_update_sources
wxpost_delete_source_preflight
wxpost_delete_source
wxpost_save_draft
```

The HTTP and MCP servers are thin adapters over the same controller core and
return the same error and version-conflict details. HTTP exposes the material
operations needed by the authoring page; MCP exposes those same operations plus
draft saves for Hermes.

`contracts.py` defines the single supported `source-manifest v4` shape plus the
operation inputs. A complete manifest example lives at
`tests/fixtures/source-manifest-v4.json`. Important invariants include:

- each collected source receives the next workspace-local material ID
  (`M01`, `M02`, and so on) when it enters the manifest; the ID is persisted,
  never recalculated from source order, and never reused after deletion;
  `nextMaterialNumber` persists that high-water mark;
- meeting-library provenance keeps the backend `fileKey`, while the local file
  path is derived as `sources/{sourceId}{originalSuffix}`;
- generated `ArticleDocument.media` keeps the same material IDs so its body and
  cover references point back to the corresponding manifest sources; saved
  media inclusion, order, and description provenance must match that manifest
  snapshot, while editorial media wording may be refined for the article;
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
- source array position is the only stored material order; `moveToIndex` moves
  one source and shifts the surrounding entries without persisting a duplicate
  `order` field;
- material changes advance only `manifestVersion`;
- every Materials mutation, including form saves, import, upload, and delete,
  requires the current `manifestVersion`; a stale operation changes nothing and
  returns a version conflict for the user to resolve;
- delete preflight reports references in the latest saved draft; deleting a
  referenced source requires explicit confirmation, direct uploads lose their
  manifest record, and meeting-library sources retain their `fileKey` so they
  can be imported again;
- `draft/article.json` is always the raw canonical `ArticleDocument`;
- draft version, source-manifest version, and hash live in the manifest,
  outside the article document;
- draft saves use the backend-owned `/posts/wxposts/validate` endpoint instead
  of maintaining a second ArticleDocument validator in the controller; the
  normalized document returned by that endpoint is the one stored on disk;
- draft saves require both expected manifest and draft versions, and every
  article media ID and kind must match the manifest snapshot being saved.

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
The same value is also mapped to the Gateway's `API_SERVER_KEY`; it is sent
only from Backend to the controller or Hermes, never to the browser or an asset
URL.

Configure the stdio MCP server once in the dedicated SoarHigh Hermes home:

```bash
docker exec \
  --user hermes \
  --env HOME=/opt/data \
  --workdir /workspace \
  soarhigh-hermes \
  hermes mcp add soarhigh-wxpost \
    --command /opt/hermes/.venv/bin/python \
    --env PYTHONPATH=/opt/soarhigh WXPOST_WORKSPACE_ROOT=/workspace \
    --args -m wxpost_controller.mcp_server
```

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
PUT    /workspaces/{workspaceId}
PATCH  /workspaces/{workspaceId}
DELETE /workspaces/{workspaceId}
GET    /workspaces/{workspaceId}/context
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

The HTTP controller is connected to the authoring page's Materials stage. It
does not implement later public-preview synchronization, Supabase writes, OSS
uploads, or WeChat draft operations.
