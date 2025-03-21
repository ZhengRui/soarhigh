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
- **/meeting/plan_from_text** - Endpoint to plan a meeting from textual description using OpenAI's API
- **/meetings** - GET: List meetings (with filter by status), POST: Create a new meeting
- **/meetings/{id}** - GET: Retrieve meeting details
- **/meetings/{id}** - PUT: Update an existing meeting
- **/meetings/{id}/status** - PUT: Update meeting status (draft/published)
- **/meetings/{id}** - DELETE: Delete a meeting

### Awards Management
- **/meetings/{id}/awards** - GET: Retrieve awards for a specific meeting
- **/meetings/{id}/awards** - POST: Save awards for a specific meeting

### Voting Management
- **/meetings/{id}/votes** - GET: Retrieve votes for a specific meeting
- **/meetings/{id}/votes** - POST: Cast votes for a specific meeting
- **/meetings/{id}/votes/increment** - POST: Increment vote counts atomically
- **/meetings/{id}/votes/status** - GET: Get voting status (open/closed) for a meeting
- **/meetings/{id}/votes/status** - PUT: Update voting status (open/close voting)

### Blog Post Management
- **/posts** - GET: List posts with pagination, POST: Create a new post
- **/posts/{slug}** - GET: Retrieve a post by slug, PATCH: Update an existing post, DELETE: Delete a post

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

### Vote Model
Model for tracking votes at meetings:
- `meeting_id`: Reference to the associated meeting
- `category`: Vote category (e.g., "Best Speaker", "Best Table Topics")
- `name`: Name of the person being voted for
- `segment`: Optional reference to a specific meeting segment
- `count`: Number of votes received

### Vote Status Model
Model for tracking voting status:
- `meeting_id`: Reference to the associated meeting
- `open`: Boolean indicating if voting is open or closed

### Post Model
Model for blog posts:
- `id`: Post identifier
- `title`: Post title
- `slug`: URL-friendly identifier
- `content`: Markdown content of the post
- `is_public`: Boolean indicating if post is publicly viewable
- `created_at`: Timestamp of post creation
- `updated_at`: Timestamp of last update
- `author`: Information about the post author (name and member_id)

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
- Functions for voting management:
  - `get_votes_by_meeting()`: Retrieves votes for a specific meeting
  - `cast_votes()`: Records votes for a meeting
  - `increment_votes()`: Atomically increments vote counts
  - `get_vote_status()`: Gets the current voting status for a meeting
  - `update_vote_status()`: Updates the voting status (open/close)
- Functions for blog post management:
  - `get_posts()`: Retrieves posts with pagination and filtering
  - `get_post_by_slug()`: Retrieves a specific post by slug
  - `create_post()`: Creates a new blog post
  - `update_post()`: Updates post details
  - `delete_post()`: Deletes a post

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
- Meeting, User, Attendee, Award, and Post data models
- Meeting agenda image parsing using OpenAI
- Meeting planning from text description using OpenAI
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
- Voting system:
  - Category-based voting for meetings
  - Vote counting with atomic operations
  - Voting status management (open/close)
  - Different permission levels for members and non-members
  - Real-time vote tracking
- Blog post management:
  - Creating new posts (members only)
  - Listing posts with pagination
  - Retrieving individual posts by slug
  - Updating existing posts (members only)
  - Deleting posts (members only)
  - Access control for posts (public/private visibility)

### Current Implementation Details

The backend now fully supports the meeting management workflow:

1. **Meeting Creation**:
   - Members can create new meetings which are saved as drafts by default
   - Meetings can be created from scratch, from parsed agenda images, or from text descriptions

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

6. **Blog Post Management**:
   - Members can create, edit, and delete blog posts
   - Posts can be set as public or private
   - Public posts are visible to all users, private posts only to members
   - Paginated listing with proper access control
   - Full CRUD operations with appropriate validation

7. **Voting System**:
   - Members and non-members can cast votes in open voting sessions
   - Only members can manage voting status (open/close)
   - Atomic vote counting to ensure data integrity
   - Category-based voting (Best Speaker, Best Table Topics, etc.)
   - Support for segment-specific voting
   - Real-time vote tallying

All these features are now fully integrated with the Supabase database, with proper error handling and status codes for API responses.
