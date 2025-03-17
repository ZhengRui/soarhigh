'use client';

import React, { useState, useEffect, useCallback } from 'react';
import * as ExcelJS from 'exceljs';

type PreviewerProps = {
  createWorkbook: () => Promise<{
    workbook: ExcelJS.Workbook;
    worksheet: ExcelJS.Worksheet;
  }>;
  autoPreview?: boolean;
};

const AgendaExcelPreviewer: React.FC<PreviewerProps> = ({
  createWorkbook,
  autoPreview = true,
}) => {
  const [isGenerating, setIsGenerating] = useState(false);
  const [previewData, setPreviewData] = useState<any[][]>([]);

  // Helper function to properly extract Excel color to CSS
  const extractExcelColor = useCallback((argbColor?: string): string => {
    if (!argbColor) return '';

    // Handle both formats: with or without alpha channel
    return argbColor.length >= 8
      ? `#${argbColor.substring(2)}` // Remove alpha if present (FFRRGGBB -> RRGGBB)
      : `#${argbColor}`; // Use as is if no alpha
  }, []);

  // Function to get border style
  const getBorderStyle = useCallback((border?: ExcelJS.BorderStyle): string => {
    if (!border) return '';
    return border === 'thin' ? '1px solid #000000' : '2px solid #000000';
  }, []);

  // Function to generate preview
  const generatePreview = useCallback(async () => {
    setIsGenerating(true);
    try {
      const { worksheet } = await createWorkbook();

      // Extract only the Opening and Intro section (approximately rows 1-10)
      const data: any[][] = [];
      const maxRow = 100; // Just capture the first section

      worksheet.eachRow({ includeEmpty: false }, (row, rowNumber) => {
        if (rowNumber <= maxRow) {
          const rowData: any[] = [];

          row.eachCell({ includeEmpty: true }, (cell) => {
            // Extract styling information
            let bgColor = '';
            if (
              cell.fill?.type === 'pattern' &&
              cell.fill?.pattern === 'solid' &&
              cell.fill?.fgColor?.argb
            ) {
              bgColor = extractExcelColor(cell.fill.fgColor.argb);
            }

            let textColor = '#000000';
            if (cell.font?.color?.argb) {
              textColor = extractExcelColor(cell.font.color.argb);
            }

            rowData.push({
              value: cell.text || '',
              style: {
                backgroundColor: bgColor,
                color: textColor,
                bold: cell.font?.bold || false,
                fontSize: cell.font?.size || 11,
                borderTop: getBorderStyle(cell.border?.top?.style),
                borderBottom: getBorderStyle(cell.border?.bottom?.style),
                borderLeft: getBorderStyle(cell.border?.left?.style),
                borderRight: getBorderStyle(cell.border?.right?.style),
                textAlign: cell.alignment?.horizontal || 'left',
                padding: '2px 6px',
              },
            });
          });

          // Ensure we have at least 4 columns
          while (rowData.length < 4) {
            rowData.push({
              value: '',
              style: {
                backgroundColor: '',
                color: '#000000',
                bold: false,
                fontSize: 11,
                borderTop: '',
                borderBottom: '',
                borderLeft: '',
                borderRight: '',
                textAlign: 'left',
                padding: '2px 6px',
              },
            });
          }

          data.push(rowData);
        }
      });

      // console.log(data);
      setPreviewData(data);
    } catch (error) {
      console.error('Error generating preview:', error);
    } finally {
      setIsGenerating(false);
    }
  }, [createWorkbook, extractExcelColor, getBorderStyle]);

  // Generate preview on mount if autoPreview is true
  useEffect(() => {
    if (autoPreview) {
      generatePreview();
    }
  }, [autoPreview, generatePreview]);

  // Render loading state
  if (isGenerating) {
    return <div className='w-full text-center py-4'>Generating preview...</div>;
  }

  // Render empty state
  if (previewData.length === 0) {
    return (
      <div className='w-full flex flex-col items-center gap-4 py-4'>
        <p>No preview available</p>
        <button
          onClick={generatePreview}
          className='px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700'
        >
          Generate Preview
        </button>
      </div>
    );
  }

  // Render the preview
  return (
    <div className='w-full mt-6'>
      <h2 className='text-xl font-semibold mb-4'>Agenda Preview</h2>
      <div className='border border-gray-300 border-opacity-0 rounded overflow-auto'>
        <table className='border-collapse table-fixed w-[840px]'>
          <tbody>
            {previewData.map((row, rowIndex) => (
              <tr key={`row-${rowIndex}`}>
                {row.map((cell, cellIndex) => (
                  <td
                    key={`cell-${rowIndex}-${cellIndex}`}
                    className='p-2'
                    style={{
                      backgroundColor: cell.style.backgroundColor,
                      color: cell.style.color,
                      fontWeight: cell.style.bold ? 'bold' : 'normal',
                      fontSize: `${cell.style.fontSize}px`,
                      borderTop: cell.style.borderTop,
                      borderBottom: cell.style.borderBottom,
                      borderLeft: cell.style.borderLeft,
                      borderRight: cell.style.borderRight,
                      textAlign: cell.style.textAlign as
                        | 'left'
                        | 'center'
                        | 'right',
                      width:
                        cellIndex === 0
                          ? '120px' // Time column
                          : cellIndex === 1
                            ? '500px' // Activities column
                            : cellIndex === 2
                              ? '60px' // Duration column
                              : '160px', // Role Taker column
                      padding: cell.style.padding,
                      height: '12px', // Standard Excel row height
                      whiteSpace: 'pre-wrap', // Preserve whitespace and wrap text
                      verticalAlign: 'middle', // Center vertically
                    }}
                  >
                    {typeof cell.value === 'string'
                      ? cell.value
                          .split('\n')
                          .map((line: string, i: number) => (
                            <React.Fragment key={i}>
                              {line}
                              {i < cell.value.split('\n').length - 1 && <br />}
                            </React.Fragment>
                          ))
                      : cell.value}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <button
        onClick={generatePreview}
        className='mt-4 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700'
      >
        Refresh Preview
      </button>
    </div>
  );
};

export default AgendaExcelPreviewer;
