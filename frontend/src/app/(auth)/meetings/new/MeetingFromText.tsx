'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Brain, PlusCircle, Table2, Loader2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { planMeetingFromText } from '@/utils/meeting';
import Editor from 'react-simple-code-editor';
import { highlight, languages } from 'prismjs';
import 'prismjs/components/prism-json';
import 'prismjs/themes/prism.css';
import { MeetingIF } from '@/interfaces';
import { convertSegmentsToBaseSegments } from '@/utils/segments';
import { MeetingForm } from '../MeetingForm';

// Custom styles for the editor
const editorStyles = {
  fontFamily: 'monospace',
  fontSize: '12px',
  // backgroundColor: 'rgb(229, 231, 235)', // bg-gray-200
  // color: 'rgb(55, 65, 81)', // text-gray-700
  // height: '100%',
  // width: '100%',
  // minHeight: '480px',
  // overflow: 'auto',
};

const CustomStyles = () => (
  <style jsx global>{`
    .editor-container textarea {
      outline: none !important;
      // height: 100% !important;
      // min-height: 480px !important;
      // position: absolute !important;
      // top: 0;
      // left: 0;
      // right: 0;
      // bottom: 0;
    }
  `}</style>
);

export const MeetingFromText = () => {
  const [inputText, setInputText] = useState('');
  const [outputJson, setOutputJson] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const outputRef = useRef<HTMLDivElement>(null);
  const inputHandleRef = useRef<HTMLDivElement>(null);
  const outputHandleRef = useRef<HTMLDivElement>(null);

  const [isThinking, setIsThinking] = useState(false);
  const [isEditing, setIsEditing] = useState(false);

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
      const container = outputRef.current;
      const handle = outputHandleRef.current;

      const handleMouseDown = (e: MouseEvent) => {
        e.preventDefault();
        const startY = e.clientY;
        const startHeight = container.offsetHeight;

        function onMouseMove(e: MouseEvent) {
          const newHeight = startHeight + (e.clientY - startY);
          if (newHeight > 100) {
            container.style.height = `${newHeight}px`;
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
        const startHeight = container.offsetHeight;

        function onTouchMove(e: TouchEvent) {
          const newHeight = startHeight + (e.touches[0].clientY - startY);
          if (newHeight > 100) {
            container.style.height = `${newHeight}px`;
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

  const handleWorkbookPreview = async () => {
    if (!outputJson) return;

    try {
      localStorage.setItem('tempMeetingData', outputJson);
      window.open(
        '/meetings/workbook/preview',
        '_blank',
        'noopener,noreferrer'
      );
    } catch (error) {
      console.error('Error saving to localStorage:', error);
    }
  };

  if (isEditing) {
    const meeting = JSON.parse(outputJson) as MeetingIF;
    const formData = {
      ...meeting,
      segments: convertSegmentsToBaseSegments(meeting.segments || []),
    };

    return (
      <div className='mt-4'>
        <div className='bg-blue-50 p-4 mb-6 rounded-md'>
          <h3 className='text-sm font-medium text-blue-800'>
            Meeting planned from text
          </h3>
          <p className='text-xs text-blue-600 mt-1'>
            You can edit the meeting details below before saving
          </p>
        </div>
        <MeetingForm initFormData={formData} mode='create' />
      </div>
    );
  }

  return (
    <div className='p-6'>
      <CustomStyles />
      <div className='mb-6'>
        <h2 className='text-2xl font-semibold text-gray-900'>
          Create from Text
        </h2>
        <p className='mt-1 text-sm text-gray-600'>
          Paste WeChat registration message to automatically create a meeting
        </p>
      </div>

      <div className='grid grid-cols-1 md:grid-cols-10 gap-8 md:gap-2'>
        {/* Input Text Area */}
        <div className='flex flex-col md:col-span-4'>
          <div className='flex flex-col bg-gray-700 rounded-2xl shadow-md focus-within:ring-1 focus-within:ring-blue-500 transition-colors duration-100 overflow-clip'>
            <div className='flex justify-between md:justify-start items-center gap-2 py-2 px-3'>
              <label
                htmlFor='inputText'
                className='block text-sm font-medium text-gray-100'
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
            <div className='relative w-full group rounded-t-xl flex overflow-clip'>
              <textarea
                ref={inputRef}
                id='inputText'
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                placeholder='Paste registration message here...'
                className='h-[320px] md:h-[480px] p-5 font-mono bg-gray-50 text-xs text-gray-700 w-full focus:outline-none'
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
        </div>

        {/* Output JSON Area */}
        <div className='flex flex-col md:col-span-6'>
          <div className='flex flex-col bg-gray-700 rounded-2xl shadow-md focus-within:ring-1 focus-within:ring-blue-500 transition-colors duration-100 overflow-clip'>
            <div className='flex justify-between md:justify-start items-center gap-4 py-2 px-3'>
              <label
                htmlFor='outputJson'
                className='block text-sm font-medium text-gray-100'
              >
                Meeting data
              </label>
              <div className='flex items-center gap-2'>
                <button
                  onClick={handleWorkbookPreview}
                  className='text-xs font-medium text-fuchsia-500 hover:text-fuchsia-600 bg-fuchsia-50 hover:bg-fuchsia-100 hover:shadow-md px-2 py-1.5 rounded-full transition flex items-center gap-1'
                >
                  <Table2 className='w-3 h-3' />
                  <span>Table</span>
                </button>
                <button
                  onClick={() => {
                    // if jsonOutput can be parsed into a valid MeetingIF then set
                    try {
                      const meeting = JSON.parse(outputJson) as MeetingIF;
                      if (meeting && meeting.segments) {
                        setIsEditing(true);
                      } else {
                        setIsEditing(false);
                      }
                    } catch (error) {
                      setIsEditing(false);
                      console.error('Error parsing JSON:', error);
                      toast.error('Failed to parse meeting data');
                    }
                  }}
                  className='text-xs font-medium text-indigo-500 hover:text-indigo-600 bg-indigo-50 hover:bg-indigo-100 hover:shadow-md px-2 py-1.5 rounded-full transition flex items-center gap-1'
                >
                  <PlusCircle className='w-3 h-3' />
                  <span>Create</span>
                </button>
              </div>
            </div>
            <div className='relative w-full group rounded-t-xl overflow-clip'>
              <div
                ref={outputRef}
                className='h-[320px] md:h-[480px] font-mono bg-gray-50 text-xs text-gray-700 w-full overflow-auto'
              >
                <Editor
                  value={outputJson}
                  onValueChange={(code) => setOutputJson(code)}
                  highlight={(code) => highlight(code, languages.json, 'json')}
                  padding={20}
                  style={editorStyles}
                  textareaId='outputJson'
                  className='editor-container focus:outline-none'
                  placeholder='Meeting data will appear here...'
                />
              </div>
              <div
                ref={outputHandleRef}
                className='absolute bottom-0 left-0 right-0 h-6 flex items-center justify-center cursor-ns-resize'
              >
                <div className='w-20 h-2 bg-gray-300 group-hover:bg-gray-400 rounded-full transition-colors duration-200'></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
