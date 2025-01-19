import React, { useState } from 'react';
import { Upload } from 'lucide-react';

export const MeetingFromImage = () => {
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

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
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (selectedFile) {
      // TODO: Handle image upload and processing
      console.log('Processing image:', selectedFile);
    }
  };

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
            className='w-full flex justify-center py-2 px-4 border border-transparent rounded-md text-sm font-medium text-white bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500'
          >
            Process Image
          </button>
        </div>
      )}
    </form>
  );
};
