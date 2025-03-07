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
- **/meetings** - GET: List meetings (with filter by status), POST: Create a new meeting
- **/meetings/{id}** - GET: Retrieve meeting details
- **/meetings/{id}** - PUT: Update an existing meeting
- **/meetings/{id}/status** - PUT: Update meeting status (draft/published)
- **/meetings/{id}** - DELETE: Delete a meeting

### Awards Management
- **/meetings/{id}/awards** - GET: Retrieve awards for a specific meeting
- **/meetings/{id}/awards** - POST: Save awards for a specific meeting

## Data Models

### User Model
A simple model with:
- `uid`: User identifier
- `username`: Username
- `full_name`: User's full name

### Attendee Model
A model for meeting participants with:
- `id`: Attendee identifier
- `name`: Attendee's full name
- `type`: Type of attendee ("Member" or "Guest")
- `wxid`: Optional WeChat ID (if available)
- `cell`: Optional cell phone number
- `member_id`: Optional link to a member record (for member-type attendees)

### Meeting Model
A comprehensive model for Toastmasters meetings with:
- Basic meeting information: type, theme, manager, date, times, location
- Introduction text
- A list of meeting segments
- Status field ("draft" or "published")

### Meeting Segment Model
Detailed model for meeting agenda items with:
- Segment ID and type
- Start time, duration and end time
- Role taker (references an Attendee)
- Title and content
- Related segment IDs (as comma-separated string)

### Award Model
Model for meeting awards and recognitions:
- `meeting_id`: Reference to the associated meeting
- `category`: Award category name
- `winner`: Name of the award recipient

## Database Integration

- Uses Supabase client with service role key
- Comprehensive functions for meeting CRUD operations:
  - `create_meeting()`: Creates a new meeting (as draft by default)
  - `get_meetings()`: Retrieves meetings with filtering options
  - `get_meeting_by_id()`: Retrieves a specific meeting by ID
  - `update_meeting()`: Updates meeting details
  - `update_meeting_status()`: Updates meeting status (draft/published)
  - `delete_meeting()`: Deletes a meeting
- Functions for working with attendees and segments:
  - `resolve_attendee_id()`: Resolves member ID or custom name to an attendee ID
  - Functions to handle creating and retrieving attendee records
- Functions for awards management:
  - `get_awards_by_meeting()`: Retrieves awards for a specific meeting
  - `save_meeting_awards()`: Saves awards for a meeting

## Authentication System

- JWT-based authentication using Supabase JWT secret
- Token verification and current user extraction from JWT
- Protected routes using FastAPI dependency injection
- Optional user dependency for public/member-only content

## Development Status

### Completed Features
- Basic FastAPI application setup with CORS support
- Supabase integration for database operations
- JWT-based authentication
- Meeting, User, Attendee, and Award data models
- Meeting agenda image parsing using OpenAI
- Complete meeting CRUD functionality:
  - Creating meetings (as drafts by default)
  - Listing meetings with filtering by status
  - Retrieving meeting details
  - Updating meeting information
  - Changing meeting status (draft/published)
  - Deleting meetings
- Access control for meetings:
  - Draft meetings visible only to members
  - Published meetings visible to all users
  - Meeting creation/editing limited to members
- Attendee management:
  - Support for both members and guests as attendees
  - Automatic resolution of attendee references
- Awards management:
  - Retrieving awards associated with meetings
  - Saving and updating meeting awards
  - Support for various award categories

### Current Implementation Details

The backend now fully supports the meeting management workflow:

1. **Meeting Creation**:
   - Members can create new meetings which are saved as drafts by default
   - Meetings can be created from scratch or from parsed agenda images

2. **Meeting Listing**:
   - Members can see all meetings (both draft and published)
   - Non-members can only see published meetings
   - Optional filtering by status

3. **Meeting Details**:
   - Detailed meeting information retrieval with segments
   - Access control based on meeting status and user authentication

4. **Meeting Updates**:
   - Full meeting information updates
   - Dedicated endpoint for status changes (draft/published)
   - Access control to ensure only members can update

5. **Meeting Deletion**:
   - Members can delete meetings they manage
   - Administrators have broader deletion rights
   - Row-level security enforced at the database level

All these features are now fully integrated with the Supabase database, with proper error handling and status codes for API responses.
