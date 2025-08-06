# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SoarHigh Toastmasters Club - A full-stack web application for managing Toastmasters club meetings, awards, posts, and voting systems.

## Tech Stack

- **Frontend**: Next.js 15 (App Router), TypeScript, Tailwind CSS, React Query, Jotai
- **Backend**: FastAPI, SQLAlchemy, Supabase, Python 3.12+
- **Database**: Supabase (PostgreSQL)
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
- `src/hooks/` - Custom React hooks
- `src/utils/` - Utility functions
- `src/interfaces.ts` - TypeScript interfaces

### Backend (`/backend`)
- `app/api/serv.py` - FastAPI application entry point
- `app/api/routes/` - API route handlers (auth, meeting, post)
- `app/models/` - Pydantic models
- `app/db/` - Database configuration
- `app/utils/` - Utility functions

## Key Features

### Core Functionality
- **Meeting Management**: Create, edit, and manage Toastmasters meetings with agendas
- **Awards System**: Track and assign awards for different categories
- **Voting System**: Allow members and guests to vote for awards with real-time counting
- **Posts/Blog**: Create and manage markdown-based blog posts with visibility controls
- **Media Management**: Upload and manage meeting media (photos, documents) via AliCloud OSS
- **Authentication**: JWT-based authentication with Supabase

### Advanced Features
- **AI-Powered Meeting Creation**: Parse agenda images and create meetings from text using OpenAI GPT-4o
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

### Blog Post Management
- `/posts` - GET: List posts with pagination, POST: Create new post
- `/posts/{slug}` - GET: Retrieve post by slug, PATCH: Update post, DELETE: Delete post

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

## Frontend Routes

### Public Routes
- `/` - Landing page with club introduction
- `/signin` - Authentication page
- `/meetings` - Public meeting listing (published only for non-members)
- `/posts` - Public posts listing (published content)
- `/posts/[slug]` - Individual post detail page
- `/meetings/workbook/[id]` - Meeting agenda workbook preview

### Protected Routes (requires authentication)
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
- Supabase configuration (service role key)
- JWT secret for token verification
- OpenAI API key (for AI-powered features)
- AliCloud OSS credentials (media storage)

## Additional Notes

### AI Integration
- **OpenAI GPT-4o** integration for parsing meeting agenda images and creating meetings from text descriptions
- **AliCloud OSS** integration for media storage with pre-signed URLs for secure uploads

### Access Control
- **Members**: Can access all meetings (draft/published), create/edit content, manage awards, and control voting
- **Non-members**: Can only view published meetings and posts, cast votes in open sessions
- **Draft/Published Status**: Controls visibility of meetings and posts

### Development Workflow
- Backend runs on port 5000, Frontend on port 3000
- Both services use Vercel for deployment
- Database operations use Supabase service role key for backend
- Media files are stored in AliCloud OSS with proper access controls