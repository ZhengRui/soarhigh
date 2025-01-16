import { MeetingCard } from './MeetingCard';
import { meetings } from './meetings';

export default function MeetingsPage() {
  return (
    <div className='min-h-screen bg-[#F9FAFB] py-12'>
      <div className='container max-w-4xl mx-auto px-4'>
        <h1 className='text-4xl font-bold text-[#1F2937] mb-4'>
          Recent Meetings
        </h1>
        <p className='text-[#6B7280] mb-8'>
          Join our weekly meetings to practice and improve your public speaking
          skills.
        </p>
        <div className='space-y-6'>
          {meetings.map((meeting, index) => (
            <MeetingCard key={index} {...meeting} />
          ))}
        </div>
      </div>
    </div>
  );
}
