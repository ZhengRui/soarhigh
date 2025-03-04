-- SoarHigh Toastmasters Club - Supabase Database Schema
-- This file contains the SQL commands used to set up the database structure in Supabase

-- =============================================
-- TABLE DEFINITIONS
-- =============================================

-- Members table - stores user account information linked to Supabase auth
CREATE TABLE members (
  id uuid PRIMARY KEY REFERENCES auth.users(id),
  username text UNIQUE NOT NULL,
  full_name text NOT NULL,
  is_admin boolean DEFAULT false,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

-- Attendees table - stores information about people who attend meetings
-- Can be linked to members (for club members) or be standalone (for guests)
CREATE TABLE attendees (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    wxid TEXT,
    cell TEXT,
    type TEXT NOT NULL CHECK (type IN ('Member', 'Guest')),
    member_id UUID REFERENCES members(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Meetings table - stores meeting information
CREATE TABLE meetings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    no INT,
    type TEXT NOT NULL CHECK (type IN ('Regular', 'Workshop', 'Activity')),
    theme TEXT NOT NULL,
    manager_id UUID REFERENCES attendees(id) NOT NULL,
    date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    location TEXT NOT NULL,
    introduction TEXT,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Segments table - stores individual meeting segments (parts of a meeting agenda)
CREATE TABLE segments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meeting_id UUID REFERENCES meetings(id) NOT NULL,
    attendee_id UUID REFERENCES attendees(id),
    type TEXT NOT NULL,
    start_time TIME NOT NULL,
    duration INTERVAL NOT NULL,
    end_time TIME NOT NULL,
    title TEXT,
    content TEXT,
    related_segment_ids TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Awards table - stores awards given at meetings
CREATE TABLE awards (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meeting_id UUID REFERENCES meetings(id) NOT NULL,
    category TEXT NOT NULL,
    winner TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- INDEXES
-- =============================================

-- Ensures meeting numbers are unique within each type
CREATE UNIQUE INDEX unique_type_no_not_null ON meetings(type, no) WHERE no IS NOT NULL;

-- =============================================
-- ROW LEVEL SECURITY POLICIES
-- =============================================

-- Enable RLS on all tables
ALTER TABLE members ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendees ENABLE ROW LEVEL SECURITY;
ALTER TABLE meetings ENABLE ROW LEVEL SECURITY;
ALTER TABLE segments ENABLE ROW LEVEL SECURITY;

-- Members table policies
CREATE POLICY "Members can read own data"
  ON members
  FOR SELECT
  TO authenticated
  USING (auth.uid() = id);

CREATE POLICY "Members can update own data"
  ON members
  FOR UPDATE
  TO authenticated
  USING (auth.uid() = id);

-- Attendees table policies
CREATE POLICY "Members can view attendees"
ON attendees FOR SELECT
TO authenticated
USING (true);

CREATE POLICY "Members can create attendees"
ON attendees FOR INSERT
TO authenticated
WITH CHECK (true);

CREATE POLICY "Members can update attendees"
ON attendees FOR UPDATE
TO authenticated
USING (true);

CREATE POLICY "Members can delete attendees"
ON attendees FOR DELETE
TO authenticated
USING (true);

-- Meetings table policies
CREATE POLICY "Members can view meetings"
ON meetings FOR SELECT
TO authenticated
USING (true);

CREATE POLICY "Non-members can only view published meetings"
ON meetings
FOR SELECT
TO anon
USING (status = 'published');

CREATE POLICY "Members can create meetings"
ON meetings FOR INSERT
TO authenticated
WITH CHECK (true);

CREATE POLICY "Members can update meetings"
ON meetings FOR UPDATE
TO authenticated
USING (true);

CREATE POLICY "Manager or admin can delete meetings"
ON meetings FOR DELETE
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM attendees
        WHERE attendees.id = meetings.manager_id
        AND attendees.member_id = auth.uid()
    )
    OR is_admin(auth.uid())
);

-- Segments table policies
CREATE POLICY "Members can view segments"
ON segments FOR SELECT
TO authenticated
USING (true);

CREATE POLICY "Members can create segments"
ON segments FOR INSERT
TO authenticated
WITH CHECK (
    EXISTS (
        SELECT 1 FROM meetings
        WHERE meetings.id = meeting_id
    )
);

CREATE POLICY "Members can update segments"
ON segments FOR UPDATE
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM meetings
        WHERE meetings.id = meeting_id
    )
);

CREATE POLICY "Members can delete segments"
ON segments FOR DELETE
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM meetings
        WHERE meetings.id = meeting_id
    )
);

-- Awards table policies
CREATE POLICY "Members can view awards"
ON awards FOR SELECT
TO authenticated
USING (true);

CREATE POLICY "Members can create awards"
ON awards FOR INSERT
TO authenticated
WITH CHECK (
    EXISTS (
        SELECT 1 FROM meetings
        WHERE meetings.id = meeting_id
    )
);

CREATE POLICY "Members can update awards"
ON awards FOR UPDATE
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM meetings
        WHERE meetings.id = meeting_id
    )
);

CREATE POLICY "Members can delete awards"
ON awards FOR DELETE
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM meetings
        WHERE meetings.id = meeting_id
    )
);


-- =============================================
-- FUNCTIONS & TRIGGERS
-- =============================================

-- Function to check if a user is an admin
CREATE OR REPLACE FUNCTION is_admin(user_id UUID)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM members
        WHERE id = user_id
        AND is_admin = true
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to check if a user has permission to delete a meeting
CREATE OR REPLACE FUNCTION can_delete_meeting(meeting_id UUID)
RETURNS BOOLEAN AS $$
BEGIN
    -- This function explicitly checks the same conditions as the RLS policy
    RETURN EXISTS (
        SELECT 1 FROM meetings m
        WHERE m.id = meeting_id
        AND (
            -- Check if user is the manager
            EXISTS (
                SELECT 1 FROM attendees a
                WHERE a.id = m.manager_id
                AND a.member_id = auth.uid()
            )
            -- Or check if user is admin
            OR is_admin(auth.uid())
        )
    );
END;
$$ LANGUAGE plpgsql SECURITY INVOKER;

-- Function to handle new member creation on signup
CREATE OR REPLACE FUNCTION handle_new_member()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO members (id, username, full_name)
  VALUES (
    new.id,
    new.raw_user_meta_data->>'username',
    new.raw_user_meta_data->>'full_name'
  );
  RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger to create member on signup
CREATE OR REPLACE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW
  EXECUTE FUNCTION handle_new_member();

-- =============================================
-- POTENTIAL FUTURE CHANGES
-- =============================================

-- Add index on meetings status for faster filtering if needed
-- CREATE INDEX idx_meetings_status ON meetings(status);
