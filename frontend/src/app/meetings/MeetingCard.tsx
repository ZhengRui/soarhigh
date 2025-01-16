'use client';

import React, { useState } from 'react';
import { ChevronDown, ChevronUp, Clock, MapPin, Trophy } from 'lucide-react';

interface Award {
  category: string;
  winner: string;
}

interface Segment {
  segment_id: string;
  segment_type: string;
  start_time: string;
  duration: string;
  end_time: string;
  role_taker: string;
  title?: string;
  content?: string;
}

interface MeetingCardProps {
  meeting_type: string;
  theme: string;
  meeting_manager: string;
  date: string;
  start_time: string;
  end_time: string;
  location: string;
  segments: Segment[];
}

export const MeetingCard: React.FC<MeetingCardProps> = ({
  meeting_type,
  theme,
  meeting_manager,
  date,
  start_time,
  end_time,
  location,
  segments,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  // This is a placeholder intro - will be added to the data model later
  const meetingIntro =
    "Join us for an engaging Toastmasters session where we'll explore various aspects of public speaking. This meeting promises to be an enriching experience with prepared speeches, impromptu speaking sessions, and constructive evaluations. Whether you're a seasoned speaker or just starting out, you'll find valuable opportunities to grow.";

  // Mock awards data - will be added to the meeting data model later
  const mockAwards: Award[] = [
    { category: 'Best Prepared Speaker', winner: 'Frank Chen' },
    { category: 'Best Host', winner: 'Jessica Wang' },
    { category: 'Best Table Topic Speaker', winner: 'Emily Liu' },
    { category: 'Best Facilitator', winner: 'Max Zhang' },
    { category: 'Best Evaluator', winner: 'Amanda Wu' },
    { category: 'Best Supporter', winner: 'Joyce Li' },
  ];

  // Check if the meeting date has passed
  const hasPassed = new Date(date) < new Date();

  return (
    <div className='bg-white rounded-xl shadow-lg overflow-hidden transition-all duration-200 ease-in-out hover:shadow-xl border border-[#e5e7eb]'>
      <div
        className='p-6 cursor-pointer'
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className='flex justify-between items-start mb-4'>
          <div>
            <span className='px-4 py-1.5 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-full text-sm font-medium'>
              {meeting_type}
            </span>
            <h2 className='text-2xl font-bold mt-3 text-gray-800'>{theme}</h2>
            <p className='text-gray-500 mt-1 text-sm'>
              Managed by {meeting_manager}
            </p>
          </div>
          {isExpanded ? (
            <ChevronUp className='w-5 h-5 text-gray-400' />
          ) : (
            <ChevronDown className='w-5 h-5 text-gray-400' />
          )}
        </div>

        <div className='flex flex-col gap-2 text-gray-500 text-sm'>
          <p className='flex items-center gap-2'>
            <Clock className='w-4 h-4' />
            {date} | {start_time} - {end_time}
          </p>
          <p className='flex items-center gap-2'>
            <MapPin className='min-w-4 min-h-4 w-4 h-4' />
            {location}
          </p>
        </div>

        <p className='mt-4 text-sm text-gray-500 leading-relaxed'>
          {meetingIntro}
        </p>

        {hasPassed && (
          <div className='mt-6 pt-6 border-t border-dashed border-gray-300'>
            <div className='flex items-center gap-2 mb-3'>
              <Trophy className='w-4 h-4 text-indigo-600' />
              <h3 className='text-sm font-semibold text-gray-800'>
                Meeting Awards
              </h3>
            </div>
            <div className='grid grid-cols-2 md:grid-cols-3 gap-4'>
              {mockAwards.map((award, index) => (
                <div key={index} className='text-sm'>
                  <p className='text-gray-500 font-medium'>{award.category}</p>
                  <p className='text-indigo-600'>{award.winner}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div
        className={`overflow-hidden transition-all duration-300 ease-in-out ${
          isExpanded ? 'max-h-[2000px] opacity-100' : 'max-h-0 opacity-0'
        }`}
      >
        <div className='p-6 border-t border-gray-300 bg-gradient-to-b from-white to-[#F9FAFB]'>
          <h3 className='text-lg font-semibold mb-4 text-gray-800'>
            Meeting Schedule
          </h3>
          <div className='space-y-4'>
            {segments.map((segment) => (
              <div key={segment.segment_id} className='flex gap-4 relative'>
                <div className='w-24 flex-shrink-0 flex flex-col items-start pt-0.5'>
                  <span className='text-sm font-medium text-indigo-600'>
                    {segment.start_time}
                  </span>
                  <span className='text-xs text-gray-500'>
                    {segment.duration}min
                  </span>
                </div>
                <div className='flex-grow'>
                  <div className='flex flex-col'>
                    <h4 className='font-medium text-gray-800'>
                      {segment.segment_type}
                    </h4>
                    <p className='text-sm text-gray-500'>
                      {segment.role_taker}
                      {segment.title && ` - ${segment.title}`}
                    </p>
                    {/* {segment.content && (
                      <p className='text-sm text-gray-500 mt-1'>
                        {segment.content}
                      </p>
                    )} */}
                  </div>
                </div>
                <div className='absolute left-24 top-0 bottom-0 w-0.5 bg-gradient-to-b from-indigo-600 to-purple-600 -z-10' />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
