import React, { useState } from 'react';
import { Upload, Loader2 } from 'lucide-react';
import { toast } from 'react-hot-toast';
import { MeetingForm } from '../MeetingForm';
import { parseMeetingFromImage } from '../../../../utils/meeting';
import { MeetingIF } from '../../../../interfaces';
import { convertSegmentsToBaseSegments } from '../../../../utils/segments';
import { convertHumanReadableDateToISO } from '../../../../utils/utils';

export const MeetingFromImage = () => {
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [parsedMeeting, setParsedMeeting] = useState<MeetingIF | null>(null);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith('image/')) {
      setSelectedFile(file);
    } else {
      toast.error('Please upload an image file');
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) return;

    setIsProcessing(true);
    try {
      const parsedData = await parseMeetingFromImage(selectedFile);

      // Convert date from human-readable format to ISO format if needed
      if (parsedData.date) {
        parsedData.date = convertHumanReadableDateToISO(parsedData.date);
      }

      setParsedMeeting(parsedData);
      toast.success('Image processed successfully');
    } catch (error) {
      console.error('Error processing image:', error);
      toast.error(
        error instanceof Error ? error.message : 'Failed to process image'
      );
    } finally {
      setIsProcessing(false);
    }
  };

  // If we have a parsed meeting, render the MeetingForm with the data
  if (parsedMeeting) {
    // Convert SegmentIF[] to BaseSegment[] for the MeetingForm
    const formData = {
      ...parsedMeeting,
      segments: convertSegmentsToBaseSegments(parsedMeeting.segments || []),
    };

    return (
      <div className='mt-4'>
        <div className='bg-blue-50 p-4 mb-6 rounded-md'>
          <h3 className='text-sm font-medium text-blue-800'>
            Meeting parsed from image
          </h3>
          <p className='text-xs text-blue-600 mt-1'>
            You can edit the meeting details below before saving
          </p>
        </div>
        <MeetingForm initFormData={formData} mode='create' />
      </div>
    );
  }

  // Otherwise, render the image upload form
  return (
    <form onSubmit={handleSubmit} className='p-6'>
      <div>
        <h2 className='text-2xl font-semibold text-gray-900'>
          Create from Image
        </h2>
        <p className='mt-1 text-sm text-gray-600'>
          Upload an agenda image to automatically create a meeting
        </p>
      </div>

      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`mt-6 relative border-2 border-dashed rounded-lg p-8 text-center ${
          isDragging
            ? 'border-blue-500 bg-blue-50'
            : 'border-gray-300 hover:border-gray-400'
        }`}
      >
        <input
          type='file'
          accept='image/*'
          onChange={handleFileSelect}
          className='absolute inset-0 w-full h-full opacity-0 cursor-pointer'
        />
        <div className='space-y-3'>
          <div className='flex justify-center'>
            <Upload
              className={`w-10 h-10 ${isDragging ? 'text-blue-500' : 'text-gray-400'}`}
            />
          </div>
          <div>
            <p className='text-sm font-medium text-gray-700'>
              {selectedFile
                ? selectedFile.name
                : 'Drop your image here, or click to select'}
            </p>
            <p className='text-xs text-gray-500 mt-1'>PNG, JPG up to 10MB</p>
          </div>
        </div>
      </div>

      {selectedFile && (
        <div className='mt-6'>
          <button
            type='submit'
            disabled={isProcessing}
            className='w-full flex justify-center items-center gap-2 py-2 px-4 border border-transparent rounded-md text-sm font-medium text-white bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-70'
          >
            {isProcessing ? (
              <>
                <Loader2 className='w-4 h-4 animate-spin' />
                Processing...
              </>
            ) : (
              'Process Image'
            )}
          </button>
        </div>
      )}
    </form>
  );
};
