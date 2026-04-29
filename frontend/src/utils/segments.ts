import { SegmentIF } from '../interfaces';
import {
  BaseSegment,
  SEGMENT_TYPE_MAP,
  SegmentParams,
} from './defaultSegments';

/**
 * Build the right BaseSegment subclass for a given type string.
 *
 * Routes "Prepared Speech [N]" to PreparedSpeechSegment, "Prepared Speech [N]
 * Evaluation" to PreparedSpeechEvalSegment, anything else in SEGMENT_TYPE_MAP
 * to its registered subclass, and unknown types to CustomSegment with the
 * incoming type preserved. Numbered variants ("Prepared Speech 2") are
 * preserved by overwriting `.type` after construction since the constructor
 * defaults to the bare name when no `speechNumber` is passed.
 *
 * Used both when hydrating saved meetings (`convertSegmentsToBaseSegments`)
 * and when applying agent agenda snapshots — without this, the snapshot path
 * fell back to plain `BaseSegment` and lost subclass-specific UI config
 * (`role_taker_config`, `title_config`, `content_config`).
 */
export function instantiateSegmentByType(
  type: string,
  params: SegmentParams
): BaseSegment {
  if (type.startsWith('Prepared Speech') && !type.includes('Evaluation')) {
    const seg = new SEGMENT_TYPE_MAP['Prepared Speech'](params);
    seg.type = type;
    return seg;
  }
  if (type.startsWith('Prepared Speech') && type.includes('Evaluation')) {
    const seg = new SEGMENT_TYPE_MAP['Prepared Speech Evaluation'](params);
    seg.type = type;
    return seg;
  }
  const SegmentClass = SEGMENT_TYPE_MAP[type as keyof typeof SEGMENT_TYPE_MAP];
  if (SegmentClass) {
    return new SegmentClass(params);
  }
  const fallback = new SEGMENT_TYPE_MAP['Custom segment'](params);
  fallback.type = type;
  return fallback;
}

/**
 * Converts API segments to BaseSegment for use with MeetingForm
 * @param segments Segments returned from the API
 * @returns BaseSegment instances compatible with MeetingForm
 */
export function convertSegmentsToBaseSegments(
  segments: SegmentIF[]
): BaseSegment[] {
  return segments.map((segment) => {
    const baseSegment = instantiateSegmentByType(segment.type, {
      id: segment.id,
      start_time: segment.start_time,
      duration: segment.duration,
      related_segment_ids: segment.related_segment_ids || '',
    });
    if (segment.role_taker) baseSegment.role_taker = segment.role_taker;
    if (segment.title) baseSegment.title = segment.title;
    if (segment.content) baseSegment.content = segment.content;
    return baseSegment;
  });
}
