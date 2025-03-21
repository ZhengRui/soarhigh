'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Brain, PlusCircle, Table2, Loader2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { planMeetingFromText } from '@/utils/meeting';

export const MeetingFromText = () => {
  const [inputText, setInputText] = useState('');
  const [outputJson, setOutputJson] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const outputRef = useRef<HTMLTextAreaElement>(null);
  const inputHandleRef = useRef<HTMLDivElement>(null);
  const outputHandleRef = useRef<HTMLDivElement>(null);

  const [isThinking, setIsThinking] = useState(false);

  useEffect(() => {
    // Handle input textarea resizing
    if (inputRef.current && inputHandleRef.current) {
      const textarea = inputRef.current;
      const handle = inputHandleRef.current;

      const handleMouseDown = (e: MouseEvent) => {
        e.preventDefault();
        const startY = e.clientY;
        const startHeight = textarea.offsetHeight;

        function onMouseMove(e: MouseEvent) {
          const newHeight = startHeight + (e.clientY - startY);
          if (newHeight > 100) {
            textarea.style.height = `${newHeight}px`;
          }
        }

        function onMouseUp() {
          document.removeEventListener('mousemove', onMouseMove);
          document.removeEventListener('mouseup', onMouseUp);
        }

        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
      };

      const handleTouchStart = (e: TouchEvent) => {
        e.preventDefault();
        const startY = e.touches[0].clientY;
        const startHeight = textarea.offsetHeight;

        function onTouchMove(e: TouchEvent) {
          const newHeight = startHeight + (e.touches[0].clientY - startY);
          if (newHeight > 100) {
            textarea.style.height = `${newHeight}px`;
          }
        }

        function onTouchEnd() {
          document.removeEventListener('touchmove', onTouchMove);
          document.removeEventListener('touchend', onTouchEnd);
        }

        document.addEventListener('touchmove', onTouchMove);
        document.addEventListener('touchend', onTouchEnd);
      };

      handle.addEventListener('mousedown', handleMouseDown as EventListener);
      handle.addEventListener('touchstart', handleTouchStart as EventListener);

      return () => {
        handle.removeEventListener(
          'mousedown',
          handleMouseDown as EventListener
        );
        handle.removeEventListener(
          'touchstart',
          handleTouchStart as EventListener
        );
      };
    }
  }, []);

  useEffect(() => {
    // Handle output textarea resizing
    if (outputRef.current && outputHandleRef.current) {
      const textarea = outputRef.current;
      const handle = outputHandleRef.current;

      const handleMouseDown = (e: MouseEvent) => {
        e.preventDefault();
        const startY = e.clientY;
        const startHeight = textarea.offsetHeight;

        function onMouseMove(e: MouseEvent) {
          const newHeight = startHeight + (e.clientY - startY);
          if (newHeight > 100) {
            textarea.style.height = `${newHeight}px`;
          }
        }

        function onMouseUp() {
          document.removeEventListener('mousemove', onMouseMove);
          document.removeEventListener('mouseup', onMouseUp);
        }

        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
      };

      const handleTouchStart = (e: TouchEvent) => {
        e.preventDefault();
        const startY = e.touches[0].clientY;
        const startHeight = textarea.offsetHeight;

        function onTouchMove(e: TouchEvent) {
          const newHeight = startHeight + (e.touches[0].clientY - startY);
          if (newHeight > 100) {
            textarea.style.height = `${newHeight}px`;
          }
        }

        function onTouchEnd() {
          document.removeEventListener('touchmove', onTouchMove);
          document.removeEventListener('touchend', onTouchEnd);
        }

        document.addEventListener('touchmove', onTouchMove);
        document.addEventListener('touchend', onTouchEnd);
      };

      handle.addEventListener('mousedown', handleMouseDown as EventListener);
      handle.addEventListener('touchstart', handleTouchStart as EventListener);

      return () => {
        handle.removeEventListener(
          'mousedown',
          handleMouseDown as EventListener
        );
        handle.removeEventListener(
          'touchstart',
          handleTouchStart as EventListener
        );
      };
    }
  }, []);

  const handleThinking = async (e: React.FormEvent) => {
    e.preventDefault();

    // Check if input text is empty (after trimming whitespace)
    if (!inputText.trim()) {
      return; // Return early if input is empty
    }

    setIsThinking(true);
    try {
      // Call the endpoint that accepts text data in the request body
      const meeting = await planMeetingFromText(inputText.trim());

      // Set the output JSON
      setOutputJson(JSON.stringify(meeting, null, 2));

      toast.success('Plan a meeting from text successfully');
    } catch (error) {
      console.error('Error planning a meeting from text:', error);
      toast.error(
        error instanceof Error
          ? error.message
          : 'Failed to plan a meeting from text'
      );
    } finally {
      setIsThinking(false);
    }
  };

  return (
    <div className='p-6'>
      <div className='mb-6'>
        <h2 className='text-2xl font-semibold text-gray-900'>
          Create from Text
        </h2>
        <p className='mt-1 text-sm text-gray-600'>
          Paste WeChat registration message to automatically create a meeting
        </p>
      </div>

      <div className='grid grid-cols-1 md:grid-cols-10 gap-2'>
        {/* Input Text Area */}
        <div className='flex flex-col md:col-span-4'>
          <div className='flex justify-start items-center gap-2 mb-1.5'>
            <label
              htmlFor='inputText'
              className='block text-sm font-normal text-gray-500'
            >
              Input text
            </label>
            <button
              onClick={handleThinking}
              disabled={isThinking}
              className='text-xs font-medium text-orange-500 hover:text-orange-600 bg-orange-50 hover:bg-orange-100 hover:shadow-md px-2 py-1.5 rounded-full transition flex items-center gap-1'
            >
              {isThinking ? (
                <Loader2 className='w-3 h-3 animate-spin' />
              ) : (
                <Brain className='w-3 h-3' />
              )}
              <span>Generate</span>
            </button>
          </div>
          <div className='relative w-full group'>
            <textarea
              ref={inputRef}
              id='inputText'
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              placeholder='Paste registration message here...'
              className='min-h-[320px] md:min-h-[480px] p-3 pb-6 font-mono border border-gray-300 rounded-md shadow-sm focus:outline-none focus:border-blue-500 bg-white text-xs text-gray-900 w-full transition-colors duration-100'
              style={{ resize: 'none' }}
            />
            <div
              ref={inputHandleRef}
              className='absolute bottom-0 left-0 right-0 h-6 flex items-center justify-center cursor-ns-resize'
            >
              <div className='w-20 h-2 bg-gray-300 group-hover:bg-gray-400 rounded-full transition-colors duration-200'></div>
            </div>
          </div>
        </div>

        {/* Output JSON Area */}
        <div className='flex flex-col md:col-span-6'>
          <div className='flex flex-col bg-gray-700 rounded-2xl shadow-md focus-within:ring-1 focus-within:ring-blue-500 transition-colors duration-100 overflow-clip'>
            <div className='flex justify-start items-center gap-4 py-2 px-3'>
              <label
                htmlFor='outputJson'
                className='block text-sm font-medium text-gray-100'
              >
                Meeting data
              </label>
              <div className='flex items-center gap-2'>
                <button className='text-xs font-medium text-fuchsia-500 hover:text-fuchsia-600 bg-fuchsia-50 hover:bg-fuchsia-100 hover:shadow-md px-2 py-1.5 rounded-full transition flex items-center gap-1'>
                  <Table2 className='w-3 h-3' />
                  <span>Table</span>
                </button>
                <button className='text-xs font-medium text-indigo-500 hover:text-indigo-600 bg-indigo-50 hover:bg-indigo-100 hover:shadow-md px-2 py-1.5 rounded-full transition flex items-center gap-1'>
                  <PlusCircle className='w-3 h-3' />
                  <span>Create</span>
                </button>
              </div>
            </div>
            <div className='relative w-full group bg-gray-200 rounded-t-xl overflow-clip'>
              <textarea
                ref={outputRef}
                id='outputJson'
                value={outputJson}
                onChange={(e) => setOutputJson(e.target.value)}
                placeholder='Meeting data will appear here...'
                className='min-h-[320px] md:min-h-[480px] py-5 px-3 font-mono  bg-gray-200 text-xs text-gray-700 w-full focus:outline-none'
                style={{ resize: 'none' }}
              />
              <div
                ref={outputHandleRef}
                className='absolute bottom-0 left-0 right-0 h-6 flex items-center justify-center cursor-ns-resize'
              >
                <div className='w-20 h-2 bg-gray-400 group-hover:bg-gray-500 rounded-full transition-colors duration-200'></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
