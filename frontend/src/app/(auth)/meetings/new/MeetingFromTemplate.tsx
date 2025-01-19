import React, { useState } from 'react';
import { Calendar, Clock, MapPin, Users } from 'lucide-react';
import { MeetingIF, SegmentIF } from '@/interfaces';
import { DEFAULT_REGULAR_MEETING } from './default';
import { SegmentsEditor } from './SegmentsEditor';

const MEETING_TYPES = ['Regular', 'Workshop'] as const;

export function MeetingFromTemplate() {
  const [formData, setFormData] = useState<Partial<MeetingIF>>(
    DEFAULT_REGULAR_MEETING
  );

  const handleInputChange = (field: keyof MeetingIF, value: string) => {
    setFormData((prev: Partial<MeetingIF>) => ({ ...prev, [field]: value }));
  };

  const handleSegmentChange = (
    index: number,
    field: keyof SegmentIF,
    value: string
  ) => {
    setFormData((prev: Partial<MeetingIF>) => ({
      ...prev,
      segments: prev.segments?.map((segment, i) =>
        i === index ? { ...segment, [field]: value } : segment
      ),
    }));
  };

  const handleSegmentDelete = (index: number) => {
    setFormData((prev: Partial<MeetingIF>) => ({
      ...prev,
      segments: prev.segments?.filter((_, i) => i !== index),
    }));
  };

  const handleSegmentAdd = (index: number) => {
    setFormData((prev: Partial<MeetingIF>) => {
      const newSegments = [...(prev.segments || [])];
      const prevSegment = newSegments[index];

      // Calculate new start time based on previous segment
      let newStartTime = '';
      let newEndTime = '';
      if (prevSegment?.start_time && prevSegment?.duration) {
        const [hours, minutes] = prevSegment.start_time.split(':');
        const date = new Date();
        date.setHours(parseInt(hours), parseInt(minutes));
        date.setMinutes(date.getMinutes() + parseInt(prevSegment.duration));
        newStartTime = `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;

        date.setMinutes(date.getMinutes() + 7);
        newEndTime = `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
      }

      const newSegment: SegmentIF = {
        segment_id: `seg_${Date.now()}`,
        segment_type: 'Prepared Speech',
        start_time: newStartTime,
        duration: '7',
        end_time: newEndTime,
        role_taker: '',
      };
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
    'block w-full px-3 py-1.5 text-sm rounded-md border border-gray-300 text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-[0.5px] focus:ring-blue-500 focus:border-blue-500 transition-colors duration-200';
  const inputWithIconClasses =
    'block w-full pl-8 pr-3 py-1.5 text-sm rounded-md border border-gray-300 text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-[0.5px] focus:ring-blue-500 focus:border-blue-500 transition-colors duration-200';

  return (
    <form onSubmit={handleSubmit} className='p-6'>
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
        {formData.meeting_type === 'Regular' && formData.segments && (
          <div className='border-t pt-6'>
            <h3 className='text-lg font-medium text-gray-900 mb-4'>
              Meeting Schedule
            </h3>
            <SegmentsEditor
              segments={formData.segments}
              onSegmentChange={handleSegmentChange}
              onSegmentDelete={handleSegmentDelete}
              onSegmentAdd={handleSegmentAdd}
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
