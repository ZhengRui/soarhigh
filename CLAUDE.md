# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SoarHigh Toastmasters Club - A full-stack web application for managing Toastmasters club meetings, awards, posts, and voting systems.

## Tech Stack

- **Frontend**: Next.js 15 (App Router), TypeScript, Tailwind CSS, React Query, Jotai
- **Backend**: FastAPI, SQLAlchemy, Supabase, Python 3.12+
- **Database**: Supabase (PostgreSQL)
- **AI Agents**: Pydantic AI (Gemini 3.x / DeepSeek V4 / OpenAI), SSE streaming
- **Deployment**: Vercel (both frontend and backend)

## Development Commands

### Frontend (Next.js)
- `bun run dev` - Start development server at http://localhost:3000
- `bun run build` - Build for production
- `bun run start` - Start production server
- `bun run lint` - Run ESLint
- `bun run prettier` - Format code with Prettier

### Backend (FastAPI)
- `uv run python main.py` - Start development server at http://localhost:5000
- `uv run ruff check .` - Run linter
- `uv run ruff format .` - Format code
- `uv run pytest` - Run tests

## Project Structure

### Frontend (`/frontend`)
- `src/app/` - Next.js app router pages
  - `(auth)/` - Protected routes (meetings, posts, awards)
  - `signin/` - Authentication
  - `meetings/` - Meeting management and display
  - `posts/` - Blog posts
  - `vote/` - Voting system
- `src/components/` - Reusable components
  - `ChatPanel/` - Floating AI assistant launcher + unified chat panel (SSE consumer, markdown render, tool-call badges)
- `src/hooks/` - Custom React hooks
- `src/utils/` - Utility functions
- `src/interfaces.ts` - TypeScript interfaces

### Backend (`/backend`)
- `app/api/serv.py` - FastAPI application entry point
- `app/api/routes/` - API route handlers (auth, meeting, post, stats, timing, checkin, feedback)
  - `agents/` - Agent endpoints (`unified.py` router, `meeting.py`, `statistics.py`, `_shared.py` helpers)
- `app/agents/` - Pydantic AI agent implementations
  - `runtime/` - Shared contracts, history utils, model settings, tool policy, persistent session/turn store
  - `router/` - LLM-backed turn classifier (route to specialist / direct_answer / clarify / refuse)
  - `meeting/` - Meeting agent (agenda edit + create-from-{text,image,template,clone} + save_draft)
  - `statistics/` - Read-only analytics agent (attendance/role/manager/award matrices, lookups)
- `app/services/` - Cross-agent shared services (`meeting_lookup`, `meeting_stats`, `meeting_preview_markdown`, `member_directory`)
- `app/models/` - Pydantic models (incl. `models/agents/` request/response shapes)
- `app/db/` - Database configuration
  - `core.py` - Core database operations
  - `stats.py` - Dashboard statistics queries
- `app/utils/` - Utility functions
- `supabase_migrations/` - Forward-only SQL migrations (apply manually via Supabase dashboard)

## Key Features

### Core Functionality
- **Meeting Management**: Create, edit, and manage Toastmasters meetings with agendas
- **Dashboard**: Member attendance charts, meeting statistics, and role participation matrix
- **Awards System**: Track and assign awards for different categories
- **Voting System**: Allow members and guests to vote for awards with real-time counting
- **Posts/Blog**: Create and manage markdown-based blog posts with visibility controls
- **Media Management**: Upload and manage meeting media (photos, documents) via AliCloud OSS
- **Authentication**: JWT-based authentication with Supabase

### Advanced Features
- **AI-Powered Meeting Creation**: Parse agenda images and create meetings from text using OpenAI GPT-4o
- **AI Assistant (Multi-Agent Chat)**: Floating chat panel powered by a manager-router + meeting/statistics specialists (Pydantic AI). Supports natural-language agenda editing on the meeting form, historical stats lookups, image-attached create-from-image, and persisted multi-turn sessions. Members-only.
- **Meeting Templates**: Pre-defined templates (Regular, Workshop, Custom) for quick meeting creation
- **Workbook Generation**: Generate Excel-compatible meeting workbooks with proper formatting
- **Role Management**: Support for both members and guests as meeting attendees
- **Access Control**: Different visibility levels for members vs. non-members
- **Real-time Interactions**: Live vote counting and status updates

## API Endpoints

