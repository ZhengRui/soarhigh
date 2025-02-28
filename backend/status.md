# SoarHigh Toastmasters Club - Backend Status

## Architecture Overview

This backend application serves as the API for the SoarHigh Toastmasters Club platform. It's built with FastAPI and uses Supabase as the database backend, with JWT-based authentication.

## Technology Stack

- **Framework**: FastAPI
- **Database**: Supabase
- **Authentication**: JWT-based authentication via Supabase
- **AI Services**: OpenAI API (GPT-4o) for meeting agenda image parsing
- **Runtime**: Python with uvicorn server

## API Endpoints

### Authentication
- **/whoami** - Endpoint to retrieve current authenticated user information
- **/members** - Endpoint to retrieve all club members (requires authentication)

### Meeting Management
- **/meeting/parse_agenda_image** - Endpoint to parse a meeting agenda from an uploaded image using OpenAI's GPT-4o model

## Data Models

### User Model
A simple model with:
- `uid`: User identifier
- `username`: Username
- `full_name`: User's full name

### Meeting Model
A comprehensive model for Toastmasters meetings with:
- Basic meeting information: type, theme, manager, date, times, location
- Introduction text
- A list of meeting segments

### Meeting Segment Model
Detailed model for meeting agenda items with:
- Segment ID and type
- Start time, duration and end time
- Role taker
- Title and content
- Related segment IDs (as comma-separated string)

## Database Integration

- Uses Supabase client with service role key
- Currently only has a `get_members()` function to retrieve club members
- No functions for creating, reading, updating, or deleting meetings

## Authentication System

- JWT-based authentication using Supabase JWT secret
- Token verification and current user extraction from JWT
- Protected routes using FastAPI dependency injection

## Development Status

### Completed Features
- Basic FastAPI application setup with CORS support
- Supabase integration for database operations
- JWT-based authentication
- Meeting and User data models
- Meeting agenda image parsing using OpenAI

### Missing Functionality for Meeting Management
1. **No CRUD Operations for Meetings**:
   - No endpoints to create, read, update, or delete meetings
   - No database functions for meeting storage or retrieval

2. **No Draft/Published Status**:
   - The Meeting model doesn't include a status field for draft/published state
   - No endpoints to change meeting status

3. **No Meeting Listing**:
   - No endpoint to list all meetings or filter by status
   - No functionality to show different meetings to members vs. non-members

## Development Required for Meeting Management

To implement the meeting save/draft/publish functionality as described in the frontend status document, we need to:

1. **Update Meeting Model**:
   - Add `status` field to Meeting model (values: "draft", "published")
   - Add `created_by`, `created_at`, `updated_at` fields for tracking

2. **Add Database Functions**:
   - Create functions to store meetings in Supabase
   - Add functions to retrieve meetings with filtering options
   - Create functions to update meeting details and status

3. **Add New API Endpoints**:
   - `POST /meetings` - Create a new meeting (as draft)
   - `GET /meetings` - List meetings (with filtering)
   - `GET /meetings/{id}` - Get meeting details
   - `PUT /meetings/{id}` - Update meeting
   - `PUT /meetings/{id}/status` - Update meeting status (or include in general update)

4. **Implement Access Control**:
   - Add logic to filter meetings based on member status and meeting status
   - Ensure draft meetings are only visible to members
   - Allow only members to create/edit meetings

## API Development Plan

1. **Phase 1: Model Updates**
   - Update Meeting model with status and tracking fields
   - Create database schema for meetings in Supabase

2. **Phase 2: Core CRUD Functionality**
   - Implement database functions for meeting operations
   - Add basic CRUD endpoints for meetings

3. **Phase 3: Status Management**
   - Add specific functionality for handling draft/published status
   - Implement visibility rules based on user role

4. **Phase 4: Advanced Features**
   - Add filtering, pagination for meeting lists
   - Implement any additional features needed for the frontend

The current backend implementation provides a solid foundation with authentication and data models but requires significant additions to support the complete meeting management functionality described in the frontend requirements.
