# SoarHigh Toastmasters Club - Frontend Status

**Last updated:** 2026-07-30

**WxPost checkpoint:** `0aa76f0` — Setup, Materials, and Workspaces complete;
Draft and Preview pending. The next slice owns the rendered Draft workbench,
the formal WxPost Hermes Skill, and the focused web Hermes session through
`hermes serve`. Feishu attachment integration, selected-image description
generation, and public-preview synchronization remain in the following slice.

## Application Overview

This Next.js application serves as the web platform for the "SoarHigh Toastmasters Club," providing functionality for meeting management, growth tracking, awards recognition, posts, and voting. The application has both public-facing components and authenticated sections.

## Application Structure

### Public Routes

- **/** - Landing page with club introduction and information
- **/signin** - Authentication page with sign-in form
- **/meetings** - Public meeting listing page showing published meetings
- **/posts** - Public listing for ordinary Posts and WxPosts
- **/posts/[slug]** - Public post detail page for viewing specific content
- **/posts/wxposts/[slug]** - Public, read-only WxPost rendering and
  presentation controls
- **/meetings/workbook/[id]** - Public meeting agenda workbook preview page

### Protected Routes (under the (auth) group)

All routes in the (auth) group are protected by authentication middleware which redirects unauthenticated users to the homepage.

#### Meetings Management

- **/meetings/new** - Page for creating new meetings with two methods:
  - Template-based meeting creation
  - Image-based meeting creation (upload agenda image)
- **/meetings/edit/[id]** - Page for editing existing meetings
- **/meetings/workbook/[id]** - Page for viewing and downloading meeting agenda workbook (requires authentication for download)

#### Post Management

- **/posts/new** - Page for creating new posts
- **/posts/edit/[slug]** - Page for editing existing posts
- **/posts/wxposts/new** - Select a meeting/event or independent source and
  create a WxPost workspace
- **/posts/wxposts/edit/[workspaceKey]** - Resume an existing workspace
  directly in Materials
- **/posts/wxposts/workspaces** - List, paginate, resume, and delete shared
  workspaces

#### Operations

- **/growth** - Club growth metrics/management
- **/awards** - Management of club awards/recognition
- **/votes** - Management of meeting voting

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

- Three-tab interface for different creation methods:

  1. **Template-based creation**:

     - Three pre-defined templates (Regular Meeting, Workshop Meeting, Custom Meeting)
     - Visual cards with icons and descriptions
     - After selection, shows comprehensive meeting form

  2. **Image-based creation**:

     - Allows uploading of agenda images
     - Extracts meeting data from images using backend API

  3. **Text-based creation**:
     - Allows entering textual descriptions of meetings
     - Converts text descriptions into structured meeting data
     - Provides the same comprehensive meeting form for further editing

### Meeting Edit Page (/meetings/edit/[id])

- Loads existing meeting data from backend
- Reuses the meeting form component with populated data
- Save button to update changes
- Publish button to change meeting status from draft to published
- Full error handling and success notifications

### Posts Listing Page (/posts)

- Displays ordinary Posts and public WxPosts with All, Posts, and WxPost filters
- "New Post" and "Wx Workspaces" actions for authenticated users
- "New Post" opens a compact choice between Regular Post and WxPost
- Content cards show title, author, date, excerpt, and content type
- Visibility indicators for authenticated users
- Edit links for authenticated users

### Post Detail Page (/posts/[slug])

- Displays full post content with title and author information
- Edit button for authenticated users
- Access control based on post visibility

### WxPost Authoring

- Setup contains only the source choice and creates one workspace
- The source is immutable after creation; resumed workspaces open Materials
  directly instead of flashing Setup first
- Article type, descriptions, inclusion, transcript, notes, and writing brief
  are one browser-local Materials working copy
- "Save Materials" persists that working copy atomically and does not change
  the last saved Draft
- Import, upload, and delete remain immediate file operations
- Import, upload, and delete persist only their structural workspace changes;
  they do not save unrelated local Materials form edits
- Every material mutation carries the current manifest version; stale writes
  open a confirmation dialog before server state replaces local edits
- The Workspaces list is shared by all members, paginated, ordered by creation
  time, and displays each workspace's latest update time
- Linked workspace cards resolve compact meeting metadata in one batch and
  remain usable if meeting metadata is temporarily unavailable
- Draft and Preview are intentionally disabled until the rendered Draft
  workbench is implemented
- The next slice connects one persisted web Hermes session to the same
  workspace, submits the complete Materials snapshot through Generate Draft,
  and saves the validated ArticleDocument through the existing MCP controller
- Generate Draft is available only after Materials form changes have been
  saved; immediate import, upload, and delete operations do not conflict with
  that rule
- Direct rendered-block edits stay local until Save Draft; a successful
  Generate, Regenerate, Save Draft, or explicit Hermes revision increments
  `draftVersion`
