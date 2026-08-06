# SoarHigh Toastmasters Club - Backend Status

**Last updated:** 2026-08-06

**WxPost checkpoint:** `46d8d7e` is the committed Phase 2 baseline. The Phase 3
implementation described below completes the WeChat Draft projection. Slice 6
provides Draft
session, save, generation, revision, and canonical rendering. Backend
normalizes every Draft mutation into
`WxPostRenderDocument`, then requires the authenticated stateless Next route to
compile it with the same pure TypeScript source used by the browser. A compiler
failure returns 503 before controller persistence, so the previous saved Draft
remains authoritative. Backend remains the validation, versioning, asset, and
publication authority and never trusts browser-generated HTML. Hermes now
submits typed proposal schema v2; the controller derives manifest-owned source
identity and inclusion, records Hermes-authored captions as AI proposals, and
deterministically serializes canonical ArticleDocument v1 directives before
Backend validation. This removes model-authored YAML without adding repair
heuristics or a second validator. Slice 7A now synchronizes one saved workspace
Draft to one stable public WxPost with guarded Supabase revisions and
content-addressed OSS assets. Slice 7B image-description proposals, Slice 7C
Draft Assistant/Controller hardening, and Slice 7D conversational Feishu
workspace/material authoring are also complete. Phase 3 now adds authenticated,
confirmed, idempotent Public Revision delivery to one Official Account draft.

Slice 7C gives small Draft edits a typed, version-bound endpoint instead of
resubmitting the complete article. Backend applies exact body-node, directive,
media, description, and cover operations, derives the body-plus-cover media
dependency snapshot, validates the complete result, and returns it to the
controller for the existing atomic compare-and-swap save. Materials inclusion
remains independent from Draft body and cover state.

## Architecture Overview

This backend application serves as the API for the SoarHigh Toastmasters Club platform. It's built with FastAPI and uses Supabase as the database backend, with JWT-based authentication.

## Technology Stack

- **Framework**: FastAPI
- **Database**: Supabase
- **Authentication**: JWT-based authentication via Supabase
- **AI Services**: OpenAI API (GPT-4o) for meeting agenda image parsing
- **Storage**: AliCloud OSS for media storage
- **Runtime**: Python with uvicorn server

## API Endpoints

### Authentication

- **/whoami** - Endpoint to retrieve current authenticated user information
- **/members** - Endpoint to retrieve all club members (requires authentication)

### Meeting Management

- **/meeting/parse_agenda_image** - Endpoint to parse a meeting agenda from an uploaded image using OpenAI's GPT-4o model
- **/meeting/plan_from_text** - Endpoint to plan a meeting from textual description using OpenAI's API
- **/meetings** - GET: List meetings (with filter by status), POST: Create a new meeting
- **/meetings/options** - GET: Paginated compact meeting records for selectors
- **/meetings/options/batch** - POST: Resolve up to 100 compact meeting records
  for workspace cards
- **/meetings/{id}** - GET: Retrieve meeting details
- **/meetings/{id}** - PUT: Update an existing meeting
- **/meetings/{id}/status** - PUT: Update meeting status (draft/published)
- **/meetings/{id}** - DELETE: Delete a meeting

### Awards Management

- **/meetings/{id}/awards** - GET: Retrieve awards for a specific meeting
- **/meetings/{id}/awards** - POST: Save awards for a specific meeting

### Media Management

- **/meetings/{id}/media** - GET: List all media files for a meeting
- **/meetings/{id}/media/get-upload-url** - POST: Get pre-signed URLs for uploading media files
- **/meetings/{id}/media** - DELETE: Delete media files from a meeting

### Voting Management

- **/meetings/{id}/votes** - GET: Retrieve votes for a specific meeting
- **/meetings/{id}/votes** - POST: Cast votes for a specific meeting
- **/meetings/{id}/votes/increment** - POST: Increment vote counts
- **/meetings/{id}/votes/status** - GET: Get voting status (open/closed) for a meeting
- **/meetings/{id}/votes/status** - PUT: Update voting status (open/close voting)

### Feedback Management

