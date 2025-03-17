'use client';

import React, { useState } from 'react';
import * as ExcelJS from 'exceljs';
import { saveAs } from 'file-saver';
import AgendaExcelPreviewer from './AgendaExcelPreviewer';

// Define types for consistent data structure
type ActivityRow = {
  time: string;
  activity: string;
  duration: number | string;
  roleTaker: string;
};

type SectionData = {
  title: string;
  headers: string[];
  rows: ActivityRow[];
  columnWidths?: number[]; // Add column widths configuration
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

  // Generic function to create a standard 4-column section
  const createStandardSection = (
    worksheet: ExcelJS.Worksheet,
    data: SectionData,
    startRow: number,
    showTitle: boolean = true, // Add parameter to control title visibility
    fontStyle?: { name?: string; size?: number } // Optional font style parameter
  ): number => {
    // Apply column widths if provided
    if (data.columnWidths && data.columnWidths.length > 0) {
      // Get current columns
      const currentColumns = worksheet.columns || [];

      // Apply new widths to columns
      data.columnWidths.forEach((width, index) => {
        // Get column index (0-based)
        const colIndex = index;

        // Check if column exists
        if (colIndex < currentColumns.length) {
          // Update existing column
          worksheet.getColumn(colIndex + 1).width = width;
        } else {
          // Should not happen normally, but handle edge case
          const newColumn: Partial<ExcelJS.Column> = { width };
          worksheet.columns = [...(worksheet.columns || []), newColumn];
        }
      });
    }

    // Add section title row if showTitle is true
    if (showTitle) {
      const titleRow = worksheet.addRow([data.title]);
      titleRow.height = 20;
      worksheet.mergeCells(`A${startRow}:D${startRow}`);

      const titleCell = titleRow.getCell(1);
      const headerStyle = getHeaderStyle();

      // Apply custom font style if provided
      if (fontStyle) {
        if (fontStyle.name)
          headerStyle.font = {
            ...(headerStyle.font as ExcelJS.Font),
            name: fontStyle.name,
          };
        if (fontStyle.size)
          headerStyle.font = {
            ...(headerStyle.font as ExcelJS.Font),
            size: fontStyle.size,
          };
      }

      titleCell.fill = headerStyle.fill as ExcelJS.Fill;
      titleCell.font = headerStyle.font as ExcelJS.Font;
      titleCell.border = headerStyle.border as ExcelJS.Borders;
      titleCell.alignment = headerStyle.alignment as ExcelJS.Alignment;

      startRow++;
    }

    // Add header row
    const headerRow = worksheet.addRow(data.headers);
    headerRow.height = 20;

    const headerStyle = getHeaderStyle();

    // Apply custom font style if provided
    if (fontStyle) {
      if (fontStyle.name)
        headerStyle.font = {
          ...(headerStyle.font as ExcelJS.Font),
          name: fontStyle.name,
        };
      if (fontStyle.size)
        headerStyle.font = {
          ...(headerStyle.font as ExcelJS.Font),
          size: fontStyle.size,
        };
    }

    headerRow.eachCell((cell) => {
      cell.fill = headerStyle.fill as ExcelJS.Fill;
      cell.font = headerStyle.font as ExcelJS.Font;
      cell.border = headerStyle.border as ExcelJS.Borders;
      cell.alignment = headerStyle.alignment as ExcelJS.Alignment;
    });

    startRow++;

    // Add data rows
    data.rows.forEach((rowData) => {
      const dataRow = worksheet.addRow([
        rowData.time,
        rowData.activity,
        rowData.duration,
        rowData.roleTaker,
      ]);

      const rowStyle = getRowStyle();

      // Apply custom font style if provided
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

        // Apply specific alignment based on column
        if (colNumber === 1) {
          // Time column
          cell.alignment = { vertical: 'middle', horizontal: 'center' };
        } else if (colNumber === 2) {
          // Activity column
          cell.alignment = { vertical: 'middle', horizontal: 'left' };
        } else if (colNumber === 3) {
          // Duration column
          cell.alignment = { vertical: 'middle', horizontal: 'center' };
        } else if (colNumber === 4) {
          // Role Taker column
          cell.alignment = { vertical: 'middle', horizontal: 'center' };
        }
      });

      startRow++;
    });

    return startRow;
  };

  // Function to create Opening and Intro Section
  const createOpeningAndIntro = (
    worksheet: ExcelJS.Worksheet,
    startRow: number,
    showTitle: boolean = true,
    fontStyle?: { name?: string; size?: number }
  ): number => {
    const openingData: SectionData = {
      title: 'Opening and Intro Session',
      headers: ['Time', 'Activities', 'Duration', 'Role Taker'],
      columnWidths: [18, 72, 8, 24], // Custom column widths for this section
      rows: [
        {
          time: '19:15',
          activity: 'Members and Guests Registration, Warm up',
          duration: 15,
          roleTaker: 'All',
        },
        {
          time: '19:30',
          activity: 'Meeting Rules Introduction (SAA)',
          duration: 3,
          roleTaker: 'Joyce',
        },
        {
          time: '19:33',
          activity: 'Opening Remarks (President)',
          duration: 2,
          roleTaker: 'Frank',
        },
        {
          time: '19:35',
          activity: 'TOM (Toastmaster of Meeting) Introduction',
          duration: 2,
          roleTaker: 'Rui',
        },
        { time: '19:37', activity: 'Timer', duration: 3, roleTaker: 'Max' },
        {
          time: '19:40',
          activity: 'Hark Master',
          duration: 3,
          roleTaker: 'Mia',
        },
        {
          time: '19:43',
          activity: 'Guests Self Introduction (30s per guest)',
          duration: 8,
          roleTaker: 'Joseph',
        },
      ],
    };

    return createStandardSection(
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
    const evaluationData: SectionData = {
      title: 'Evaluation Session',
      headers: ['Time', 'Evaluation Session', 'Duration', 'Role Taker'],
      columnWidths: [18, 72, 8, 24], // Custom column widths for this section
      rows: [
        {
          time: '20:42',
          activity: 'Table Topic Evaluation',
          duration: 7,
          roleTaker: 'Emily',
        },
        {
          time: '20:50',
          activity: 'Prepared Speech 1 Evaluation',
          duration: 3,
          roleTaker: 'Phyllis',
        },
        {
          time: '20:54',
          activity: 'Prepared Speech 2 Evaluation',
          duration: 3,
          roleTaker: 'Amanda',
        },
      ],
    };

    return createStandardSection(
      worksheet,
      evaluationData,
      startRow,
      showTitle,
      fontStyle
    );
  };

  // Function to create Facilitators' Report Section
  const createFacilitatorsReport = (
    worksheet: ExcelJS.Worksheet,
    startRow: number,
    showTitle: boolean = true,
    fontStyle?: { name?: string; size?: number }
  ): number => {
    const facilitatorsData: SectionData = {
      title: "Facilitators' Report",
      headers: ['Time', "Facilitators' Report", 'Duration', 'Role Taker'],
      columnWidths: [18, 72, 8, 24], // Custom column widths for this section
      rows: [
        {
          time: '20:58',
          activity: "Timer's Report",
          duration: 2,
          roleTaker: 'Max',
        },
        {
          time: '21:01',
          activity: 'Hark Master Pop Quiz Time',
          duration: 5,
          roleTaker: 'Mia',
        },
        {
          time: '21:07',
          activity: 'General Evaluation',
          duration: 8,
          roleTaker: 'Karman',
        },
        {
          time: '21:16',
          activity: 'Voting Section (TOM)',
          duration: 2,
          roleTaker: 'Rui',
        },
        {
          time: '21:19',
          activity: 'Moment of Truth',
          duration: 7,
          roleTaker: 'Leta',
        },
        {
          time: '21:27',
          activity: 'Awards(President)',
          duration: 3,
          roleTaker: 'Frank',
        },
        {
          time: '21:30',
          activity: 'Closing Remarks(President)',
          duration: 1,
          roleTaker: 'Frank',
        },
      ],
    };

    return createStandardSection(
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
      { width: 10 }, // A - Time column
      { width: 40 }, // B - Activities/content column
      { width: 15 }, // C - Duration column
      { width: 15 }, // D - Role Taker column
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
