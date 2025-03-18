'use client';

import React, { useState } from 'react';
import { saveAs } from 'file-saver';
import { createWorkbook } from './workbookUtils';

const AgendaExcelGenerator: React.FC = () => {
  const [isGenerating, setIsGenerating] = useState(false);
  const [isReady, setIsReady] = useState(false);

  // Function to generate and download Excel file
  const generateExcel = async () => {
    setIsGenerating(true);
    setIsReady(false);

    try {
      const { workbook } = await createWorkbook();

      // Generate Excel file as a buffer
      const buffer = await workbook.xlsx.writeBuffer();

      // Create a Blob from the buffer
      const blob = new Blob([buffer], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      });

      // Save the file using FileSaver
      saveAs(blob, 'SoarhighMeetingAgenda.xlsx');

      setIsReady(true);
    } catch (error) {
      console.error('Error generating Excel file:', error);
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className='flex flex-col items-center p-6 bg-white rounded-lg shadow-md max-w-4xl mx-auto my-8'>
      <h1 className='text-2xl font-bold mb-6'>
        Toastmasters Meeting Agenda Generator
      </h1>

      <div className='w-full mb-6'>
        <p className='text-gray-700 mb-4'>
          This component generates an Excel file with the Toastmasters meeting
          agenda. Currently implemented: Opening/Intro, Evaluation, and
          Facilitators&apos; Report sections.
        </p>
      </div>

      <div className='flex gap-4 mb-6'>
        <button
          onClick={generateExcel}
          disabled={isGenerating}
          className='px-6 py-3 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 disabled:opacity-50 transition-colors'
        >
          {isGenerating ? 'Generating...' : 'Download Excel File'}
        </button>
      </div>

      {isReady && (
        <div className='mt-2 text-green-600 font-semibold'>
          Excel file downloaded successfully!
        </div>
      )}

      <div className='mt-8 text-sm text-gray-500'>
        <p>
          Note: This uses the ExcelJS library to generate the file in the
          browser and FileSaver.js to download it.
        </p>
      </div>
    </div>
  );
};

export default AgendaExcelGenerator;
