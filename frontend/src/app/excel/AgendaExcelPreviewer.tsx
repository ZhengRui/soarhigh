'use client';

import React, { useState, useEffect, useCallback } from 'react';
import * as ExcelJS from 'exceljs';
import { createWorkbook } from './workbookUtils';

type PreviewerProps = {
  autoPreview?: boolean;
};

const AgendaExcelPreviewer: React.FC<PreviewerProps> = ({
  autoPreview = true,
}) => {
  const [isGenerating, setIsGenerating] = useState(false);
  const [previewData, setPreviewData] = useState<any[][]>([]);
  const [columnWidths, setColumnWidths] = useState<number[]>([]);

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

  // Function to generate preview
  const generatePreview = useCallback(async () => {
    setIsGenerating(true);
    try {
      const { worksheet } = await createWorkbook();

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

        // Access the _merges object directly (based on the screenshot)
        if (worksheetAny._merges && typeof worksheetAny._merges === 'object') {
          // Process each merge range (B2, B3, etc. are keys in the _merges object)
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
      setColumnWidths(widths);

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
  }, [extractExcelColor, getBorderStyle]);

  // Generate preview on mount if autoPreview is true
  useEffect(() => {
    if (autoPreview) {
      generatePreview();
    }
  }, [autoPreview, generatePreview]);

  // Render loading state
  if (isGenerating) {
    return (
      <div className='flex flex-col items-center p-6 bg-white rounded-lg shadow-md max-w-4xl mx-auto my-8'>
        Generating preview...
      </div>
    );
  }

  // Render empty state
  if (previewData.length === 0) {
    return (
      <div className='flex flex-col items-center p-6 bg-white rounded-lg shadow-md max-w-4xl mx-auto my-8'>
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
    <div className='flex flex-col items-center p-6 bg-white rounded-lg shadow-md max-w-4xl mx-auto my-8'>
      <h2 className='text-xl font-semibold mb-4'>Agenda Preview</h2>
      <div className='w-full border border-gray-300 border-opacity-30 pt-2 rounded-t-md overflow-auto'>
        <table className='border-collapse table-fixed w-full'>
          <colgroup>
            {columnWidths.map((width, index) => (
              <col key={`col-${index}`} style={{ width: `${width * 7}px` }} />
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
                        fontSize: `${cell.style.fontSize}px`,
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