### Authentication
- `/whoami` - Retrieve current authenticated user information
- `/members` - Retrieve all club members (requires authentication)

### Meeting Management
- `/meeting/parse_agenda_image` - Parse meeting agenda from uploaded image (OpenAI GPT-4o)
- `/meeting/plan_from_text` - Plan meeting from textual description (OpenAI API)
- `/meetings` - GET: List meetings (with filter by status), POST: Create new meeting
- `/meetings/{id}` - GET: Retrieve meeting details, PUT: Update meeting, DELETE: Delete meeting
- `/meetings/{id}/status` - PUT: Update meeting status (draft/published)

### Awards Management
- `/meetings/{id}/awards` - GET: Retrieve awards, POST: Save awards for specific meeting

### Media Management
- `/meetings/{id}/media` - GET: List media files, DELETE: Delete media files
- `/meetings/{id}/media/get-upload-url` - POST: Get pre-signed URLs for AliCloud OSS uploads

### Voting Management
- `/meetings/{id}/votes` - GET: Retrieve votes, POST: Cast votes
- `/meetings/{id}/votes/increment` - POST: Increment vote counts (atomic)
- `/meetings/{id}/votes/status` - GET: Get voting status, PUT: Update voting status (open/close)

### Feedback Management
- `/meetings/{id}/feedbacks` - GET: Retrieve feedbacks with access control, POST: Create feedback
- `/meetings/{id}/feedbacks/{feedback_id}` - PUT: Update feedback, DELETE: Delete feedback
- `/meetings/{id}/feedbacks/experiences` - POST: Create experience curve feedbacks (batch operation)

### Checkin Management
- `/meetings/{id}/checkins` - GET: Retrieve checkins (members see all, non-members see own), POST: Create/update checkins for segments
  - Supports `referral_source` field to track how attendees heard about the meeting
  - Checkins are automatically deleted when the parent meeting is deleted (cascade)
- `/meetings/{id}/checkins/reset` - POST: Reset a segment's checkin (members only, for releasing Timer role)

### Blog Post Management
- `/posts` - GET: List posts with pagination, POST: Create new post
- `/posts/{slug}` - GET: Retrieve post by slug, PATCH: Update post, DELETE: Delete post

### Dashboard Statistics
- `/stats/dashboard` - GET: Retrieve dashboard statistics (member attendance, meeting attendance) for date range

### Agent Endpoints (SSE streaming, members only)
- `/agent/turn` - POST (multipart: `payload` JSON + optional `image`): Unified entry. Loads session history, runs the LLM router, then either replies directly (clarify/refuse/direct_answer) or dispatches to a specialist. Image attachments skip the router and go straight to the meeting agent's `create_from_image` tool.
- `/meeting-agent/turn` - POST: Meeting specialist turn (agenda edit / create / save_draft). Requires `agenda_snapshot`. Tool calls and final text streamed as SSE events.
- `/meeting-agent/revert` - POST: Roll session state back to a prior turn (undo last assistant action).
- `/statistics-agent/turn` - POST: Read-only stats specialist turn (attendance/role/manager/award matrices, member/meeting lookups).

All agent endpoints reject unbound WeChat sessions — `_shared.require_member` mandates a bound club member account; foreign session_ids 404 transparently.

- `/docs` - FastAPI documentation
- `/static/*` - Static file serving

## Database Schema

The application uses Supabase with tables for:
- **Users** (authentication with JWT-based auth)
- **Attendees** (meeting participants - members and guests)
- **Meetings** (with segments, roles, status: draft/published)
- **Posts** (blog content with public/private visibility)
- **Awards** (meeting awards with categories)
- **Votes** (voting records with atomic counting)
- **Media** (file uploads via AliCloud OSS)
- **Vote Status** (voting session management)
- **Feedbacks** (meeting feedback with experience curve methodology)
- **Checkins** (meeting participation tracking by segment)
- **agent_sessions / agent_turns** (unified per-user agent chat history; one row per turn carries `agent_kind`, `router_decision` JSONB, and the Pydantic AI message_history cursor)

## Frontend Routes

### Public Routes
- `/` - Landing page with club introduction
- `/signin` - Authentication page
- `/meetings` - Public meeting listing (published only for non-members)
- `/posts` - Public posts listing (published content)
- `/posts/[slug]` - Individual post detail page
- `/meetings/workbook/[id]` - Meeting agenda workbook preview

