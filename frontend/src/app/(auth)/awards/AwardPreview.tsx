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

    // Create new image object
    const img = new Image();
    // Set the source - replace this URL with your actual award image URL
    img.src = `/images/awards/${award.category.toLowerCase().replace(/\s+/g, '-')}.webp`;

    // Wait for image to load before drawing
    img.onload = () => {
      // Draw the image to fill the canvas
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

      // Add text with shadow for better visibility
      ctx.textAlign = 'center';
      ctx.fillStyle = 'black';

      // add date
      ctx.font = 'lighter 180px Courier New';
      ctx.fillText('2025/01/11', 1700, 4050);

      // add president signature
      ctx.font = 'lighter 200px serif';
      ctx.fillText('Libra Lee', 4925, 4050);

      // Add award category if it's Customized Award
      //   ctx.fillText(award.category, 400, 300);

      // Add member name
      ctx.font = '480px Brush Script MT';

      // Add shadow for better visibility
      ctx.shadowColor = 'rgba(0, 0, 0, 0.6)';
      ctx.shadowBlur = 12;
      ctx.shadowOffsetX = 6;
      ctx.shadowOffsetY = 6;

      const text = award.member.full_name;
      const metrics = ctx.measureText(text);
      const textWidth = metrics.width;

      // Create gradient matching NavLink colors
      const gradient = ctx.createLinearGradient(
        canvas.width / 2 - textWidth / 2, // start x
        0, // start y
        canvas.width / 2 + textWidth / 2, // end x
        0 // end y
      );

      // Match the "from-blue-600 to-purple-600" colors
      gradient.addColorStop(0, '#2563eb'); // blue-600
      gradient.addColorStop(1, '#9333ea'); // purple-600

      // Apply gradient
      ctx.fillStyle = gradient;

      // Draw text
      ctx.fillText(text, canvas.width / 2, 2850);
    };
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
        width={6652}
        height={5140}
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