- **/meetings/{id}/feedbacks** - GET: Retrieve feedbacks with access control, POST: Create feedback
- **/meetings/{id}/feedbacks/{feedback_id}** - PUT: Update feedback, DELETE: Delete feedback
- **/meetings/{id}/feedbacks/experiences** - POST: Create experience curve feedbacks (batch operation)

### Checkin Management

- **/meetings/{id}/checkins** - GET: Retrieve checkins, POST: Create checkins for segments

### Blog Post Management

- **/posts** - GET: List posts with pagination, POST: Create a new post
- **/posts/{slug}** - GET: Retrieve a post by slug, PATCH: Update an existing post, DELETE: Delete a post

### WxPost Management

- **/posts/wxposts/capabilities** - GET: Return the canonical authoring
  vocabulary
- **/posts/wxposts/validate** - POST: Validate an ArticleDocument without
  storing it
- **/posts/wxposts** - POST: Store a validated WxPost through the scoped
  service credential
- **/posts/wxposts/{id}** - PATCH: Update a stored WxPost with revision
  protection
- **/posts/wxposts/{slug}** - GET: Return a public render document
- **/posts/wxposts/workspaces** - POST/GET: Create a controller-identified
  workspace or list paginated shared workspaces
- **/posts/wxposts/workspaces/{id}/publication** - GET: Derive publication
  freshness from the current saved Draft and ready public revision
- **/posts/wxposts/workspaces/{id}/publication/service** - GET: Return the same
  database-only publication metadata to the Controller under the existing
  service token, without creating a Controller-to-Backend proxy loop
- **/posts/wxposts/workspaces/{id}/draft-preview** - POST: Under the existing
  service credential, issue a 24-hour temporary link bound to the current saved
  Draft version together with the authenticated Draft Edit URL
- **/posts/wxposts/workspaces/{id}/editor-links** - GET: Under the same service
  credential, return canonical authenticated Materials and Draft Edit routes
  for Feishu-to-web handoff
- **/posts/wxposts/draft-previews/{token}** - GET: Return canonical render input
  only while the signed Draft version remains current; its nested media route
  serves only media referenced by that exact Draft
- **/posts/wxposts/workspaces/{id}/publication/sync** - POST: Explicitly and
  version-safely synchronize the saved Draft, included assets, and canonical
  render to one stable public WxPost
- **/posts/wxposts/workspaces/{id}** - PATCH/DELETE: Save or delete a versioned
  workspace
- **/posts/wxposts/workspaces/{id}/...** - Authenticated proxy for the
  controller's context, material, import, upload, content, delete, Draft
  session, Draft save, Draft generation, and Draft chat operations

Frontend and Backend may remain on Vercel while Controller and Hermes run on a
DigitalOcean VPS. Backend proxies canonical workspace operations over HTTPS
using `WXPOST_SERVICE_TOKEN`; no feature requires the processes to share a
host. Their checked API contracts must remain compatible.

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
- Associated media files stored in AliCloud OSS

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

### Media File Model

Model for tracking meeting media files:

- `filename`: Original filename of the media file
- `url`: Public URL for accessing the file
- `fileKey`: OSS object key for the file
- `uploadedAt`: Timestamp when the file was uploaded

### Vote Status Model

Model for tracking voting status:

- `meeting_id`: Reference to the associated meeting
- `open`: Boolean indicating if voting is open or closed

### Feedback Model

Model for meeting feedback and checkins:

- `id`: Feedback identifier
- `meeting_id`: Reference to the associated meeting
- `from_wxid`: WeChat openid of the feedback provider
- `type`: Feedback type (experience_opening/peak/valley/ending, segment, attendee)
- `value`: Feedback content
- `segment_id`: Optional reference to a specific meeting segment
- `to_attendee_id`: Optional target attendee for the feedback
- `created_at`: Timestamp of feedback creation
- `updated_at`: Timestamp of last update

### Checkin Model

Model for meeting participation tracking:

