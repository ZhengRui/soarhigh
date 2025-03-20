'use client';

import React, { useState, useEffect, useCallback } from 'react';
import * as ExcelJS from 'exceljs';
import { saveAs } from 'file-saver';
import { MeetingIF } from '@/interfaces';
import { createMeetingWorkbook } from '@/utils/workbook';
import Image from 'next/image';
import { Download } from 'lucide-react';

type AgendaWorkbookProps = {
  meeting: MeetingIF;
};

const AgendaWorkbook: React.FC<AgendaWorkbookProps> = ({ meeting }) => {
  const [isGenerating, setIsGenerating] = useState(false);
  const [previewData, setPreviewData] = useState<any[][]>([]);
  const [columnWidths, setColumnWidths] = useState<number[]>([]);
  const [fontSizeScale, setFontSizeScale] = useState(1);

  // Helper function to properly extract Excel color to CSS
  const extractExcelColor = useCallback((argbColor?: string): string => {
    if (!argbColor) return '';

    // Handle both formats: with or without alpha channel
    return argbColor.length >= 8
      ? `#${argbColor.substring(2)}` // Remove alpha if present (FFRRGGBB -> RRGGBB)
      : `#${argbColor}`; // Use as is if no alpha
  }, []);

  // Function to get border style
  const getBorderStyle = useCallback(
    (border?: Partial<ExcelJS.Border>): string => {
      if (!border) return '';

      const width = border.style === 'thin' ? '1px' : '2px';
      const color = border.color?.argb
        ? extractExcelColor(border.color.argb)
        : '#000000';

      return `${width} solid ${color}`;
    },
    [extractExcelColor]
  );

  // Function to convert Excel font size to responsive rem units
  const getResponsiveFontSize = useCallback(
    (excelFontSize: number = 11): string => {
      // Base conversion: Excel size to rem (11px in Excel ≈ 0.688rem in browser)
      const baseRemSize = excelFontSize / 16;
      // Apply scaling factor for different device sizes
      return `${baseRemSize * fontSizeScale}rem`;
    },
    [fontSizeScale]
  );

  // Adjust scale factor based on screen size
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth < 768) {
        setFontSizeScale(0.92); // Mid scale for tablets
      } else {
        setFontSizeScale(1); // Normal scale for desktop
      }
    };

    // Set initial value
    handleResize();

    // Add resize listener
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Function to generate Excel download
  const handleDownload = async () => {
    setIsGenerating(true);
    try {
      const { workbook } = await createMeetingWorkbook(meeting);

      // Generate Excel file as a buffer
      const buffer = await workbook.xlsx.writeBuffer();

      // Create a Blob from the buffer
      const blob = new Blob([buffer], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      });

      // Save the file using FileSaver
      saveAs(blob, `${meeting.theme || 'Meeting'}_Agenda.xlsx`);
    } catch (error) {
      console.error('Error generating Excel file:', error);
    } finally {
      setIsGenerating(false);
    }
  };

  // Function to generate preview
  const generatePreview = useCallback(async () => {
    setIsGenerating(true);
    try {
      const { worksheet } = await createMeetingWorkbook(meeting);

      // Extract only a preview section (increased from 100 to 150 rows to capture more content)
      const data: any[][] = [];
      const maxRow = 150;

      // Track merged cells
      const mergedCells: Record<string, boolean> = {};
      // Store primary cell spans
      const primaryCellSpans: Record<
        string,
        { rowSpan: number; colSpan: number }
      > = {};

      // Helper function to convert Excel column letter to number
      function excelColToNum(col: string): number {
        let result = 0;
        for (let i = 0; i < col.length; i++) {
          result = result * 26 + (col.charCodeAt(i) - 64);
        }
        return result;
      }

      // Process merged cell ranges - using a direct approach
      try {
        // Use type assertion to access internal properties
        const worksheetAny = worksheet as any;

        // Access the _merges object directly
        if (worksheetAny._merges && typeof worksheetAny._merges === 'object') {
          // Process each merge range
          Object.keys(worksheetAny._merges).forEach((mergeKey) => {
            // The value could be a string range like 'B2:C2' or a model object
            const mergeInfo = worksheetAny._merges[mergeKey];
            let startCell, endCell;

            if (typeof mergeInfo === 'string') {
              // If it's a string like 'B2:C2'
              const parts = mergeInfo.split(':');
              if (parts.length === 2) {
                [startCell, endCell] = parts;
              }
            } else if (mergeInfo && mergeInfo.model) {
              // Based on screenshot, each merge has a model property
              // The address is likely stored in the model
              if (mergeInfo.model.address) {
                const parts = mergeInfo.model.address.split(':');
                if (parts.length === 2) {
                  [startCell, endCell] = parts;
                }
              } else if (mergeKey.includes(':')) {
                // Sometimes the key itself might be the range
                const parts = mergeKey.split(':');
                if (parts.length === 2) {
                  [startCell, endCell] = parts;
                }
              } else {
                // If we can't find an address, try using the key (like B2)
                // and the extents from the model
                startCell = mergeKey;

                // Try to compute the end cell from the model properties
                if (
                  mergeInfo.model.left !== undefined &&
                  mergeInfo.model.top !== undefined &&
                  mergeInfo.model.right !== undefined &&
                  mergeInfo.model.bottom !== undefined
                ) {
                  // Convert number to column letter (e.g., 2 -> B)
                  function numToColLetter(n: number): string {
                    let colStr = '';
                    while (n > 0) {
                      const modulo = (n - 1) % 26;
                      colStr = String.fromCharCode(65 + modulo) + colStr;
                      n = Math.floor((n - modulo) / 26);
                    }
                    return colStr || 'A';
                  }

                  const endColLetter = numToColLetter(mergeInfo.model.right);
                  const endRow = mergeInfo.model.bottom;
                  endCell = `${endColLetter}${endRow}`;
                }
              }
            }

            // Process the start and end cells if we have them
            if (startCell && endCell) {
              const startMatch = startCell.match(/([A-Z]+)(\d+)/);
              const endMatch = endCell.match(/([A-Z]+)(\d+)/);

              if (startMatch && endMatch) {
                const startCol = excelColToNum(startMatch[1]);
                const startRow = parseInt(startMatch[2]);
                const endCol = excelColToNum(endMatch[1]);
                const endRow = parseInt(endMatch[2]);

                // Store span information for primary cell (top-left)
                const rowSpan = endRow - startRow + 1;
                const colSpan = endCol - startCol + 1;
                primaryCellSpans[`${startRow}:${startCol}`] = {
                  rowSpan,
                  colSpan,
                };

                // Mark all cells in the merge range except the top-left
                for (let row = startRow; row <= endRow; row++) {
                  for (let col = startCol; col <= endCol; col++) {
                    if (row !== startRow || col !== startCol) {
                      mergedCells[`${row}:${col}`] = true;
                    }
                  }
                }
              }
            }
          });
        }
      } catch (err) {
        console.error('Error processing merged cells:', err);
        // Continue even if we can't process merged cells
      }

      // Get column widths
      const widths: number[] = [];
      worksheet.columns.forEach((column) => {
        widths.push(column.width!);
      });
      setColumnWidths([18, 21, 24, 28, 12, 22]);

      worksheet.eachRow({ includeEmpty: false }, (row, rowNumber) => {
        if (rowNumber <= maxRow) {
          const rowData: any[] = [];

          row.eachCell({ includeEmpty: true }, (cell, colNumber) => {
            // Skip cells that are part of a merge but not the top-left cell
            if (mergedCells[`${rowNumber}:${colNumber}`]) {
              return;
            }

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

            // Check if this is a primary cell in a merge range
            const primarySpan = primaryCellSpans[
              `${rowNumber}:${colNumber}`
            ] || { rowSpan: 1, colSpan: 1 };

            rowData.push({
              value: cell.text || '',
              style: {
                backgroundColor: bgColor,
                color: textColor,
                bold: cell.font?.bold || false,
                fontSize: cell.font?.size || 11,
                borderTop: getBorderStyle(cell.border?.top),
                borderBottom: getBorderStyle(cell.border?.bottom),
                borderLeft: getBorderStyle(cell.border?.left),
                borderRight: getBorderStyle(cell.border?.right),
                textAlign: cell.alignment?.horizontal || 'left',
                verticalAlign: cell.alignment?.vertical || 'middle',
                padding: '2px 6px',
                isMerged: primarySpan.rowSpan > 1 || primarySpan.colSpan > 1,
                rowSpan: primarySpan.rowSpan,
                colSpan: primarySpan.colSpan,
              },
            });
          });

          // Ensure we have at least 4 columns (or more if needed)
          const minColumns = Math.max(4, widths.length);
          while (rowData.length < minColumns) {
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
                isMerged: false,
                rowSpan: 1,
                colSpan: 1,
              },
            });
          }

          data.push(rowData);
        }
      });

      setPreviewData(data);
    } catch (error) {
      console.error('Error generating preview:', error);
    } finally {
      setIsGenerating(false);
    }
  }, [extractExcelColor, getBorderStyle, meeting]);

  // Generate preview on mount
  useEffect(() => {
    generatePreview();
  }, [generatePreview, meeting]);

  // Render empty state
  if (previewData.length === 0) {
    return (
      <div className='flex flex-col items-center justify-center p-6 my-8 w-full h-64'>
        <p className='mb-4 text-gray-600'>No workbook data available</p>
      </div>
    );
  }

  const tableWidth = columnWidths.reduce((sum, width) => sum + width, 0);

  // Render the preview
  return (
    <div className='w-full my-8 max-w-4xl mx-auto px-4'>
      <div className='flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4 mb-8'>
        <div>
          <h1 className='text-2xl sm:text-3xl font-bold text-gray-900 mb-2'>
            Meeting Agenda Workbook
          </h1>
          <p className='text-gray-600 text-sm sm:text-base'>
            Preview and download meeting agenda workbook
          </p>
        </div>

        <button
          onClick={handleDownload}
          className='self-start sm:self-center items-center inline-flex gap-1.5 px-3 py-1.5 bg-gradient-to-r from-blue-600 to-purple-600 text-white text-sm rounded-md hover:from-blue-700 hover:to-purple-700 transition-all duration-200 shadow-sm hover:shadow-md'
          disabled={isGenerating}
        >
          <Download className='w-4 h-4' />
          <span className='font-medium'>Download Excel</span>
        </button>
      </div>

      <div className='w-full border border-gray-300 border-opacity-30 rounded-md overflow-auto'>
        <div className='min-w-[600px] relative'>
          {/* Images with responsive containers */}
          <div className='absolute left-2.5 top-2.5 w-[72px] md:w-20 aspect-square'>
            <Image
              src='/images/toastmasters.png'
              alt='Toastmasters Logo'
              fill
              className='object-fill'
            />
          </div>
          <div className='absolute left-[88px] md:left-28 lg:left-36 top-[18px] md:top-2.5 w-16 md:w-[72px] aspect-square'>
            <Image
              src='/images/soarhighQR.png'
              alt='Soarhigh QR Code'
              fill
              className='object-fill'
            />
          </div>
          <div className='absolute right-4 md:right-8 top-9 md:top-[30px] lg:top-6 w-14 md:w-16 aspect-square'>
            <Image
              src='/images/vpmQR.png'
              alt='VPM QR Code'
              fill
              className='object-fill'
            />
          </div>
          <table className='border-collapse table-fixed w-full'>
            <colgroup>
              {columnWidths.map((width, index) => (
                <col
                  key={`col-${index}`}
                  style={{ width: `${(width / tableWidth) * 100}%` }}
                />
              ))}
            </colgroup>
            <tbody>
              {previewData.map((row, rowIndex) => (
                <tr
                  key={`row-${rowIndex}`}
                  // className={rowIndex % 2 === 0 ? 'bg-white' : 'bg-gray-50'}
                >
                  {row.map((cell, cellIndex) => {
                    return (
                      <td
                        key={`cell-${rowIndex}-${cellIndex}`}
                        className='p-2'
                        rowSpan={cell.style.rowSpan}
                        colSpan={cell.style.colSpan}
                        style={{
                          backgroundColor: cell.style.backgroundColor,
                          color: cell.style.color,
                          fontWeight: cell.style.bold ? 'bold' : 'normal',
                          fontSize: getResponsiveFontSize(cell.style.fontSize),
                          borderTop: cell.style.borderTop,
                          borderBottom: cell.style.borderBottom,
                          borderLeft: cell.style.borderLeft,
                          borderRight: cell.style.borderRight,
                          textAlign: cell.style.textAlign as
                            | 'left'
                            | 'center'
                            | 'right',
                          // width: `${columnWidths[cellIndex] * 7}px`, // Scale column width based on Excel width
                          padding: cell.style.padding,
                          height: '12px', // Standard Excel row height
                          whiteSpace: 'pre-wrap', // Preserve whitespace and wrap text
                          verticalAlign: cell.style.verticalAlign || 'middle', // Center vertically
                        }}
                      >
                        {typeof cell.value === 'string'
                          ? cell.value
                              .split('\n')
                              .map((line: string, i: number) => (
                                <React.Fragment key={i}>
                                  {line}
                                  {i < cell.value.split('\n').length - 1 && (
                                    <br />
                                  )}
                                </React.Fragment>
                              ))
                          : cell.value}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default AgendaWorkbook;
