import { MeetingCard } from './MeetingCard';
import { meetings } from './meetings';
import { Plus } from 'lucide-react';
import Link from 'next/link';

export default function MeetingsPage() {
  return (
    <div className='min-h-screen bg-gray-50 py-12'>
      <div className='container max-w-4xl mx-auto px-4'>
        <div className='flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4 mb-8'>
          <div>
            <h1 className='text-3xl sm:text-4xl font-bold text-gray-900 mb-2 sm:mb-4'>
              Recent Meetings
            </h1>
            <p className='text-gray-600 text-sm sm:text-base'>
              Join our weekly meetings to practice and improve your public
              speaking skills.
            </p>
          </div>

          <Link
            href='/meetings/new'
            className='self-start sm:self-center inline-flex items-center gap-1.5 px-3 py-1.5 bg-gradient-to-r from-blue-600 to-purple-600 text-white text-sm rounded-md hover:from-blue-700 hover:to-purple-700 transition-all duration-200 shadow-sm hover:shadow-md whitespace-nowrap'
          >
            <Plus className='w-4 h-4' />
            <span className='font-medium'>Create Meeting</span>
          </Link>
        </div>
        <div className='space-y-6'>
          {meetings.map((meeting, index) => (
            <MeetingCard key={index} {...meeting} />
          ))}
        </div>
      </div>
    </div>
  );
}