- The first Draft workbench supports block editing and selected-text context
  for Hermes, not a general rich-text formatting toolbar
- Regenerate replaces the current canonical Draft and advances its version;
  retained version history and rollback are not part of the next slice
- Feishu active-workspace selection, Feishu attachment ingestion, selected-image
  description generation, and explicit public-preview synchronization are not
  part of that Draft-workbench slice

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

### Meeting Voting Component

- Component for meeting voting functionality
- Categorized voting options (Best Speaker, Best Table Topics, Best Evaluator, etc.)
- Support for both members and guests to cast votes
- Visual status indicator for open/closed voting
- Vote count tracking
- Admin controls to open/close voting for a meeting

### Meeting Agenda Workbook Page (/meetings/workbook/[id])

- Browser-based preview of the Excel-compatible agenda
- Download button for authenticated users
- Preview mode for draft meetings
- Proper section formatting for all meeting components

## Data Model

The application uses several key interfaces:

- **UserIF** - User information (uid, username, full_name)
- **AttendeeIF** - Meeting participant information
- **SegmentIF** - Meeting segments/agenda items with role taker references to attendees
- **MeetingIF** - Complete meeting data structure with status field ("draft" or "published")
- **MediaFile** - Media file structure with filename, url, fileKey, and uploadedAt fields
- **AwardIF** - Award structure with meeting_id, category, and winner fields
- **PostIF** - Post structure with title, slug, content, visibility, and author information
- **WxPost** interfaces - Public article documents, workspace manifests,
  versioned material sources, editorial state, and paginated workspace
  summaries
- **VoteIF** - Vote structure with meeting_id, category, name, segment (optional), and count fields
- **VoteStatusIF** - Vote status structure with meeting_id and open (boolean) fields

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
- Media upload and management for meetings
- Success/error notifications for user actions
- Attendee handling for role assignments
- Meeting awards management
- Post management with create, read, update, and delete capabilities
- Public WxPost rendering and filtering inside Posts
- Source-only WxPost Setup and immutable workspace creation
- Browser-local Materials editing with explicit Save Materials
- Version-conflict confirmation for every Materials mutation
- Responsive, paginated shared Workspaces list with semantic edit routes
- Meeting voting system with category-based voting
- Meeting media display with image gallery and lightbox
- Vote status management (open/close voting)
- Voting permissions for members and non-members
- Meeting agenda workbook generation with Excel compatibility
- Browser-based preview with responsive Excel-like styling

### Current Implementation Details

The meeting management workflow is now fully implemented:

1. **Meeting Creation**

   - Users can create meetings using templates, image upload, or text descriptions
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

8. **WxPost Workspace Authoring**

   - Creates linked or independent workspaces from a source-only Setup page
   - Opens existing workspaces directly in Materials
   - Keeps ordinary form edits local until "Save Materials"
   - Keeps the saved Draft isolated from Materials edits
   - Executes import, upload, and delete immediately with manifest-version
     protection
   - Lists shared workspaces with pagination, stable creation-time ordering,
     compact linked-meeting metadata, and resilient loading/error states
   - Keeps workspace cards visible during deletion and background refreshes;
     only the first load replaces the list with the centered spinner
   - Leaves Draft generation, rendered Draft editing, read-only Preview, the
     formal WxPost Hermes Skill, and the focused `hermes serve` conversation
     for the next implementation slice
   - Plans a workspace-local, multi-select `Voice & tone` brief for that slice:
     six presets, up to three selections, and optional custom profiles with a
     user-editable AI instruction proposal
   - Leaves Feishu workspace/attachment integration, selected-image
     descriptions, and public-preview synchronization for the following slice

9. **Voting System**

   - Category-based voting for meetings (Best Speaker, Best Table Topics, etc.)
   - Voting status management (open/close)
   - Vote counting with atomic operations
   - Different permissions for members and non-members
   - Admin controls for managing voting
   - Real-time vote count updates

10. **Meeting Agenda Workbook**

- Excel-compatible workbook generation with proper formatting
- Browser-based preview with responsive design
- Support for complex Excel features (merged cells, styling)
- Embedded images (club logos and QR codes)
- Preview mode for draft meetings
- Authentication-gated download functionality
- Proper section formatting for all meeting components

11. **Meeting Media Management**

- Image upload functionality for meetings
- Media display in expandable meeting cards with tabbed interface
- Responsive image gallery with grid layout
- Interactive lightbox for full-size image viewing
- Image navigation with prev/next controls in lightbox
- Environment-aware handling of HTTP/HTTPS URLs

The application follows a clean, modern UI design with gradient accents, responsive layouts, and thoughtful user interactions. The meeting creation workflow is particularly sophisticated, offering multiple creation methods and detailed customization options.