- `id`: Checkin identifier
- `meeting_id`: Reference to the associated meeting
- `wxid`: WeChat openid of the participant
- `segment_id`: Reference to the meeting segment being checked into
- `name`: Optional name for validation
- `created_at`: Timestamp of checkin

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
  - `get_meeting_options()`: Retrieves lightweight paginated selector records
  - `get_meeting_options_by_ids()`: Resolves a bounded batch for workspace cards
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
- Functions for feedback and checkin management:
  - `create_feedback()`: Creates individual feedback records
  - `create_experiences()`: Creates experience curve feedbacks (batch operation)
  - `get_feedbacks_by_meeting()`: Retrieves feedbacks with sophisticated access control
  - `update_feedback()`: Updates existing feedback records
  - `delete_feedback()`: Deletes feedback records
  - `create_checkins()`: Creates checkin records for meeting segments
  - `get_checkins_by_meeting()`: Retrieves checkins for a meeting
- Functions for blog post management:
  - `get_content_items()`: Merges ordinary Posts and public WxPosts for the
    paginated Posts index
  - `get_post_by_slug()`: Retrieves a specific post by slug
  - `create_post()`: Creates a new blog post
  - `update_post()`: Updates post details
  - `delete_post()`: Deletes a post
- Functions for WxPost management:
  - `create_wxpost()`: Stores one validated canonical article document
  - `update_wxpost()`: Updates through an expected-revision guard
  - `get_public_wxpost_by_slug()`: Derives the public render document
  - Workspace proxy routes authenticate members, hide the controller token,
    enforce a 50 MiB upload limit, and forward manifest-version guards

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
- WxPost management:
  - Canonical ArticleDocument validation and public rendering
  - Revision-protected create and update operations
  - Authenticated workspace creation, listing, saving, deletion, and material
    operations through the containerized controller
  - Bounded compact meeting metadata for selectors and workspace cards
  - Controller-side ArticleDocument validation and Draft persistence with
    workspace-scoped Hermes Generate, Regenerate, and focused revision
  - Strict typed Draft proposal schema v2 with controller-owned directive
    serialization, one bounded formal pre-save correction, and no YAML repair
    or runtime/version retry heuristic
  - Optional Custom article labels, allowing Independent workspaces to infer
    their form from the saved brief without inventing a placeholder label
  - Deterministic public persistence for an unlabeled Custom article using the
    database-safe `Custom` label while workspace and Draft state remain null
  - Trusted canonical inline-HTML compilation for every Draft mutation through
    the existing WxPost service credential and public-base URL
  - Versioned semantic validation for explicit narrative sections, single
    images, galleries, videos, people, takeaways, info grids, timelines, pull
    quotes, and inline key points without content-repair heuristics
  - Workspace-local `Voice & tone` editorial state without a legacy-manifest
    migration or compatibility branch
  - One durable public WxPost per workspace with `source_workspace_id`, saved
    Draft version, and normalized Draft/media bundle SHA-256 linkage
  - First publication hidden until every public asset and canonical render are
    ready; later updates preserve the previous ready revision until one guarded
    final row swap succeeds
  - Workspace-linked public rows reject the legacy direct-update endpoint, so
    the saved workspace Draft remains the only editorial authority
  - Idempotent content-addressed OSS asset reuse and explicit failed/pending
    asset lifecycle without leaking workspace source URLs to public documents
  - Post-finalization cleanup removes public OSS assets no longer referenced by
    the new revision; authenticated public-page deletion hides the post first,
    removes all of its OSS assets, and then removes the public database row
  - Batched publication status enrichment for paginated workspace summaries
    without one Supabase query per card; a temporary Supabase status failure
    does not make private workspace listing unavailable
  - Authenticated Public Revision projection to one WeChat Official Account
    draft per durable workspace, with Backend-owned projection state and a
    typed fixed-egress VPS gateway that alone owns Official Account credentials
    and its process-local access-token cache
  - Deterministic WeChat delivery over the existing canonical inline HTML:
    editor-only `data-*`/`contenteditable` attributes are removed, active
    content is rejected, rendered image `src` values are replaced with URLs
    returned by WeChat, root `clamp()` padding becomes a fixed mobile inset,
    section-heading font quotes are normalized, and hyperlinks become visible
    plain text before submission
  - Content-addressed body-image and permanent-cover reuse, revision and
    presentation fingerprinting, update-in-place through the stored WeChat
    media ID, and no publication-time content generation or re-layout
  - Backend sends immutable public-asset descriptors rather than image bytes;
    the fixed-egress Gateway alone downloads validated `public/wxposts/*` OSS
    objects and uploads them to the typed WeChat media endpoints
  - Atomic `creating`/`ready`/`uncertain` projection state with a 15-minute
    lease, safe retry of updates, and bounded recovery of an ambiguous first
    add without issuing a blind second `draft/add`
  - `draft/get` readback hashes and official temporary-preview refetch without
    storing a third editable HTML document
  - Official preview URL validation accepts WeChat's observed
    `http://mp.weixin.qq.com` response and deterministically upgrades it to
    HTTPS while continuing to reject every non-WeChat host

