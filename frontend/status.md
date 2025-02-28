# SoarHigh Toastmasters Club - Frontend Status

## Application Overview

This Next.js application serves as the web platform for the "SoarHigh Toastmasters Club," providing functionality for meeting management, growth tracking, and awards recognition. The application has both public-facing components and authenticated sections.

## Application Structure

### Public Routes

- **/** - Landing page with club introduction and information
- **/signin** - Authentication page with sign-in form

### Protected Routes (under the (auth) group)

All routes in the (auth) group are protected by authentication middleware which redirects unauthenticated users to the homepage.

#### Meetings Management

- **/meetings** - Displays a list of meetings
- **/meetings/new** - Page for creating new meetings with two methods:
  - Template-based meeting creation
  - Image-based meeting creation (upload agenda image)
- **/meetings/edit/[id]** - Page for editing existing meetings (planned)

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
- Main navigation links: Introduction, Meetings
- Dropdown menu for Operations (Growth, Awards) for authenticated users
- Sign-out functionality

### New Meeting Creation (/meetings/new)

- Two-tab interface for different creation methods:

  1. **Template-based creation**:

     - Three pre-defined templates (Regular Meeting, Workshop Meeting, Custom Meeting)
     - Visual cards with icons and descriptions
     - After selection, shows comprehensive meeting form

  2. **Image-based creation**:
     - Allows uploading of agenda images
     - Likely extracts meeting data from images

### Meeting Form

- Extensive form for meeting details including:
  - Meeting type, theme, manager
  - Date, start/end times
  - Location
  - Segments editor for managing meeting agenda
  - Currently implements meeting editing but lacks save/draft/publish functionality

### Meetings List

- Displays all meetings
- For members: Shows both published and draft meetings with status indicators
- For non-members: Shows only published meetings
- Clicking on draft meetings takes members to the edit page

### Meeting Edit Page (Planned)

- Allows members to continue editing draft meetings
- Provides options to save changes or publish the meeting
- Reuses the MeetingForm component with additional status controls

## Data Model

The application uses several key interfaces:

- **UserIF** - User information (uid, username, full_name)
- **SegmentIF** - Meeting segments/agenda items
- **MeetingIF** - Complete meeting data structure
  - Will include a `status` field ("draft" or "published")
- **AwardIF** - Award categories and winners

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

### Planned Enhancements

- Meeting save and publish functionality
- Draft status for meetings
- Status indicators in meetings list
- Edit page for continuing work on draft meetings
- Form validation
- Success/error notifications
- Navigation after save operations

## Save/Draft/Publish Implementation Plan

For the meeting creation and publishing functionality, we've established a simplified approach:

1. **Core Workflow**

   - All newly created meetings are saved as drafts by default
   - Members can see draft meetings in the meetings list (with visual indicators)
   - Non-members only see published meetings
   - Members can edit draft meetings and publish them when ready

2. **Data Model Updates**

   - Add `status` field to MeetingIF interface (values: "draft", "published")
   - Default value for new meetings: "draft"

3. **Meetings List Page Updates**

   - Show draft meetings only to members
   - Add clear visual indicators for draft status
   - Link draft meetings to the edit page

4. **Meeting Creation**

   - Single "Create Meeting" button that saves the meeting as a draft
   - Minimal validation for draft creation
   - Redirect to meetings list after creation

5. **Edit Route Implementation**

   - Create a dedicated meetings/edit/[id] route
   - Reuse the MeetingForm component with added status controls
   - Include "Save Changes" button to update draft
   - Add "Publish Meeting" button to change status to published

6. **Validation Logic**

   - Minimal validation when saving as draft (allow incomplete information)
   - Comprehensive validation before publishing
   - Visual feedback for validation errors

7. **User Feedback**
   - Toast notifications for successful operations
   - Clear error messages
   - Loading indicators during API operations

This simplified approach creates a more intuitive workflow that aligns with common document editing patterns in modern web applications.

The application follows a clean, modern UI design with gradient accents, responsive layouts, and thoughtful user interactions. The meeting creation workflow is particularly sophisticated, offering multiple creation methods and detailed customization options.
