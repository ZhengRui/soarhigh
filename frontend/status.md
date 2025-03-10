# SoarHigh Toastmasters Club - Frontend Status

## Application Overview

This Next.js application serves as the web platform for the "SoarHigh Toastmasters Club," providing functionality for meeting management, growth tracking, awards recognition, and posts. The application has both public-facing components and authenticated sections.

## Application Structure

### Public Routes

- **/** - Landing page with club introduction and information
- **/signin** - Authentication page with sign-in form
- **/meetings** - Public meeting listing page showing published meetings
- **/posts** - Public posts listing page showing published content
- **/posts/[slug]** - Public post detail page for viewing specific content

### Protected Routes (under the (auth) group)

All routes in the (auth) group are protected by authentication middleware which redirects unauthenticated users to the homepage.

#### Meetings Management

- **/meetings/new** - Page for creating new meetings with two methods:
  - Template-based meeting creation
  - Image-based meeting creation (upload agenda image)
- **/meetings/edit/[id]** - Page for editing existing meetings

#### Post Management

- **/posts/new** - Page for creating new posts
- **/posts/edit/[slug]** - Page for editing existing posts

#### Operations

- **/growth** - Club growth metrics/management
- **/awards** - Management of club awards/recognition

## User Experience by Route

### Landing Page (/)

- Features the club name "SoarHigh Toastmasters Club" with a stylized header
- Contains introduction content about the club
- Accessible to all users (authenticated and unauthenticated)

### Sign In Page (/signin)

- Simple authentication form
- Redirects authenticated users appropriately

### Header Navigation

- Present across all pages
- Responsive design with mobile menu
- Dynamically changes based on authentication status
- Main navigation links: Introduction, Meetings, Posts
- Dropdown menu for Operations (Growth, Awards) for authenticated users
- Sign-out functionality

### Public Meetings Page (/meetings)

- Displays all meetings with different visibility rules:
  - For members: Shows both published and draft meetings with status indicators
  - For non-members: Shows only published meetings
- "Create Meeting" button displayed only for authenticated users
- Meeting cards show key meeting information including date, time, and theme
- Status indicators for draft/published meetings (visible to members)
- Link to edit draft meetings for authenticated users

### New Meeting Creation (/meetings/new)

- Two-tab interface for different creation methods:

  1. **Template-based creation**:

     - Three pre-defined templates (Regular Meeting, Workshop Meeting, Custom Meeting)
     - Visual cards with icons and descriptions
     - After selection, shows comprehensive meeting form

  2. **Image-based creation**:
     - Allows uploading of agenda images
     - Extracts meeting data from images using backend API

### Meeting Edit Page (/meetings/edit/[id])

- Loads existing meeting data from backend
- Reuses the meeting form component with populated data
- Save button to update changes
- Publish button to change meeting status from draft to published
- Full error handling and success notifications

### Posts Listing Page (/posts)

- Displays posts with visibility based on user authentication
- "Create Post" button for authenticated users
- Post cards with title, author, date, and excerpt
- Visibility indicators for authenticated users
- Edit links for authenticated users

### Post Detail Page (/posts/[slug])

- Displays full post content with title and author information
- Edit button for authenticated users
- Access control based on post visibility

### Meeting Form

- Comprehensive form for meeting details including:
  - Meeting type, theme, manager
  - Date, start/end times
  - Location
  - Segments editor for managing meeting agenda
- Save functionality that preserves meeting as draft
- Validation rules with appropriate UI feedback

### Role Taker Input Component

- Custom input component for selecting or creating role takers
- Supports both members and guests as attendees
- Auto-suggests existing club members
- Allows creating guest attendees with custom names
- Provides visual distinction between member and guest selections

### Meeting Awards Form Component

- Component for managing meeting awards
- Add/remove functionality for awards
- Category selection with standard options and custom input
- Winner selection with member auto-suggestion
- Validation with appropriate UI feedback
- Save functionality to submit all awards at once

## Data Model

The application uses several key interfaces:

- **UserIF** - User information (uid, username, full_name)
- **AttendeeIF** - Meeting participant information
- **SegmentIF** - Meeting segments/agenda items with role taker references to attendees
- **MeetingIF** - Complete meeting data structure with status field ("draft" or "published")
- **AwardIF** - Award structure with meeting_id, category, and winner fields
- **PostIF** - Post structure with title, slug, content, visibility, and author information

## Technical Implementation

- Uses Next.js App Router for routing
- Authentication with token-based system
- React Query for data fetching
- Jotai for state management
- Tailwind CSS for styling
- Mobile-responsive design

## Development Status

### Completed Features

- User authentication
- Meeting template selection
- Meeting form with segment editing
- Template transformation with UUID generation
- Responsive UI
- Meeting listing with status indicators
- Meeting creation (saving as draft)
- Meeting edit functionality
- Status management (draft/published)
- Role taker input component with member/guest handling
- Time picker components for meeting segments
- Segments editor with add/edit/delete operations
- Success/error notifications for user actions
- Attendee handling for role assignments
- Meeting awards management
- Post management with create, read, update, and delete capabilities

### Current Implementation Details

The meeting management workflow is now fully implemented:

1. **Meeting Creation**

   - Users can create meetings using templates or image upload
   - All new meetings are saved as drafts by default
   - Multiple validation options with appropriate feedback

2. **Meeting Listing**

   - Responsive meeting card design
   - Different visibility based on authentication status
   - Clear status indicators for draft meetings

3. **Meeting Editing**

   - Full editing capabilities for existing meetings
   - Status management (draft/published)
   - Validation before publishing

4. **Meeting Form Components**

   - Rich form controls with validation
   - Segments editor for detailed agenda management
   - Time management with visual pickers

5. **User Feedback**

   - Loading states during API operations
   - Success notifications after operations complete
   - Error handling with appropriate messages

6. **Awards Management**

   - UI for adding and managing meeting awards
   - Support for both standard and custom award categories
   - Winner selection with member auto-suggestion
   - Validation before submitting awards
   - Success/error notifications for award operations

7. **Post Management**

   - Posts are markdown based
   - Complete CRUD operations for posts
   - Visibility controls (public/private)
   - Access control based on visibility and user authentication

The application follows a clean, modern UI design with gradient accents, responsive layouts, and thoughtful user interactions. The meeting creation workflow is particularly sophisticated, offering multiple creation methods and detailed customization options.
