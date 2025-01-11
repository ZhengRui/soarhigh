import React, { useEffect, useRef } from 'react';
import { Download } from 'lucide-react';
import { AwardCategory } from './AwardForm';
import { UserIF } from '@/interfaces';

export interface AwardResult {
  category: AwardCategory;
  member: UserIF;
  date: string;
  customTitle?: string;
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
    img.src =
      award.category === 'Custom Award'
        ? `/images/awards/customizable.webp`
        : `/images/awards/${award.category.toLowerCase().replace(/\s+/g, '-')}.webp`;

    // Wait for image to load before drawing
    img.onload = () => {
      // Draw the image to fill the canvas
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

      // basic text settings
      ctx.textAlign = 'center';

      // Add shadow for better visibility
      ctx.shadowColor = 'rgba(0, 0, 0, 0.6)';
      ctx.shadowBlur = 12;
      ctx.shadowOffsetX = 6;
      ctx.shadowOffsetY = 6;

      // If it's a custom award, add the custom title to the canvas
      if (award.category === 'Custom Award') {
        // Add your custom title drawing logic here
        ctx.font = 'bold 600px serif';

        // Get text metrics to create gradient
        const text = (award.customTitle || 'Custom Award').toUpperCase();
        const metrics = ctx.measureText(text);
        const textWidth = metrics.width;

        // Create golden gradient
        const gradient = ctx.createLinearGradient(
          canvas.width / 2 - textWidth / 2, // start x
          0, // start y
          canvas.width / 2 + textWidth / 2, // end x
          0 // end y
        );

        // Vibrant gradient colors
        gradient.addColorStop(0, '#FFD700'); // Bright gold
        gradient.addColorStop(0.5, '#FDB931'); // Deep gold
        gradient.addColorStop(1, '#FFD700'); // Bright gold

        // Apply gradient
        ctx.fillStyle = gradient;

        ctx.fillText(
          (award.customTitle || 'Custom Award').toUpperCase(),
          canvas.width / 2,
          1800
        );
      }

      ctx.fillStyle = 'black';

      // Determine y-coordinate based on award category
      const yOffset = [
        'Best Evaluator',
        'Best Partner',
        'Custom Award',
      ].includes(award.category)
        ? -80
        : 0;

      // Format date from YYYY-MM-DD to YYYY/MM/DD
      const formattedDate = award.date.replace(/-/g, '/');

      // add date
      ctx.font = 'lighter 180px Courier New';
      ctx.fillText(formattedDate, 1700, 4050 + yOffset);

      // add president signature
      ctx.font = 'lighter 200px serif';
      ctx.fillText('Libra Lee', 4925, 4050 + yOffset);

      // Add member name
      ctx.font = '480px Brush Script MT';

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
      ctx.fillText(text, canvas.width / 2, 2850 + yOffset);
    };
  }, [award]);

  const handleDownload = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const link = document.createElement('a');
    const filename =
      award.category === 'Custom Award'
        ? `${award.customTitle?.toLowerCase().replace(/\s+/g, '-') || 'custom-award'}.png`
        : `${award.category.toLowerCase().replace(/\s+/g, '-')}.png`;

    link.download = filename;
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
