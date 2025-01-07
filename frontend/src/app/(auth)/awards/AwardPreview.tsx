import React, { useEffect, useRef } from 'react';
import { Download } from 'lucide-react';
import { AwardCategory } from './AwardForm';
import { UserIF } from '@/interfaces';

export interface AwardResult {
  category: AwardCategory;
  member: UserIF;
}

export const AwardPreview = ({ award }: { award: AwardResult }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Clear canvas
    ctx.fillStyle = '#E5E7EB';
    ctx.fillRect(0, 0, 800, 600);

    // Add text
    ctx.fillStyle = '#1F2937';
    ctx.font = 'bold 24px serif';
    ctx.textAlign = 'center';
    ctx.fillText(award.category, 400, 300);
    ctx.fillText(award.member.full_name, 400, 400);
  }, [award]);

  const handleDownload = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const link = document.createElement('a');
    link.download = `${award.category.toLowerCase().replace(/\s+/g, '-')}.png`;
    link.href = canvas.toDataURL();
    link.click();
  };

  return (
    <div className='relative'>
      <canvas
        ref={canvasRef}
        width={800}
        height={600}
        className='w-full h-auto rounded-lg shadow-sm'
      />
      <button
        onClick={handleDownload}
        className='absolute top-4 right-4 p-2 bg-white rounded-full shadow-md hover:bg-gray-50'
        title='Download Award'
      >
        <Download className='w-5 h-5 text-gray-600' />
      </button>
    </div>
  );
};
