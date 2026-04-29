import { AttendeeIF, MeetingIF, UserIF } from '@/interfaces';
import { BaseSegment } from '@/utils/defaultSegments';
import { instantiateSegmentByType } from '@/utils/segments';
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
 *
 * Phase B: `role_taker` ships as the structured `{id?, name, member_id}` (or
 * `null` when unset), so the backend preserves DB-authoritative `member_id`
 * end-to-end. The route's render layer no longer has to guess membership
 * against a static `CLUB_MEMBERS` list — `member_id` IS the answer.
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
      const role_taker = s.role_taker?.name
        ? {
            id: s.role_taker.id,
            name: s.role_taker.name,
            member_id: s.role_taker.member_id ?? '',
          }
        : null;
      return {
        id: s.id,
        type: s.type,
        start_time: s.start_time,
        duration: parseInt(s.duration, 10) || 0,
        role_taker,
        buffer_before,
        // Phase 3: send segment detail through to the agent. Pre-Phase-3 the
        // agent never saw these so any tool that mutated a segment (set_role,
        // set_duration, …) would silently drop the title / content when the
        // agenda_after came back.
        title: s.title ?? '',
        content: s.content ?? '',
        related_segment_ids: s.related_segment_ids ?? '',
      };
    }),
  };
}

/**
 * Apply the agent's returned agenda back onto the MeetingForm state.
 *
 * Phase B: each segment's `role_taker` arrives as a structured Attendee (or
 * `null`). When the backend already resolved `member_id` (typical: agent kept
 * a role taker that was on a sibling segment), we use it verbatim. When the
 * backend produced a fresh Attendee with empty `member_id` (typical: model
 * said "set Timer to Joyce" and the agenda didn't already have Joyce), the
 * frontend resolves `member_id` against the live members list — that's the
 * one place the frontend has more information than the backend, since the
 * backend doesn't (yet) know about live member UUIDs.
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

  // Adopt the snapshot's structured role_taker, falling back to the live
  // members list only when member_id is empty (i.e. backend couldn't
  // resolve). Guards against the edge case where a saved AttendeeIF has the
  // same name but a stale member_id by trusting the snapshot's value.
  const adoptRoleTaker = (
    raw: AgendaSnapshot['segments'][number]['role_taker'],
    fallback?: AttendeeIF
  ): AttendeeIF | undefined => {
    if (!raw || !raw.name) return undefined;
    if (raw.member_id) {
      return {
        id: raw.id ?? raw.member_id,
        name: raw.name,
        member_id: raw.member_id,
      };
    }
    return resolveAttendee(raw.name, fallback);
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
      cloned.role_taker = adoptRoleTaker(s.role_taker, existing.role_taker);
      // Phase 3: snapshot is authoritative for segment detail too. The
      // agent now carries title / content / related_segment_ids through
      // `meeting_to_agenda` and clone / preview projections, so any change
      // (or no-change) the agent expressed is what we adopt. Pre-Phase-3
      // we relied on the prototype clone preserving these — which was
      // correct only when the agent didn't touch them, and silently lossy
      // on every wholesale replace (clone / create-from-text).
      cloned.title = s.title ?? '';
      cloned.content = s.content ?? '';
      cloned.related_segment_ids = s.related_segment_ids ?? '';
      return cloned;
    }
    // New segment from the agent — wholesale-replace paths (clone /
    // create_from_text / create_from_image) allocate fresh UUIDs server-side
    // so every segment lands here, and add_segment also takes this path.
    // Route to the typed subclass so role_taker_config / title_config /
    // content_config match the segment kind; falling back to plain
    // BaseSegment leaves Prepared Speech / Table Topic Session / Custom
    // rows with the wrong inputs and placeholders.
    const fresh = instantiateSegmentByType(s.type, {
      id: s.id,
      start_time: s.start_time,
      duration: String(s.duration),
      related_segment_ids: s.related_segment_ids ?? '',
    });
    fresh.role_taker = adoptRoleTaker(s.role_taker);
    fresh.title = s.title ?? '';
    fresh.content = s.content ?? '';
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
    // Text meta fields treat `null` as an explicit clear signal — the
    // backend emits null when the agent runs `set_meta(field="theme", "")`
    // (apply_set_meta converts empty string to None, which serializes to
    // null). Without this branch the form silently keeps the previous
    // value and the user's clear request is dropped.
    theme:
      snapshot.meta.theme === null
        ? ''
        : typeof snapshot.meta.theme === 'string'
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
      snapshot.meta.location === null
        ? ''
        : typeof snapshot.meta.location === 'string'
          ? snapshot.meta.location
          : prev.location,
    introduction:
      snapshot.meta.introduction === null
        ? ''
        : typeof snapshot.meta.introduction === 'string'
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