Phase 3 projection persistence is installed through Supabase migrations
`20260806000000` through `20260806000002`. Migration `20260806000003` removes
the obsolete service-role token table after Backend transport moves to the VPS
gateway; it does not touch draft projections. Configure Backend with
`WECHAT_GATEWAY_BASE_URL`, `WECHAT_GATEWAY_SERVICE_TOKEN`, and
`WECHAT_OFFICIAL_ACCOUNT_NAME`. AppID/AppSecret live only on the gateway; none
of these server settings are sent to the browser.

Validation recorded on 2026-08-06:

- the configured real Official Account issued an access token and accepted a
  `draft/batchget` read after its direct backend IP was allowlisted;
- the remote claim RPC was probed with temporary rows and correctly returned
  claimed, busy for a live add, and uncertain only after lease expiry; probes
  were deleted in `finally`;
- Saved Draft v19 changed only its explicitly approved 118-character excerpt,
  then synchronized Public Revision 2 without changing its durable row or
  public slug;
- real body-image and cover uploads plus `draft/add` created exactly one
  Official Account draft from Public Revision 2; an identical retry returned
  `unchanged`, kept the same media ID, and left the real draft count at one;
- changing only the typeface updated that same draft in place, and restoring
  the final `brand-default` / `paper-neutral` / `light` / `editorial-serif`
  projection again preserved the media ID and draft count;
- real `draft/get` readback preserved the complete text and tag sequence. The
  detected platform filtering moved two image `src` values to `data-src`,
  removed their `loading` attributes, and stripped a bounded set of heading,
  article-padding, and positioned-container styles. The official temporary
  `mp.weixin.qq.com` preview still loaded the title, digest, body structure,
  and both body images;
- projection version 4 was revalidated over all 15 controlled observations:
  fixed root padding survived in 15/15 readbacks, empty section-title styles
  fell from 17 to zero, and hyperlink tag differences fell from 10 to zero;
  all six existing draft media IDs were reused, including one diagnostic draft
  updated and captured sequentially across ten presentation states;
- a focused official-preview check used Chrome device emulation at a 390 x 844
  viewport through Computer Use. WeChat's mobile stylesheet overrode ordinary
  root `text-align:left` with justified text; the deterministic projection now
  submits `text-align:left!important`. After reusing and updating the same
  diagnostic media ID, submitted HTML and `draft/get` readback retained that
  declaration, and the live page computed `left` for both the root article and
  its paragraphs with `word-spacing: 0px`;
- physical-phone evidence then isolated two content-controlled differences:
  WeChat's native `blockquote` styling added a rule to the centered Quote, and
  three whitespace-only list nodes appeared as three empty bullets in the
  Official Account Assistant. Projection version 5 now resets border and
  padding only on borderless styled blockquotes and removes only whitespace
  between list boundaries and `li` elements;
- the same diagnostic draft was updated in place with its original media ID.
  Submitted HTML and `draft/get` readback retained both v5 transforms. A fresh
  official temporary preview at 390 x 844 computed zero Quote border/padding,
  exposed exactly two list items with no whitespace child nodes, and retained
  the intentional 2px Pull Quote and 3px Takeaway rules. Physical-phone
  confirmation of those two fixes remains pending;
- the desktop temporary preview still remaps the light palette through
  WeChat-generated `prefers-color-scheme: dark` rules. The physical-phone
  Official Account Assistant already renders the requested light background
  and black Takeaway rule, so no unsupported color override or second renderer
  was added for that surface-specific behavior;
