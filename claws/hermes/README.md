# Hermes container

This directory runs the Hermes Gateway in the official Hermes Agent container.
It keeps Hermes state and article working files in two separate host
directories:

| Host setting           | Container path | Purpose                                                                 |
| ---------------------- | -------------- | ----------------------------------------------------------------------- |
| `HERMES_HOME_DIR`      | `/opt/data`    | Configuration, credentials, memory, sessions, skills, and gateway state |
| `HERMES_WORKSPACE_DIR` | `/workspace`   | WXPost sources, working files, and exports                              |

The SoarHigh repository, host home directory, Docker socket, SSH credentials,
and Git credentials are not mounted into the container.

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
