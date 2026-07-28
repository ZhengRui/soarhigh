# Hermes container

This directory runs the Hermes Gateway in the official Hermes Agent container.
It keeps Hermes state and article working files in two separate host
directories:

| Host setting           | Container path | Purpose                                                                 |
| ---------------------- | -------------- | ----------------------------------------------------------------------- |
| `HERMES_HOME_DIR`      | `/opt/data`    | Configuration, credentials, memory, sessions, skills, and gateway state |
| `HERMES_WORKSPACE_DIR` | `/workspace`   | WXPost article workspaces and their local source files                  |

The Compose file mounts only the small `wxpost_controller` package read-only at
`/opt/soarhigh/wxpost_controller`. The rest of the SoarHigh repository, the
complete host home directory, Docker socket, SSH credentials, and Git
credentials are not mounted into the container.

## First startup

The first interactive `up` asks for the Hermes home, workspace, image, and
container name:

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
configuration, and delegates to Docker Compose. Only the first interactive
`up` starts the configuration prompt; the other commands never create
configuration.

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

## WXPost workspace controller

The tracked `wxpost_controller` package is the shared boundary for one
canonical WXPost authoring workspace. Its MCP surface implements the complete
material-controller and draft operations:

```text
wxpost_get_context
wxpost_bootstrap_workspace
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

`contracts.py` defines the single supported `source-manifest v2` shape plus the
operation inputs. A complete manifest example lives at
`tests/fixtures/source-manifest-v2.json`. Important invariants include:

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
- workspace bootstrap registers current meeting media without downloading it;
  a later refresh appends newly discovered `fileKey` values but never renumbers
  or silently removes an existing source;
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
workspace-ready file and declared size, uses a per-workspace file lock and
operation-specific expected version, validates stored and incoming data, and
writes by atomic replacement. A short-lived pending record makes the two-file
draft/manifest update recoverable if the process stops between the two atomic
replacements.

Linked workspaces read `/meetings/{meetingId}/media` from
`SOARHIGH_API_BASE_URL`. Set the same non-empty `WXPOST_SERVICE_TOKEN` in the
backend and Hermes environments when draft-meeting media must be visible. The
token is sent only to the SoarHigh media-list endpoint, never to an asset URL.

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

Run the HTTP adapter on the host against the same host workspace mount. It
binds to loopback and requires a bearer token:

```bash
PYTHONPATH=claws/hermes \
WXPOST_WORKSPACE_ROOT=/absolute/path/to/hermes-workspace \
WXPOST_CONTROLLER_TOKEN=replace-with-a-local-secret \
backend/.venv/bin/python -m wxpost_controller.http_server
```

HTTP routes are:

```text
PUT    /workspaces/{workspaceId}
GET    /workspaces/{workspaceId}/context
PATCH  /workspaces/{workspaceId}/sources
POST   /workspaces/{workspaceId}/sources/{sourceId}/import
PUT    /workspaces/{workspaceId}/sources/{sourceId}/inclusion
POST   /workspaces/{workspaceId}/uploads?filename=...
GET    /workspaces/{workspaceId}/sources/{sourceId}/delete-preflight
DELETE /workspaces/{workspaceId}/sources/{sourceId}
```

The upload route accepts the source bytes as its body, the MIME type in
`Content-Type`, and the compare-and-swap version in
`X-Expected-Manifest-Version`.

The controller is not yet connected to the authoring page and does not implement
public-preview synchronization, Supabase writes, OSS uploads, or WeChat draft
operations.