- the physical-phone Official Account Assistant also inserted roughly one
  inherited line box between images and their captions even though submitted
  HTML, readback, and the official temporary preview retained the intended 8px
  gap. Projection version 6 gives only direct image-wrapper containers zero
  font size and line height. The user confirmed that this makes the Assistant
  caption spacing compact; the same declarations survive `draft/get`, while
  the canonical renderer and caption spacing remain unchanged;
- projection version 9 delegates only each palette's ordinary body and heading
  text color to WeChat instead of submitting a fixed light-palette foreground.
  All five palettes and both requested appearances are covered by focused
  tests; muted text, accents, borders, and local surfaces remain explicit. A
  real dark Brand Blue update reused the existing diagnostic media ID, and
  both submitted HTML and `draft/get` readback omitted the base foreground
  while retaining `#5f6b7a` muted text and `#2563eb` accents. At a 390 x 844
  dark official-preview viewport, Chrome computed ordinary body and heading
  text from WeChat's native rule as `rgba(255, 255, 255, 0.55)`;
- projection version 10 removes only the canonical `<article>`'s direct
  `<header>` before WeChat submission because the official page already owns
  the title, account name, and date, while the excerpt is supplied separately
  as the WeChat digest. Submitted HTML and `draft/get` both fell from 100 to 93
  elements without any additional readback tag loss. The official 390 x 844
  preview retained only WeChat's native heading metadata and began the article
  at its opening paragraph after one refresh for WeChat's preview cache;
- projection version 11 retains the removed header's original top rule as a
  content-free separator: Brand Blue keeps its two-color `border-image`
  gradient, Warm Terracotta keeps its solid accent, and the remaining palettes
  keep their existing thin rule. The WeChat-only article top padding is 16px,
  the separator-to-body gap is 16px, and the canonical body's additional 32px
  top padding becomes zero. Real submitted HTML, `draft/get`, and the 390 x 844
  official preview retained the gradient and the compact opening spacing;
- projection version 12 removes the remaining WeChat-only article top padding,
  leaving only the platform's own fixed space below its native metadata. Header
  rules authored at 4px become 2px in the WeChat separator while existing 1px
  rules remain unchanged. Real submitted HTML and `draft/get` retained the 2px
  Brand Blue gradient, and the 390 x 844 official preview confirmed the tighter
  placement above it;
- projection version 13 restricts palette-token mapping to inline `style`
  declarations so matching literal text, alt attributes, and URLs cannot be
  rewritten. Ambiguous-add recovery now requires matching metadata plus a
  deterministic text/tag/body-image signature. Reloaded clients can invoke the
  recovery request, while a separate literal confirmation can reset only an
  uncertain projection with no known media ID after the member verifies that
  no matching Official Account draft exists. An authenticated Chrome update of
  the existing diagnostic projection returned `updated`, reused its stored
  draft rather than adding another one, and completed the required `draft/get`
  readback;
- projection version 14 moves Gateway draft payloads from ASCII `\\u` escapes
  to real UTF-8 bytes. This prevents WeChat from preserving escaped curly
  quotes and dashes as visible text or corrupting the title's middle dot. The
  Gateway no longer repairs readback content locally, so platform corruption
  remains visible. A real update reused the existing media ID; strict
  `draft/get` returned the exact title, curly quotes, and em dash with no
  replacement character or literal escape, and the refreshed 390 x 844 Chrome
  preview displayed the same corrected punctuation;
- full backend validation passed with 674 tests, 23 intentionally deselected,
  Ruff, Ruff format, and mypy;
- physical-phone checks confirmed the content-controlled list, Quote, Takeaway,
  image, caption-spacing, and light-surface behavior. The real API lifecycle
  and official temporary browser preview are complete; a final production
  deployment smoke remains after the fixed-egress gateway is installed. The
  adapter continues to reject over-limit revisions instead of truncating or
  rewriting Saved Draft content;
