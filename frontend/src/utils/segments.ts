import { SegmentIF } from '../interfaces';
import { BaseSegment, SEGMENT_TYPE_MAP } from '../app/(auth)/meetings/default';

/**
 * Converts API segments to BaseSegment for use with MeetingForm
 * @param segments Segments returned from the API
 * @returns BaseSegment instances compatible with MeetingForm
 */
export function convertSegmentsToBaseSegments(
  segments: SegmentIF[]
): BaseSegment[] {
  return segments.map((segment) => {
    const params = {
      id: segment.id,
      start_time: segment.start_time,
      duration: segment.duration,
      related_segment_ids: segment.related_segment_ids || '',
    };

    // Check if it's a prepared speech (which might have a number)
    if (
      segment.type.startsWith('Prepared Speech') &&
      !segment.type.includes('Evaluation')
    ) {
      const baseSegment = new SEGMENT_TYPE_MAP['Prepared Speech'](params);
      if (segment.role_taker) baseSegment.role_taker = segment.role_taker;
      if (segment.title) baseSegment.title = segment.title;
      if (segment.content) baseSegment.content = segment.content;
      return baseSegment;
    }

    // Check if it's a prepared speech evaluation
    if (
      segment.type.startsWith('Prepared Speech') &&
      segment.type.includes('Evaluation')
    ) {
      const baseSegment = new SEGMENT_TYPE_MAP['Prepared Speech Evaluation'](
        params
      );
      if (segment.role_taker) baseSegment.role_taker = segment.role_taker;
      if (segment.title) baseSegment.title = segment.title;
      if (segment.content) baseSegment.content = segment.content;
      return baseSegment;
    }

    // For other segment types, look up in the map
    const SegmentClass =
      SEGMENT_TYPE_MAP[segment.type as keyof typeof SEGMENT_TYPE_MAP];

    // If we found a matching class, use it, otherwise create a custom segment
    if (SegmentClass) {
      const baseSegment = new SegmentClass(params);
      if (segment.role_taker) baseSegment.role_taker = segment.role_taker;
      if (segment.title) baseSegment.title = segment.title;
      if (segment.content) baseSegment.content = segment.content;
      return baseSegment;
    } else {
      // Use CustomSegment as fallback
      const baseSegment = new SEGMENT_TYPE_MAP['Custom segment'](params);
      baseSegment.type = segment.type;
      if (segment.role_taker) baseSegment.role_taker = segment.role_taker;
      if (segment.title) baseSegment.title = segment.title;
      if (segment.content) baseSegment.content = segment.content;
      return baseSegment;
    }
  });
}
