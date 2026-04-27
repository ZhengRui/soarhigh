import { AttendeeIF, MeetingIF, UserIF } from '@/interfaces';
import { BaseSegment } from '@/utils/defaultSegments';
import { AgendaSnapshot } from './types';

type MeetingFormState = Omit<MeetingIF, 'segments'> & {
  segments: BaseSegment[];
};

function parseHhmmToMinutes(hhmm: string): number {
  const parts = hhmm.split(':');
  const h = parseInt(parts[0] ?? '0', 10);
  const m = parseInt(parts[1] ?? '0', 10);
  if (isNaN(h) || isNaN(m)) return 0;
  return h * 60 + m;
}

/**
 * Build the agenda snapshot that the agent sees on each turn.
 * role_taker is flattened to a plain string (the agent works with names, not
 * member records).
 *
 * buffer_before is derived from the gap between each segment's start_time and
 * the previous segment's end_time. The frontend's BaseSegment doesn't carry a
 * buffer_before field, but templates can encode gaps implicitly via start_time
 * values (e.g. PS1 ends 20:20, PS2 starts 20:21 = a 1-min gap). Without this
 * derivation the agent sees every buffer as 0 and cannot manipulate those gaps,
 * AND any mutation would trigger the backend's recompute_start_times to wipe
 * out the implicit gap on the next tool call.
 */
export function buildAgendaSnapshot(meeting: MeetingFormState): AgendaSnapshot {
  const segs = meeting.segments;
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
    segments: segs.map((s, i) => {
      let buffer_before = 0;
      if (i > 0) {
        const prev = segs[i - 1];
        const prevStart = parseHhmmToMinutes(prev.start_time);
        const prevDuration = parseInt(prev.duration, 10) || 0;
        const curStart = parseHhmmToMinutes(s.start_time);
        const gap = curStart - (prevStart + prevDuration);
        buffer_before = Math.max(gap, 0);
      }
      return {
        id: s.id,
        type: s.type,
        start_time: s.start_time,
        duration: parseInt(s.duration, 10) || 0,
        role_taker: s.role_taker?.name ?? '',
        buffer_before,
      };
    }),
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
  const resolveAttendee = (
    name: string,
    fallback?: AttendeeIF
  ): AttendeeIF | undefined => {
    if (!name) return undefined;
    if (fallback?.name.toLowerCase() === name.toLowerCase()) {
      return fallback;
    }
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

  const normalizeNo = (value: unknown): number | undefined => {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string') {
      const parsed = parseInt(value, 10);
      return Number.isFinite(parsed) ? parsed : undefined;
    }
    return undefined;
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
      cloned.role_taker = resolveAttendee(s.role_taker, existing.role_taker);
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
    no:
      snapshot.meta.no === null
        ? undefined
        : snapshot.meta.no === undefined
          ? prev.no
          : normalizeNo(snapshot.meta.no),
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
    manager:
      snapshot.meta.manager === null
        ? undefined
        : typeof snapshot.meta.manager === 'string'
          ? resolveAttendee(snapshot.meta.manager, prev.manager)
          : prev.manager,
    segments: nextSegments,
  };
}
