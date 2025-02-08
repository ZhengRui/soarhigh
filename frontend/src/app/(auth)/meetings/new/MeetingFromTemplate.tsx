import React, { useState } from 'react';
import {
  Calendar,
  Clock,
  MapPin,
  Users,
  FileText,
  Presentation,
  Hammer,
  ArrowRight,
} from 'lucide-react';
import { MeetingIF } from '@/interfaces';
import {
  DEFAULT_REGULAR_MEETING,
  DEFAULT_WORKSHOP_MEETING,
  DEFAULT_CUSTOM_MEETING,
  BaseSegment,
  CustomSegment,
  SEGMENT_TYPE_MAP,
  SegmentParams,
} from './default';
import { SegmentsEditor, timeStringToMinutes } from './SegmentsEditor';
import { v4 as uuidv4 } from 'uuid';

const MEETING_TYPES = ['Regular', 'Workshop', 'Custom'] as const;

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

type MeetingTemplateType = Omit<MeetingIF, 'segments'> & {
  segments: BaseSegment[];
};

export function MeetingFromTemplate() {
  const [selectedTemplate, setSelectedTemplate] = useState<
    (typeof MEETING_TEMPLATES)[number] | null
  >(null);

  const [formData, setFormData] = useState<MeetingTemplateType>({
    meeting_type: '',
    theme: '',
    meeting_manager: '',
    date: '',
    start_time: '',
    end_time: '',
    location: '',
    introduction: '',
    segments: [],
  });

  const handleTemplateSelect = (
    template: (typeof MEETING_TEMPLATES)[number]
  ) => {
    setSelectedTemplate(template);
    setFormData({
      ...template.meeting,
      segments: template.meeting.segments.map((segment) => ({ ...segment })),
    });
  };

  const handleInputChange = (
    field: keyof MeetingTemplateType,
    value: string
  ) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const handleSegmentChange = (
    index: number,
    field: keyof BaseSegment,
    value: string
  ) => {
    setFormData((prev) => {
      const newSegments = [...prev.segments];

      if (field === 'segment_type') {
        if (value in SEGMENT_TYPE_MAP) {
          // Create new segment of the selected type
          const oldSegment = newSegments[index];
          const params = {
            segment_id: oldSegment.segment_id,
            start_time: oldSegment.start_time,
            duration: oldSegment.duration,
          };

          const SegmentClass =
            SEGMENT_TYPE_MAP[value as keyof typeof SEGMENT_TYPE_MAP];
          if (SegmentClass) {
            newSegments[index] = new (SegmentClass as new (
              params: SegmentParams
            ) => BaseSegment)(params);
          }
        } else {
          newSegments[index] = { ...newSegments[index], [field]: value };
        }
      } else {
        // Handle other field changes while preserving the class instance
        const segment = newSegments[index];
        (segment[field] as string) = value;
      }

      return { ...prev, segments: newSegments };
    });
  };

  const handleSegmentsShift = (
    startIndex: number,
    endIndex: number,
    startTime: string,
    duration: string
  ) => {
    setFormData((prev) => {
      const newSegments = [...prev.segments];
      const firstSegment = newSegments[startIndex];

      // Calculate time shift
      const oldStartMinutes = timeStringToMinutes(firstSegment.start_time);
      const newStartMinutes = timeStringToMinutes(startTime);
      const startTimeShift = newStartMinutes - oldStartMinutes;

      // Update duration shift
      const durationShift =
        parseInt(duration) - parseInt(firstSegment.duration);

      // Update first segment directly
      firstSegment.start_time = startTime;
      firstSegment.duration = duration;

      // Shift subsequent segments
      for (let i = startIndex + 1; i <= endIndex; i++) {
        const segment = newSegments[i];
        const currentStartMinutes = timeStringToMinutes(segment.start_time);
        const newStartMinutes =
          currentStartMinutes + startTimeShift + durationShift;
        const hours = Math.floor(newStartMinutes / 60);
        const minutes = newStartMinutes % 60;

        segment.start_time = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
      }

      return { ...prev, segments: newSegments };
    });
  };

  const handleSegmentDelete = (index: number) => {
    setFormData((prev) => {
      const segmentToDelete = prev.segments[index];
      const newSegments = prev.segments.filter((_, i) => i !== index);

      // Update related_segment_ids in remaining segments
      newSegments.forEach((segment) => {
        if (segment.related_segment_ids) {
          segment.related_segment_ids = segment.related_segment_ids
            .split(',')
            .filter((id) => id !== segmentToDelete.segment_id)
            .join(',');
        }
      });

      return { ...prev, segments: newSegments };
    });
  };

  const handleSegmentAdd = (index: number) => {
    setFormData((prev) => {
      const newSegments = [...prev.segments];
      const prevSegment = newSegments[index];

      // Calculate new start time based on previous segment
      let newStartTime = '';
      if (prevSegment?.start_time && prevSegment?.duration) {
        const [hours, minutes] = prevSegment.start_time.split(':');
        const date = new Date();
        date.setHours(parseInt(hours), parseInt(minutes));
        date.setMinutes(date.getMinutes() + parseInt(prevSegment.duration));
        newStartTime = `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
      }

      // Create new custom segment
      const newSegment = new CustomSegment({
        segment_id: uuidv4(),
        segment_type: 'New segment',
        start_time: newStartTime,
        duration: '5',
      });
      newSegments.splice(index + 1, 0, newSegment);
      return { ...prev, segments: newSegments };
    });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // TODO: Handle form submission
    console.log('Form submitted:', formData);
  };

  const inputClasses =
    'block w-full px-3 py-1.5 text-sm rounded-md border border-gray-300 text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-0 focus:ring-blue-500 focus:border-blue-500 transition-colors duration-200';
  const inputWithIconClasses =
    'block w-full pl-8 pr-3 py-1.5 text-sm rounded-md border border-gray-300 text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-0 focus:ring-blue-500 focus:border-blue-500 transition-colors duration-200';

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
    <form onSubmit={handleSubmit} className='px-6 pt-6 pb-60'>
      <div>
        <h2 className='text-2xl font-semibold text-gray-900'>
          Create from Template
        </h2>
        <p className='mt-1 text-sm text-gray-600'>
          Fill in the meeting details using our predefined template
        </p>
      </div>

      <div className='mt-6 space-y-6'>
        {/* Basic Information */}
        <div className='grid grid-cols-1 md:grid-cols-2 gap-6'>
          {/* Meeting Type */}
          <div>
            <label
              htmlFor='meeting_type'
              className='block text-sm font-medium text-gray-700 mb-1'
            >
              Meeting Type
            </label>
            <div className='relative'>
              <select
                id='meeting_type'
                value={formData.meeting_type}
                onChange={(e) =>
                  handleInputChange('meeting_type', e.target.value)
                }
                className={inputClasses}
              >
                {MEETING_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Theme */}
          <div>
            <label
              htmlFor='theme'
              className='block text-sm font-medium text-gray-700 mb-1'
            >
              Theme
            </label>
            <input
              type='text'
              id='theme'
              value={formData.theme}
              onChange={(e) => handleInputChange('theme', e.target.value)}
              placeholder='Enter meeting theme'
              className={inputClasses}
            />
          </div>

          {/* Meeting Manager */}
          <div>
            <label
              htmlFor='meeting_manager'
              className='block text-sm font-medium text-gray-700 mb-1'
            >
              Meeting Manager
            </label>
            <div className='relative'>
              <input
                type='text'
                id='meeting_manager'
                value={formData.meeting_manager}
                onChange={(e) =>
                  handleInputChange('meeting_manager', e.target.value)
                }
                placeholder='Enter manager name'
                className={inputWithIconClasses}
              />
              <Users className='absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400' />
            </div>
          </div>

          {/* Date */}
          <div>
            <label
              htmlFor='date'
              className='block text-sm font-medium text-gray-700 mb-1'
            >
              Date
            </label>
            <div className='relative'>
              <input
                type='date'
                id='date'
                value={formData.date}
                onChange={(e) => handleInputChange('date', e.target.value)}
                className={inputWithIconClasses}
              />
              <Calendar className='absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400' />
            </div>
          </div>

          {/* Start Time */}
          <div>
            <label
              htmlFor='start_time'
              className='block text-sm font-medium text-gray-700 mb-1'
            >
              Start Time
            </label>
            <div className='relative'>
              <input
                type='time'
                id='start_time'
                value={formData.start_time}
                onChange={(e) =>
                  handleInputChange('start_time', e.target.value)
                }
                className={inputWithIconClasses}
              />
              <Clock className='absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400' />
            </div>
          </div>

          {/* End Time */}
          <div>
            <label
              htmlFor='end_time'
              className='block text-sm font-medium text-gray-700 mb-1'
            >
              End Time
            </label>
            <div className='relative'>
              <input
                type='time'
                id='end_time'
                value={formData.end_time}
                onChange={(e) => handleInputChange('end_time', e.target.value)}
                className={inputWithIconClasses}
              />
              <Clock className='absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400' />
            </div>
          </div>

          {/* Location */}
          <div className='md:col-span-2'>
            <label
              htmlFor='location'
              className='block text-sm font-medium text-gray-700 mb-1'
            >
              Location
            </label>
            <div className='relative'>
              <input
                type='text'
                id='location'
                value={formData.location}
                onChange={(e) => handleInputChange('location', e.target.value)}
                placeholder='Enter meeting location'
                className={inputWithIconClasses}
              />
              <MapPin className='absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400' />
            </div>
          </div>
        </div>

        {/* Segments Editor */}
        {formData.segments && formData.segments.length > 0 && (
          <div className='border-t pt-6'>
            <h3 className='text-lg font-medium text-gray-900 mb-4'>
              Meeting Schedule
            </h3>
            <SegmentsEditor
              segments={formData.segments}
              onSegmentChange={handleSegmentChange}
              onSegmentDelete={handleSegmentDelete}
              onSegmentAdd={handleSegmentAdd}
              onSegmentsShift={handleSegmentsShift}
            />
          </div>
        )}

        {/* Submit Button */}
        <div className='pt-6 border-t'>
          <button
            type='submit'
            className='w-full flex justify-center py-2 px-4 border border-transparent rounded-md text-sm font-medium text-white bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500'
          >
            Create Meeting
          </button>
        </div>
      </div>
    </form>
  );
}
