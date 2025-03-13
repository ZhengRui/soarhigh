'use client';

import React, { useEffect, useState, useRef, useCallback } from 'react';
import ReactCanvasConfetti from 'react-canvas-confetti';

type CelebrationModalProps = {
  onClose: () => void;
};

// Typewriter hook
const useTypewriter = (text: string, speed: number = 70) => {
  const [displayedText, setDisplayedText] = useState('');
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isComplete, setIsComplete] = useState(false);

  useEffect(() => {
    if (currentIndex < text.length) {
      const timer = setTimeout(() => {
        setDisplayedText((prev) => prev + text[currentIndex]);
        setCurrentIndex((prev) => prev + 1);
      }, speed);
      return () => clearTimeout(timer);
    } else {
      setIsComplete(true);
    }
  }, [currentIndex, text, speed]);

  return { displayedText, isComplete };
};

// Confetti configuration
const canvasStyles: React.CSSProperties = {
  position: 'fixed',
  pointerEvents: 'none',
  width: '100%',
  height: '100%',
  top: 0,
  left: 0,
  zIndex: 999,
};

export function CelebrationModal({ onClose }: CelebrationModalProps) {
  const [showHeart, setShowHeart] = useState(false);
  const [showText, setShowText] = useState(false);
  const refAnimationInstance = useRef<any>(null);

  // Text to be typed
  const celebrationText =
    'Thank you for attending the meeting\nSee you next time\nLove from SoarHigh';
  const { displayedText, isComplete } = useTypewriter(
    showText ? celebrationText : '',
    70
  );

  // Function to render text with line breaks
  const renderTextWithLineBreaks = (text: string) => {
    return text.split('\n').map((line, index, array) => (
      <React.Fragment key={index}>
        {line}
        {index < array.length - 1 && <br />}
      </React.Fragment>
    ));
  };

  // Auto-close after animation completes
  useEffect(() => {
    // Show heart after 1 second
    const heartTimer = setTimeout(() => setShowHeart(true), 1000);

    // Show text after heart appears
    const textTimer = setTimeout(() => setShowText(true), 2500);

    // Auto-close after everything completes (adjust timing as needed)
    const closeTimer = setTimeout(() => onClose(), 12000);

    return () => {
      clearTimeout(heartTimer);
      clearTimeout(textTimer);
      clearTimeout(closeTimer);
    };
  }, [onClose]);

  // Confetti setup
  const getInstance = useCallback((instance: any) => {
    refAnimationInstance.current = instance;
  }, []);

  const makeFirework = useCallback(() => {
    if (!refAnimationInstance.current) return;

    const colors = ['#4f46e5', '#8b5cf6', '#ec4899', '#f43f5e', '#f97316'];

    refAnimationInstance.current.confetti({
      particleCount: 80,
      spread: 100,
      origin: { y: Math.random() * 0.6 + 0.2, x: Math.random() },
      colors: colors,
      startVelocity: 30,
      scalar: 1.2,
      ticks: 60,
      gravity: 0.9,
      shapes: ['circle', 'square'],
    });
  }, []);

  // Fire multiple fireworks
  useEffect(() => {
    let interval: NodeJS.Timeout;
    let timeout: NodeJS.Timeout;

    const startFireworks = () => {
      // Initial burst
      makeFirework();

      // Continuous fireworks
      interval = setInterval(() => {
        makeFirework();
      }, 800);

      // Stop after 7 seconds
      timeout = setTimeout(() => {
        clearInterval(interval);
      }, 7000);
    };

    startFireworks();

    return () => {
      clearInterval(interval);
      clearTimeout(timeout);
    };
  }, [makeFirework]);

  return (
    <div className='fixed inset-0 z-50 flex items-center justify-center'>
      {/* Fireworks */}
      <ReactCanvasConfetti onInit={getInstance} style={canvasStyles} />

      {/* Heart Animation */}
      <div
        className={`flex flex-col justify-center items-center transition-all bg-purple-50 backdrop-blur-sm bg-opacity-50 w-80 h-80 sm:w-[440px] sm:h-[440px] rounded-full p-4 duration-1000 ease-in-out transform ${showHeart ? 'scale-100 opacity-100' : 'scale-0 opacity-0'}`}
      >
        <div className='animate-pulse'>
          <svg
            className='w-32 h-32 sm:w-40 sm:h-40 text-pink-500'
            viewBox='0 0 24 24'
            fill='currentColor'
            xmlns='http://www.w3.org/2000/svg'
          >
            <path d='M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z' />
          </svg>
        </div>

        {/* Typewriter Text */}
        <div className='mt-2 sm:mt-8 max-w-md text-center w-full px-3 sm:px-6'>
          <p className='text-pink-500 text-sm sm:text-xl font-medium relative text-center mx-auto'>
            {renderTextWithLineBreaks(displayedText)}
            <span
              className={`inline-block w-0.5 h-[14px] sm:h-4 ml-1 bg-pink-500 ${isComplete ? 'animate-pulse' : 'animate-blink'}`}
            ></span>
          </p>
        </div>
      </div>
    </div>
  );
}

// Add this to your globals.css or as a style tag
// @keyframes blink {
//   0%, 100% { opacity: 1; }
//   50% { opacity: 0; }
// }
// .animate-blink {
//   animation: blink 1s step-end infinite;
// }
