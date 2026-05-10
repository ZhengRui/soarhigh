---
name: supabase-migration-workflow
description: Project-specific workflow for safely managing SoarHigh Supabase migrations with the Supabase CLI. Use when asked to link Supabase projects, migrate backend/supabase_migrations into backend/supabase/migrations, repair migration history, dry-run or apply database migrations, verify backup/dev/production Supabase targets, or diagnose mismatches between the running backend env and the linked Supabase project.
---

# Supabase Migration Workflow

## Project Shape

Treat `backend/` as the Supabase CLI project root, not the repository root.

Expected layout:

```text
backend/supabase/config.toml
backend/supabase/.temp/project-ref
backend/supabase/migrations/*.sql
```

Legacy migrations may still appear as deleted/renamed files from:

```text
backend/supabase_migrations/
```

Use `supabase` commands from `backend/`, or pass `--workdir backend`.

## Safety Rules

Never run `supabase db push` before `supabase db push --dry-run`.

Before any command that writes remote state, state the exact target project ref and the intended effect:

- `supabase link` changes local CLI target.
- `supabase migration repair` writes Supabase migration history metadata but does not execute migration SQL.
- `supabase db push` executes pending migration SQL against the linked database.

Do not repair a migration version unless the corresponding schema change is already known to exist in that database. When unsure, stop and inspect first.

Do not infer the running backend database from a fresh shell's default `.env`. For this project, `python main.py --backup` sets `ENV_FILE=.env.bak`. Verify the running process command and environment when the user says the server is already running.

## Standard Flow

1. Confirm the CLI project root:

```bash
cd backend
test -f supabase/config.toml
cat supabase/.temp/project-ref
```

2. Confirm the intended Supabase project:

```bash
supabase projects list
supabase link --project-ref <project-ref>
cat supabase/.temp/project-ref
```

3. Inspect migration state:

```bash
supabase migration list
```

4. If historical migrations were manually applied but are missing from remote history, repair only those historical versions:

```bash
supabase migration repair --status applied \
  20260424000000 \
  20260427000000 \
  20260429000000 \
  20260430000000 \
  20260430010000 \
  20260430020000 \
  20260430030000
```

5. Dry-run:

```bash
supabase db push --dry-run
```

Proceed only if the dry-run output lists exactly the intended pending migration(s).

6. Apply:

```bash
supabase db push
```

7. Verify:

```bash
supabase migration list
supabase db push --dry-run
```

The second command should report that the remote database is up to date.

## This Project's Known Migration Versions

Use unique 14-digit versions. The old `20260430_*.sql` files must not keep duplicate 8-digit versions.

```text
20260424000000_meeting_agent_tables.sql
20260427000000_statistics_agent_tables.sql
20260429000000_agent_router_decisions.sql
20260430000000_agent_unified_turns.sql
20260430010000_unify_agent_history.sql
20260430020000_drop_agent_router_decisions.sql
20260430030000_drop_agent_turns_specialist_seq.sql
20260510000000_agent_public_tables.sql
```

For the Public Agent migration, expected new objects are:

```text
public.agent_sessions_public
public.agent_turns_public
public.agent_rate_limits_public
public.increment_agent_rate_limit_public(...)
```

## Backend Environment Verification

To confirm a running local backend's database target:

```bash
lsof -nP -iTCP -sTCP:LISTEN | rg 'python|5000'
ps eww -p <pid> -o pid,ppid,command
lsof -a -p <pid> -d cwd
```

Look for:

```text
python main.py --backup
ENV_FILE=.env.bak
PWD=/.../backend
```

Then verify the app config with the same env file:

```bash
ENV_FILE=.env.bak .venv/bin/python -c "from app.config import SUPABASE_URL; print(SUPABASE_URL)"
```

To verify PostgREST sees the new Public Agent tables:

```bash
ENV_FILE=.env.bak .venv/bin/python -c "from app.db.supabase import supabase; tables=['agent_sessions_public','agent_turns_public','agent_rate_limits_public'];\
for t in tables:\
    res=supabase.table(t).select('*').limit(1).execute(); print(t, 'ok', len(res.data or []))"
```

If the same command without `ENV_FILE=.env.bak` points to another Supabase URL, that only verifies the default environment, not the running backup server.

## Production Guidance

For production, do not assume the backup project's repaired history applies.

Run:

```bash
cd backend
supabase link --project-ref <production-project-ref>
supabase migration list
supabase db push --dry-run
```

If dry-run lists old historical migrations that were manually applied in production, repair only those already-applied versions, then dry-run again. Apply only when the dry-run lists exactly the intended new migration.

## Common Pitfalls

- `supabase db dump` may require Docker locally; failure to dump does not mean migration failed.
- PostgREST schema cache can lag briefly, but a persistent `PGRST205` usually means the app is querying a different Supabase project or env file.
- Supabase CLI login role errors can be transient; rerun the exact read-only command before changing approach.
- `supabase db execute` is not available in Supabase CLI `2.72.7`; use `db push` for migrations or `psql`/Dashboard SQL Editor for direct SQL execution.