- the typed fixed-egress gateway implementation now owns only Official Account
  credentials, a locked in-memory token cache, fixed-IP calls to the seven
  required WeChat operations, and synchronous response forwarding. Vercel
  Backend remains the sole publication orchestrator and Supabase writer. The
  gateway cannot read Public Revisions, access Supabase, persist publication
  state, proxy arbitrary WeChat paths, or implement a second renderer or
  idempotency model. Production HTTPS reverse-proxy setup, VPS-IP allowlisting,
  Vercel environment migration, and the final real draft smoke remain deployment
  operations rather than local implementation claims.
- fixed-egress gateway validation passed the complete Backend suite at 676
  tests with 23 intentionally deselected, the complete Hermes/Controller/Gateway
  suite at 237 tests, Ruff, Ruff format, mypy, shell syntax, Compose config,
  a real Docker image build, and a locked-down container `/healthz` smoke. The
  13-test WxPost renderer/browser suite also passed without a frontend contract
  change.
- direct OSS image transport validation passed the complete Backend suite at
  679 tests with 23 intentionally deselected and the complete
  Hermes/Controller/Gateway suite at 253 tests. A real local end-to-end smoke
  created `gateway-oss-transport-smoke-test`: Gateway downloaded one immutable
  public OSS object from its validated descriptor, uploaded it through both
  typed WeChat image endpoints, created one Official Account draft, completed
  readback and temporary-preview retrieval, then returned `unchanged` on an
  identical retry without another image upload or draft mutation.
- confirmed-missing WeChat drafts are now replaced instead of blocking a
  publish. Backend preserves Gateway `wechatErrcode`, treats `40007` as safe to
  replace only after `draft/get` confirms the stored ID is gone, clears that
  stale reference atomically, refreshes the cover media ID, and creates one new
  draft under the existing uncertainty recovery rules. A real smoke deleted
  the linked diagnostic draft remotely, then republished it successfully with
  one cover upload, one draft add, and successful readback. Local status remains
  responsible only for publication and uncertainty-recovery state. The Revision
  page keeps its Eye action available and performs the live `draft/get` through
  the preview endpoint only when the member clicks it. A confirmed `40007`
  clears the stale local ID and reports the missing remote draft, while transient
  WeChat failures do not erase projection state. The complete Backend suite
  passes at 688 tests with 23 intentionally deselected, plus Ruff, Ruff format,
  and mypy.
- direct OSS upload now keeps byte-size and SHA-256 verification authoritative
  while deriving the WeChat multipart MIME type from the actual image
  signature. This restores the previous successful behavior for an immutable
  PNG whose legacy OSS metadata says JPEG without routing its bytes back
  through Backend or weakening content-integrity checks.

The real Supabase/OSS publication lifecycle has an opt-in destructive smoke
test at `app/services/tests/test_wxpost_publication_live.py`. It creates only a
uniquely named temporary WxPost, verifies initial publication, idempotent retry,
stale-asset cleanup, and final deletion, then cleans up in `finally`. It is
excluded from normal test runs and requires all four guards below to match the
loaded backend target exactly:

```bash
WXPOST_PUBLICATION_LIVE_TEST=1 \
WXPOST_PUBLICATION_LIVE_ALLOW_MUTATION=yes \
WXPOST_PUBLICATION_LIVE_SUPABASE_URL="$SUPABASE_URL" \
WXPOST_PUBLICATION_LIVE_OSS_BUCKET="$ALICLOUD_OSS_BUCKET" \
  pytest -m live app/services/tests/test_wxpost_publication_live.py
```

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
   - Associated media files automatically deleted from AliCloud OSS

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

8. **Feedback and Checkin System**:

   - Complete feedback CRUD operations with sophisticated access control
   - Experience curve feedback methodology (opening/peak/valley/ending)
   - Batch experience feedback creation for efficient user input
   - Segment and attendee-targeted feedback support
   - Meeting participation tracking through checkins
   - WeChat integration for miniapp user feedback submission
   - Proper ownership validation and admin override capabilities

9. **Media Management**:
   - Support for uploading media files to meetings
   - Pre-signed URL generation for direct browser-to-OSS uploads
   - Media file listing with proper file metadata
   - Media file deletion with permission controls
   - Automatic cleanup of media files when meetings are deleted

All these features are now fully integrated with the Supabase database and AliCloud OSS storage, with proper error handling and status codes for API responses.
