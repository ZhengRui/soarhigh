import { AttendeeIF, MeetingIF, UserIF } from '@/interfaces';
import { BaseSegment } from '@/utils/defaultSegments';
import { AgendaSnapshot } from './types';

type MeetingFormState = Omit<MeetingIF, 'segments'> & {
  segments: BaseSegment[];
};

/**
 * Build the agenda snapshot that the agent sees on each turn.
 * role_taker is flattened to a plain string (the agent works with names, not
 * member records).
 */
export function buildAgendaSnapshot(meeting: MeetingFormState): AgendaSnapshot {
  return {
    meta: {
      no: meeting.no ?? null,
      type: meeting.type ?? null,
      theme: meeting.theme ?? null,
      manager: meeting.manager?.name ?? null,
      date: meeting.date ?? null,
      start_time: meeting.start_time ?? null,
      end_time: meeting.end_time ?? null,
      location: meeting.location ?? null,
      introduction: meeting.introduction ?? null,
    },
    segments: meeting.segments.map((s) => ({
      id: s.id,
      type: s.type,
      start_time: s.start_time,
      duration: parseInt(s.duration, 10) || 0,
      role_taker: s.role_taker?.name ?? '',
      buffer_before: 0, // frontend doesn't track this yet — Phase 4
    })),
  };
}

/**
 * Apply the agent's returned agenda back onto the MeetingForm state.
 *
 * Map name -> AttendeeIF using the members list. Unknown names become guest
 * attendees with empty member_id (the existing agenda flow already allows this).
 */
export function applyAgendaSnapshot(
  prev: MeetingFormState,
  snapshot: AgendaSnapshot,
  members: UserIF[]
): MeetingFormState {
  const membersByName = new Map(
    members.map((m) => [m.full_name.toLowerCase(), m])
  );
  const resolveAttendee = (name: string): AttendeeIF | undefined => {
    if (!name) return undefined;
    const match = membersByName.get(name.toLowerCase());
    if (match) {
      return { id: match.uid, name: match.full_name, member_id: match.uid };
    }
    // First-name heuristic: "Rui" -> "Rui Zheng" if unique.
    const firstNameMatches = members.filter(
      (m) => m.full_name.split(' ')[0].toLowerCase() === name.toLowerCase()
    );
    if (firstNameMatches.length === 1) {
      const m = firstNameMatches[0];
      return { id: m.uid, name: m.full_name, member_id: m.uid };
    }
    // Fall back to guest (no member_id).
    return { name, member_id: '' };
  };

  const nextSegments: BaseSegment[] = snapshot.segments.map((s) => {
    const existing = prev.segments.find((p) => p.id === s.id);
    if (existing) {
      // Mutate in-place on a clone to preserve any instance-specific fields
      // (title_config, content_config, etc.) that BaseSegment subclasses set.
      const cloned = Object.assign(
        Object.create(Object.getPrototypeOf(existing)),
        existing
      );
      cloned.type = s.type;
      cloned.start_time = s.start_time;
      cloned.duration = String(s.duration);
      cloned.role_taker = resolveAttendee(s.role_taker);
      return cloned;
    }
    // New segment inserted by the agent (via add_segment). No prototype template
    // available; build a plain BaseSegment instance.
    const fresh = new BaseSegment({
      id: s.id,
      start_time: s.start_time,
      duration: String(s.duration),
    });
    fresh.type = s.type;
    fresh.role_taker = resolveAttendee(s.role_taker);
    return fresh;
  });

  return {
    ...prev,
    type:
      typeof snapshot.meta.type === 'string' ? snapshot.meta.type : prev.type,
    theme:
      typeof snapshot.meta.theme === 'string'
        ? snapshot.meta.theme
        : prev.theme,
    date:
      typeof snapshot.meta.date === 'string' ? snapshot.meta.date : prev.date,
    start_time:
      typeof snapshot.meta.start_time === 'string'
        ? snapshot.meta.start_time
        : prev.start_time,
    end_time:
      typeof snapshot.meta.end_time === 'string'
        ? snapshot.meta.end_time
        : prev.end_time,
    location:
      typeof snapshot.meta.location === 'string'
        ? snapshot.meta.location
        : prev.location,
    introduction:
      typeof snapshot.meta.introduction === 'string'
        ? snapshot.meta.introduction
        : prev.introduction,
    // Don't round-trip meta.manager through the snapshot — it's a name-only
    // flatten and we'd lose the member_id. Manager changes via chat are not a
    // common case; if the agent sets it, it'll come as a name string on the
    // next snapshot anyway.
    segments: nextSegments,
  };
}
