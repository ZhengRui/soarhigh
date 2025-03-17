'use client';

import React, { useState } from 'react';
import * as ExcelJS from 'exceljs';
import { saveAs } from 'file-saver';
import AgendaExcelPreviewer from './AgendaExcelPreviewer';

// Define a new section data type with array-based rows
type ArraySectionData = {
  title: string;
  headers: string[];
  columnWidths?: number[];
  rows: Array<(string | number)[]>;
};

const AgendaExcelGenerator: React.FC = () => {
  const [isGenerating, setIsGenerating] = useState(false);
  const [isReady, setIsReady] = useState(false);

  // Common styling functions
  const getHeaderStyle = (): Partial<ExcelJS.Style> => ({
    fill: {
      type: 'pattern',
      pattern: 'solid',
      fgColor: { argb: 'FF343e4e' }, // Dark blue background
    },
    font: {
      color: { argb: 'FFFFFFFF' }, // White text
      bold: true,
      name: 'Arial',
      size: 9,
    },
    border: {
      top: { style: 'thin' },
      left: { style: 'thin' },
      bottom: { style: 'thin' },
      right: { style: 'thin' },
    },
    alignment: {
      vertical: 'middle',
      horizontal: 'center',
    },
  });

  const getRowStyle = (): Partial<ExcelJS.Style> => ({
    border: {
      top: { style: 'thin' },
      left: { style: 'thin' },
      bottom: { style: 'thin' },
      right: { style: 'thin' },
    },
    alignment: {
      vertical: 'middle',
    },
    font: {
      bold: true,
      name: 'Arial',
      size: 9,
    },
  });

  // Function to create a section using array-based row data
  const createArraySection = (
    worksheet: ExcelJS.Worksheet,
    data: ArraySectionData,
    startRow: number,
    showTitle: boolean = true,
    fontStyle?: { name?: string; size?: number }
  ): number => {
    // Apply column widths if provided
    if (data.columnWidths && data.columnWidths.length > 0) {
      data.columnWidths.forEach((width, index) => {
        worksheet.getColumn(index + 1).width = width;
      });
    }

    // Add section title row if showTitle is true
    if (showTitle) {
      const titleRow = worksheet.addRow([data.title]);
      titleRow.font = { bold: true, size: 11 };
      startRow++;
    }

    // Process headers with support for merged cells
    const headerRow = worksheet.addRow(data.headers);

    // Apply header styling
    const headerStyle = getHeaderStyle();
    headerRow.eachCell((cell) => {
      cell.fill = headerStyle.fill as ExcelJS.Fill;
      cell.font = headerStyle.font as ExcelJS.Font;
      cell.border = headerStyle.border as ExcelJS.Borders;
      cell.alignment = headerStyle.alignment as ExcelJS.Alignment;
    });

    // Handle merged cells in headers (marked with '>')
    let mergeStart = -1;
    let mergeCount = 0;

    data.headers.forEach((cell, index) => {
      if (cell !== '>' && mergeStart === -1) {
        // Start of a potential merge
        mergeStart = index;
        mergeCount = 1;
      } else if (cell === '>' && mergeStart !== -1) {
        // Continue merge
        mergeCount++;
      }

      // End of headers or next non-merge cell
      if (
        (cell !== '>' && mergeStart !== -1 && mergeStart !== index) ||
        (index === data.headers.length - 1 && mergeCount > 1)
      ) {
        // If we collected multiple cells, perform merge
        if (mergeCount > 1) {
          worksheet.mergeCells(
            startRow,
            mergeStart + 1,
            startRow,
            mergeStart + mergeCount
          );
        }
        // Reset for next merge
        if (cell !== '>') {
          mergeStart = index;
          mergeCount = 1;
        } else {
          mergeStart = -1;
          mergeCount = 0;
        }
      }
    });

    startRow++;

    // Add data rows
    data.rows.forEach((rowData) => {
      // Filter out '>' in the row data (used for merging)
      const dataRow = worksheet.addRow(rowData);

      // Apply styling
      const rowStyle = getRowStyle();
      if (fontStyle) {
        if (fontStyle.name)
          rowStyle.font = {
            ...(rowStyle.font as ExcelJS.Font),
            name: fontStyle.name,
          };
        if (fontStyle.size)
          rowStyle.font = {
            ...(rowStyle.font as ExcelJS.Font),
            size: fontStyle.size,
          };
      }

      dataRow.eachCell((cell, colNumber) => {
        cell.border = rowStyle.border as ExcelJS.Borders;
        cell.font = rowStyle.font as ExcelJS.Font;

        // Special handling for different columns
        if (
          colNumber === 1 ||
          colNumber === dataRow.cellCount - 1 ||
          colNumber === dataRow.cellCount
        ) {
          // Time, Duration, Role Taker columns - center align
          cell.alignment = { vertical: 'middle', horizontal: 'center' };
        } else {
          // Activity columns - left align
          cell.alignment = { vertical: 'middle', horizontal: 'left' };
        }
      });

      // Handle cell merging in rows
      let rowMergeStart = -1;
      let rowMergeCount = 0;

      rowData.forEach((cell, index) => {
        if (cell !== '>' && rowMergeStart === -1) {
          // Start of a potential merge
          rowMergeStart = index;
          rowMergeCount = 1;
        } else if (cell === '>' && rowMergeStart !== -1) {
          // Continue merge
          rowMergeCount++;
        }

        // End of row or next non-merge cell
        if (
          (cell !== '>' && rowMergeStart !== -1 && rowMergeStart !== index) ||
          (index === rowData.length - 1 && rowMergeCount > 1)
        ) {
          // If we collected multiple cells, perform merge
          if (rowMergeCount > 1) {
            worksheet.mergeCells(
              startRow,
              rowMergeStart + 1,
              startRow,
              rowMergeStart + rowMergeCount
            );
          }
          // Reset for next merge
          if (cell !== '>') {
            rowMergeStart = index;
            rowMergeCount = 1;
          } else {
            rowMergeStart = -1;
            rowMergeCount = 0;
          }
        }
      });

      startRow++;
    });

    return startRow;
  };

  // Function to create Table Topic Section
  const createTableTopicSection = (
    worksheet: ExcelJS.Worksheet,
    startRow: number,
    showTitle: boolean = true,
    fontStyle?: { name?: string; size?: number }
  ): number => {
    const tableTopicData: ArraySectionData = {
      title: 'Table Topic Session',
      headers: [
        'Time',
        'Table Topic Session',
        '>',
        '>',
        'Duration',
        'Role Taker',
      ],
      columnWidths: [18, 24, 24, 24, 8, 24], // Custom column widths for this section
      rows: [
        ['19:52', 'TTM (Table Topic Master) Opening', '>', '>', 4, 'Rui'],
        ['19:56', 'Aging', 'WOT(Word of Today):', 'Immortal', 16, 'All'],
      ],
    };

    return createArraySection(
      worksheet,
      tableTopicData,
      startRow,
      showTitle,
      fontStyle
    );
  };

  // Function to create Opening and Intro Section
  const createOpeningAndIntro = (
    worksheet: ExcelJS.Worksheet,
    startRow: number,
    showTitle: boolean = true,
    fontStyle?: { name?: string; size?: number }
  ): number => {
    const openingData: ArraySectionData = {
      title: 'Opening and Intro Session',
      headers: ['Time', 'Activities', '>', '>', 'Duration', 'Role Taker'],
      columnWidths: [18, 24, 24, 24, 8, 24], // Custom column widths for this section
      rows: [
        [
          '19:15',
          'Members and Guests Registration, Warm up',
          '>',
          '>',
          15,
          'All',
        ],
        ['19:30', 'Meeting Rules Introduction (SAA)', '>', '>', 3, 'Joyce'],
        ['19:33', 'Opening Remarks (President)', '>', '>', 2, 'Frank'],
        [
          '19:35',
          'TOM (Toastmaster of Meeting) Introduction',
          '>',
          '>',
          2,
          'Rui',
        ],
        ['19:37', 'Timer', '>', '>', 3, 'Max'],
        ['19:40', 'Hark Master', '>', '>', 3, 'Mia'],
        [
          '19:43',
          'Guests Self Introduction (30s per guest)',
          '>',
          '>',
          8,
          'Joseph',
        ],
      ],
    };

    return createArraySection(
      worksheet,
      openingData,
      startRow,
      showTitle,
      fontStyle
    );
  };

  // Function to create Evaluation Section
  const createEvaluation = (
    worksheet: ExcelJS.Worksheet,
    startRow: number,
    showTitle: boolean = true,
    fontStyle?: { name?: string; size?: number }
  ): number => {
    const evaluationData: ArraySectionData = {
      title: 'Evaluation Session',
      headers: [
        'Time',
        'Evaluation Session',
        '>',
        '>',
        'Duration',
        'Role Taker',
      ],
      columnWidths: [18, 24, 24, 24, 8, 24], // Custom column widths for this section
      rows: [
        ['20:42', 'Table Topic Evaluation', '>', '>', 7, 'Emily'],
        ['20:50', 'Prepared Speech 1 Evaluation', '>', '>', 3, 'Phyllis'],
        ['20:54', 'Prepared Speech 2 Evaluation', '>', '>', 4, 'Amanda'],
      ],
    };

    return createArraySection(
      worksheet,
      evaluationData,
      startRow,
      showTitle,
      fontStyle
    );
  };

  // Function to create Prepared Speech Section
  // const createPreparedSpeechSection = (
  //   worksheet: ExcelJS.Worksheet,
  //   startRow: number,
  //   showTitle: boolean = true,
  //   fontStyle?: { name?: string; size?: number }
  // ): number => {
  //   const preparedSpeechData: ArraySectionData = {
  //     title: 'Prepared Speech Session',
  //     headers: ['Time', 'Title', '>', '>', 'Duration', 'Role Taker'],
  //     columnWidths: [18, 24, 24, 24, 8, 24],
  //     rows: [
  //       [
  //         '20:13',
  //         'Engaging humor 3.1:',
  //         'Captivate your audience',
  //         'with humor',
  //         7,
  //         'Frank',
  //       ],
  //       ['Prepared Speech 2', 'Title', '', '', '', ''],
  //       [
  //         '20:21',
  //         'Dynamic leadership 3.1:',
  //         'Effective body language',
  //         'Do you fear aging?',
  //         7,
  //         'Libra',
  //       ],
  //     ],
  //   };

  //   return createArraySection(
  //     worksheet,
  //     preparedSpeechData,
  //     startRow,
  //     showTitle,
  //     fontStyle
  //   );
  // };

  // Function to create Facilitators' Report Section using array-based data
  const createFacilitatorsReport = (
    worksheet: ExcelJS.Worksheet,
    startRow: number,
    showTitle: boolean = true,
    fontStyle?: { name?: string; size?: number }
  ): number => {
    const facilitatorsData: ArraySectionData = {
      title: "Facilitators' Report",
      headers: [
        'Time',
        "Facilitators' Report",
        '>',
        '>',
        'Duration',
        'Role Taker',
      ],
      columnWidths: [18, 24, 24, 24, 8, 24], // Custom column widths for this section
      rows: [
        ['20:58', "Timer's Report", '>', '>', 2, 'Max'],
        ['21:01', 'Hark Master Pop Quiz Time', '>', '>', 5, 'Mia'],
        ['21:07', 'General Evaluation', '>', '>', 8, 'Karman'],
        ['21:16', 'Voting Section (TOM)', '>', '>', 2, 'Rui'],
        ['21:19', 'Moment of Truth', '>', '>', 7, 'Leta'],
        ['21:27', 'Awards(President)', '>', '>', 3, 'Frank'],
        ['21:30', 'Closing Remarks(President)', '>', '>', 1, 'Frank'],
      ],
    };

    return createArraySection(
      worksheet,
      facilitatorsData,
      startRow,
      showTitle,
      fontStyle
    );
  };

  // Create workbook function that will call the section creation functions
  const createWorkbook = async () => {
    // Create a new workbook and worksheet
    const workbook = new ExcelJS.Workbook();
    const worksheet = workbook.addWorksheet('Meeting Agenda');

    // Set default column widths
    worksheet.columns = [
      { width: 18 },
      { width: 24 },
      { width: 24 },
      { width: 24 },
      { width: 8 },
      { width: 24 },
    ];

    // Start adding sections - we're starting with row 1
    let currentRow = 1;

    // Add a spacing row for demonstration - this would be replaced with header later
    worksheet.addRow(['SOARHIGH TOASTMASTERS CLUB']);
    currentRow++; // Adding some space

    // Add Opening and Intro Section - Don't show title and set Arial font size 9
    currentRow = createOpeningAndIntro(worksheet, currentRow, false, {
      name: 'Arial',
      size: 9,
    });

    // Add spacing row
    // worksheet.addRow([]);
    // currentRow++;

    // Add Table Topic Section - Don't show title and set Arial font size 9
    currentRow = createTableTopicSection(worksheet, currentRow, false, {
      name: 'Arial',
      size: 9,
    });

    // Add spacing row
    // worksheet.addRow([]);
    // currentRow++;

    // Add Prepared Speech Section - Don't show title and set Arial font size 9
    // currentRow = createPreparedSpeechSection(worksheet, currentRow, false, {
    //   name: 'Arial',
    //   size: 9,
    // });

    // Add spacing row
    // worksheet.addRow([]);
    // currentRow++;

    // Add Evaluation Section - Don't show title and set Arial font size 9
    currentRow = createEvaluation(worksheet, currentRow, false, {
      name: 'Arial',
      size: 9,
    });

    // Add spacing row
    // worksheet.addRow([]);
    // currentRow++;

    // Add Facilitators' Report Section - Don't show title and set Arial font size 9
    createFacilitatorsReport(worksheet, currentRow, false, {
      name: 'Arial',
      size: 9,
    });

    return { workbook, worksheet };
  };

  // Function to generate and download Excel file
  const generateExcel = async () => {
    setIsGenerating(true);
    setIsReady(false);

    try {
      const { workbook } = await createWorkbook();

      // Generate Excel file as a buffer
      const buffer = await workbook.xlsx.writeBuffer();

      // Create a Blob from the buffer
      const blob = new Blob([buffer], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      });

      // Save the file using FileSaver
      saveAs(blob, 'SoarhighMeetingAgenda.xlsx');

      setIsReady(true);
    } catch (error) {
      console.error('Error generating Excel file:', error);
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className='flex flex-col items-center p-6 bg-white rounded-lg shadow-md max-w-4xl mx-auto my-8'>
      <h1 className='text-2xl font-bold mb-6'>
        Toastmasters Meeting Agenda Generator
      </h1>

      <div className='w-full mb-6'>
        <p className='text-gray-700 mb-4'>
          This component generates an Excel file with the Toastmasters meeting
          agenda. Currently implemented: Opening/Intro, Evaluation, and
          Facilitators&apos; Report sections.
        </p>
      </div>

      <div className='flex gap-4 mb-6'>
        <button
          onClick={generateExcel}
          disabled={isGenerating}
          className='px-6 py-3 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 disabled:opacity-50 transition-colors'
        >
          {isGenerating ? 'Generating...' : 'Download Excel File'}
        </button>
      </div>

      {isReady && (
        <div className='mt-2 text-green-600 font-semibold'>
          Excel file downloaded successfully!
        </div>
      )}

      {/* Use the AgendaExcelPreviewer component */}
      <AgendaExcelPreviewer
        createWorkbook={createWorkbook}
        autoPreview={true}
      />

      <div className='mt-8 text-sm text-gray-500'>
        <p>
          Note: This uses the ExcelJS library to generate the file in the
          browser and FileSaver.js to download it.
        </p>
      </div>
    </div>
  );
};

export default AgendaExcelGenerator;
