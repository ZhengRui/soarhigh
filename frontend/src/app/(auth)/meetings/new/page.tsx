'use client';

import React, { useState } from 'react';
import { FileImage, FileSpreadsheet, FileText } from 'lucide-react';
import { MeetingFromTemplate } from './MeetingFromTemplate';
import { MeetingFromImage } from './MeetingFromImage';
import { MeetingFromText } from './MeetingFromText';

export default function CreateMeeting() {
  const [activeTab, setActiveTab] = useState<'template' | 'image' | 'text'>(
    'template'
  );

  return (
    <div className='min-h-screen bg-gray-50 py-12'>
      <div className='container max-w-4xl mx-auto px-4'>
        <h1 className='text-3xl sm:text-4xl font-bold text-gray-900 mb-2'>
          Create New Meeting
        </h1>
        <p className='text-sm text-gray-600 mb-6'>
          Choose how you want to create your meeting
        </p>

        {/* Creation Method Tabs */}
        <div className='flex flex-col xs:flex-row gap-1.5 xs:gap-4 mb-6'>
          <button
            onClick={() => setActiveTab('template')}
            className={`flex items-center gap-2 px-4 py-2 rounded-md border transition-all duration-200 text-sm ${
              activeTab === 'template'
                ? 'border-blue-600 bg-blue-50 text-blue-700'
                : 'border-gray-200 hover:border-gray-300 text-gray-600 hover:bg-gray-50'
            }`}
          >
            <FileSpreadsheet className='w-4 h-4' />
            <span className='font-medium'>Use Template</span>
          </button>

          <button
            onClick={() => setActiveTab('image')}
            className={`flex items-center gap-2 px-4 py-2 rounded-md border transition-all duration-200 text-sm ${
              activeTab === 'image'
                ? 'border-blue-600 bg-blue-50 text-blue-700'
                : 'border-gray-200 hover:border-gray-300 text-gray-600 hover:bg-gray-50'
            }`}
          >
            <FileImage className='w-4 h-4' />
            <span className='font-medium'>Upload Agenda Image</span>
          </button>

          <button
            onClick={() => setActiveTab('text')}
            className={`flex items-center gap-2 px-4 py-2 rounded-md border transition-all duration-200 text-sm ${
              activeTab === 'text'
                ? 'border-blue-600 bg-blue-50 text-blue-700'
                : 'border-gray-200 hover:border-gray-300 text-gray-600 hover:bg-gray-50'
            }`}
          >
            <FileText className='w-4 h-4' />
            <span className='font-medium'>Use Text</span>
          </button>
        </div>

        {/* Content based on selected tab */}
        <div className='bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden'>
          {activeTab === 'template' ? (
            <MeetingFromTemplate />
          ) : activeTab === 'image' ? (
            <MeetingFromImage />
          ) : (
            <MeetingFromText />
          )}
        </div>
      </div>
    </div>
  );
}
