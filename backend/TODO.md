# TODO: Meeting Checkins and Feedbacks API

## API Design Overview

### Authentication Strategy
- **Webapp Users (Logged In)**: Use JWT token, ignore wxid parameters
- **Miniapp Users (Anonymous)**: Use WeChat `wx_code` to exchange for `openid` (wxid)
- **Priority**: JWT token takes precedence over wxid parameters
- **Error**: If neither auth method provided, return authentication error

### WeChat Authentication Flow
1. Miniapp calls `wx.login()` → gets temporary `code`
2. Frontend sends `code` to backend
3. Backend exchanges `code` + `app_secret` with WeChat API → gets `openid` + `session_key`
4. Backend processes request using verified `openid` as wxid

## Checkins API

### POST /meetings/{meeting_id}/checkins
**Purpose**: User checks in for multiple meeting segments (roles)

**Authentication**: JWT token OR wx_code
**Request Body**:
```json
{
  "wx_code": "071234567890abcdef",  // Optional: from wx.login() for miniapp users
  "segment_ids": ["uuid1", "uuid2"],  // Array of segment IDs user is checking in for
  "name": "张三"  // Optional: nickname for validation
}
```

**Response**:
```json
{
  "success": true,
  "checkins": [
    {
      "id": "uuid",
      "meeting_id": "uuid",
      "wxid": "wechat_openid",
      "segment_id": "uuid1",
      "name": "张三",
      "created_at": "2023-...",
      "updated_at": "2023-..."
    }
  ]
}
```

**Logic**:
1. Authenticate user (JWT or wx_code)
2. Validate meeting exists and segment_ids belong to meeting
3. Delete existing checkins for this wxid + meeting_id
4. Insert new checkin records for each segment_id
5. Return created checkins

### GET /meetings/{meeting_id}/checkins
**Purpose**: Retrieve checkins for a meeting

**Authentication**: JWT token OR wx_code
**Query Parameters**:
- `wx_code`: Optional, for miniapp users

**Response**:
```json
{
  "checkins": [
    {
      "id": "uuid",
      "meeting_id": "uuid", 
      "wxid": "wechat_openid",
      "segment_id": "uuid",
      "name": "张三",
      "created_at": "2023-...",
      "updated_at": "2023-..."
    }
  ]
}
```

**Logic**:
1. Authenticate user (JWT or wx_code)
2. If webapp user: return all checkins for meeting
3. If miniapp user: return only user's own checkins for meeting

## Feedbacks API

### POST /meetings/{meeting_id}/feedbacks
**Purpose**: Submit feedback for meeting

**Authentication**: JWT token OR wx_code
**Request Body**:
```json
{
  "wx_code": "071234567890abcdef",  // Optional: for miniapp users
  "segment_id": "uuid",  // Optional: null for experience feedback
  "type": "experience_peak",  // experience_opening|experience_peak|experience_valley|experience_ending|segment|attendee
  "value": "Great opening speech!",
  "to_attendee_id": "uuid"  // Optional: null for experience, segment's attendee_id for segment feedback, any attendee_id for attendee feedback
}
```

**Response**:
```json
{
  "success": true,
  "feedback": {
    "id": "uuid",
    "meeting_id": "uuid",
    "segment_id": "uuid",
    "type": "experience_peak",
    "value": "Great opening speech!",
    "from_wxid": "wechat_openid",
    "to_attendee_id": "uuid",
    "created_at": "2023-...",
    "updated_at": "2023-..."
  }
}
```

### GET /meetings/{meeting_id}/feedbacks
**Purpose**: Retrieve feedbacks for a meeting

**Authentication**: JWT token OR wx_code
**Query Parameters**:
- `wx_code`: Optional, for miniapp users
- `type`: Optional filter by feedback type
- `segment_id`: Optional filter by segment

**Response**: Array of feedback objects

**Access Control Logic**:
1. **Webapp user with wxid bound**: Can view feedbacks sent by their wxid + feedbacks received by their attendee_id
2. **Webapp user without wxid bound**: Can only view feedbacks received by their attendee_id  
3. **Miniapp user with wxid bound**: Can view feedbacks sent by their wxid + feedbacks received by their attendee_id
4. **Miniapp user without wxid bound**: Can only view feedbacks sent by their wxid
5. **Admin**: Can view all feedbacks

### PUT /meetings/{meeting_id}/feedbacks/{feedback_id}
**Purpose**: Update existing feedback

**Authentication**: JWT token OR wx_code
**Request Body**: Same as POST (excluding wx_code)

**Logic**:
1. Authenticate user
2. Verify user owns the feedback (from_wxid matches)
3. Update feedback
4. Return updated feedback

### DELETE /meetings/{meeting_id}/feedbacks/{feedback_id}
**Purpose**: Delete feedback

**Authentication**: JWT token OR wx_code

**Logic**:
1. Authenticate user  
2. Verify user owns the feedback (from_wxid matches) or is admin
3. Delete feedback
4. Return success

## Data Validation Rules

### Checkins
- `meeting_id` must exist
- `segment_ids` must belong to the meeting
- `wxid` must be valid (from WeChat auth)
- Replace all existing checkins for same wxid + meeting_id

### Feedbacks  
- `meeting_id` must exist
- `segment_id` must belong to meeting (if provided)
- `to_attendee_id` must be valid attendee (if provided)
- `type` must be valid enum value
- Experience feedback types: `to_attendee_id` should be null
- Segment feedback: `to_attendee_id` should match segment's attendee_id
- Attendee feedback: `to_attendee_id` can be any valid attendee_id
- Unique constraint: one experience feedback per wxid per meeting per experience type

## Implementation Notes

### WeChat Integration
- Need WeChat App ID and App Secret in environment variables
- Exchange endpoint: `https://api.weixin.qq.com/sns/jscode2session`
- Handle WeChat API errors gracefully
- Cache openid temporarily if needed

### Database Functions
- Use `get_attendee_id_for_wxid(wxid)` function for wxid → attendee_id conversion
- Leverage existing RLS policies for webapp users
- Bypass RLS with service role for all operations

### Error Handling
- Authentication failures: 401
- Authorization failures: 403  
- Validation failures: 422
- WeChat API failures: 502
- Database constraint violations: 409

### Response Filtering
- Filter sensitive data based on user permissions
- Don't expose wxids to unauthorized users
- Consistent error response format