### Protected Routes (requires authentication)
- `/dashboard` - Dashboard with attendance charts and role participation matrix
- `/meetings/new` - Create new meetings (template, image, or text-based)
- `/meetings/edit/[id]` - Edit existing meetings
- `/posts/new` - Create new blog posts
- `/posts/edit/[slug]` - Edit existing posts
- `/awards` - Awards management
- `/votes` - Voting management

## Environment Setup

### Frontend (`.env.local`)
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`

### Backend (environment variables)
- Supabase configuration (service role key, JWT secret)
- `WECHAT_JWT_SECRET` - Validates miniapp wechat_session JWTs (agent endpoints accept these for bound members)
- OpenAI API key (for legacy `/meeting/parse_agenda_image` + text planner)
- AliCloud OSS credentials (media storage)
- Agent models / providers:
  - `MEETING_AGENT_MODEL`, `ROUTER_AGENT_MODEL`, `STATISTICS_AGENT_MODEL` - Pydantic AI model strings (default `google-gla:gemini-3.1-flash-lite-preview`; DeepSeek V4 via `deepseek:deepseek-chat`)
  - `MEETING_THINKING_LEVEL`, `ROUTER_THINKING_LEVEL`, `STATISTICS_THINKING_LEVEL` - Per-agent reasoning effort (mapped to provider knob in `agents/runtime/model_settings.py`)
  - `GOOGLE_API_KEY` (or `GEMINI_API_KEY`) - Gemini provider
  - `DEEPSEEK_API_KEY` - DeepSeek provider; bridged into `os.environ` for pydantic-ai
  - `MEETING_TEXT_PLANNER_MODEL`, `MEETING_TEXT_PLANNER_REASONING_EFFORT` - Inner model used by `/meeting/plan_from_text`

## Additional Notes

### AI Integration
- **OpenAI GPT-4o** integration for parsing meeting agenda images and creating meetings from text descriptions
- **Pydantic AI Multi-Agent System**: Three independently-tunable agents share a unified `agent_sessions`/`agent_turns` history and SSE event protocol.
  - **Router** (`agents/router/`): Tiny structured-output classifier with no tools; sees prior history, picks `specialist_meeting` / `specialist_statistics` / `direct_answer` / `clarify`. Skipped when an image is attached.
  - **Meeting agent** (`agents/meeting/`): ~25 tools covering set_role/title/content, segment add/remove/move/swap, time shift, validators, create-from-{text,image,template,clone}, preview, save_draft (two-turn confirm with time-gate), and revert. Tool policy enforced at the route layer.
  - **Statistics agent** (`agents/statistics/`): Read-only matrices over historical meetings (member attendance, role participation, manager assignments, award counts) plus member/meeting lookups.
  - Cross-specialist flows are emergent: each turn is classified independently; both specialists load the same `session_id` history, so the meeting agent on a follow-up turn naturally sees the stats agent's prior tool calls.
- **AliCloud OSS** integration for media storage with pre-signed URLs for secure uploads
- **Database snapshots**: `.github/workflows/db-snapshot.yml` performs a weekly `pg_dump` of the public schema to AliCloud OSS; `backend/scripts/restore-db.sh` restores from a downloaded dump.

### Access Control
- **Members**: Can access all meetings (draft/published), create/edit content, manage awards, control voting, and use the AI assistant
- **Non-members**: Can only view published meetings and posts, cast votes in open sessions; agent endpoints reject unbound WeChat sessions
- **Draft/Published Status**: Controls visibility of meetings and posts
- **Agent sessions**: `agent_sessions.user_id` is checked against the caller before any model runs; foreign session_ids fail closed without leaking existence

### Development Workflow
- Backend runs on port 5000, Frontend on port 3000
- Both services use Vercel for deployment
- Database operations use Supabase service role key for backend
- Media files are stored in AliCloud OSS with proper access controls

### Git Commits
- **Never commit directly after implementing code changes** - always wait for the user to test first
- Before committing, activate the backend venv for pre-commit hooks:
```bash
cd backend && source .venv/bin/activate && cd .. && git add ... && git commit ...
```

### Testing Changes
- **Frontend**: Use `bun run lint` to check for errors. Do NOT use `bun run build` as it will interfere with the user's running dev server.
- **Backend**: Use `uv run ruff check .` to check for errors.