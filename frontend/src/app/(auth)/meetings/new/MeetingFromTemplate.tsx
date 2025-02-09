import React, { useState } from 'react';
import { FileText, Presentation, Hammer, ArrowRight } from 'lucide-react';
import {
  DEFAULT_REGULAR_MEETING,
  DEFAULT_WORKSHOP_MEETING,
  DEFAULT_CUSTOM_MEETING,
  BaseSegment,
} from '../default';
import { v4 as uuidv4 } from 'uuid';
import { MeetingForm } from '../MeetingForm';

const transformSegmentsWithUUID = (segments: BaseSegment[]): BaseSegment[] => {
  // Create a mapping of old IDs to new UUIDs
  const idMap = new Map<string, string>();

  // First pass: generate new IDs
  segments.forEach((segment) => {
    const newId = uuidv4();
    idMap.set(segment.segment_id, newId);
    segment.segment_id = newId;
  });

  // Second pass: update related_segment_ids
  segments.forEach((segment) => {
    if (segment.related_segment_ids) {
      segment.related_segment_ids = segment.related_segment_ids
        .split(',')
        .map((id) => idMap.get(id) || '')
        .join(',');
    }
  });

  return segments;
};

const MEETING_TEMPLATES = [
  {
    title: 'Regular Meeting',
    description:
      'Standard Toastmasters meeting format with prepared speeches, table topics, and evaluations.',
    icon: <FileText className='w-6 h-6' />,
    meeting: {
      ...DEFAULT_REGULAR_MEETING,
      segments: transformSegmentsWithUUID(DEFAULT_REGULAR_MEETING.segments),
    },
  },
  {
    title: 'Workshop Meeting',
    description:
      'Focused learning session with interactive exercises and group activities.',
    icon: <Presentation className='w-6 h-6' />,
    meeting: {
      ...DEFAULT_WORKSHOP_MEETING,
      segments: transformSegmentsWithUUID(DEFAULT_WORKSHOP_MEETING.segments),
    },
  },
  {
    title: 'Custom Meeting',
    description: 'Create a custom meeting with your own segments.',
    icon: <Hammer className='w-6 h-6' />,
    meeting: {
      ...DEFAULT_CUSTOM_MEETING,
      segments: transformSegmentsWithUUID(DEFAULT_CUSTOM_MEETING.segments),
    },
  },
] as const;

export function MeetingFromTemplate() {
  const [selectedTemplate, setSelectedTemplate] = useState<
    (typeof MEETING_TEMPLATES)[number] | null
  >(null);

  const handleTemplateSelect = (
    template: (typeof MEETING_TEMPLATES)[number]
  ) => {
    setSelectedTemplate(template);
  };

  if (!selectedTemplate) {
    return (
      <div className='p-6'>
        <div>
          <h2 className='text-2xl font-semibold text-gray-900'>
            Select a Template
          </h2>
          <p className='mt-1 text-sm text-gray-600'>
            Choose a meeting template to get started
          </p>
        </div>

        <div className='mt-6 grid gap-4'>
          {MEETING_TEMPLATES.map((template) => (
            <button
              key={template.meeting.meeting_type}
              onClick={() => handleTemplateSelect(template)}
              className='w-full text-left p-4 rounded-lg border border-gray-200 hover:border-blue-300 bg-white hover:bg-blue-50 transition-all duration-200 group'
            >
              <div className='flex items-start gap-4'>
                <div className='p-2 rounded-lg bg-gradient-to-br from-blue-50 to-purple-50 border border-blue-100 group-hover:from-blue-100 group-hover:to-purple-100 transition-colors'>
                  {template.icon}
                </div>
                <div className='flex-1'>
                  <h3 className='text-lg font-medium text-gray-900 flex items-center gap-2'>
                    {template.title}
                    <ArrowRight className='w-4 h-4 opacity-0 -translate-x-2 group-hover:opacity-100 group-hover:translate-x-0 transition-all' />
                  </h3>
                  <p className='mt-1 text-sm text-gray-600'>
                    {template.description}
                  </p>
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <MeetingForm
      key={selectedTemplate.title}
      initFormData={selectedTemplate.meeting}
    />
  );
}
