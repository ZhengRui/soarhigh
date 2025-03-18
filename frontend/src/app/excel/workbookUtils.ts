import * as ExcelJS from 'exceljs';

// Define a new section data type with array-based rows
type CellData =
  | string
  | number
  | {
      text: string | number;
      style?: {
        alignment?: {
          horizontal?: 'left' | 'center' | 'right';
          vertical?: 'top' | 'middle' | 'bottom';
          wrapText?: boolean;
        };
        fill?: {
          type: 'pattern';
          pattern: 'solid';
          fgColor: { argb: string }; // ARGB format like 'FFFF0000' for red
        };
        font?: {
          bold?: boolean;
          italic?: boolean;
          color?: { argb: string };
          size?: number;
        };
      };
    };

// Define vertical merge instructions
type VerticalMerge = {
  col: number; // 1-indexed column number
  startRow: number; // 1-indexed start row (relative to section)
  endRow: number; // 1-indexed end row (relative to section)
};

type ArraySectionData = {
  title: string;
  headers: string[];
  columnWidths?: number[];
  rows: Array<CellData[]>;
  verticalMerges?: VerticalMerge[]; // New property for vertical merges
};

const defaultColumnWidths = [18, 21, 24, 30, 8, 24];

// Function to fetch an image and convert it to base64
const getImageAsBase64 = async (url: string): Promise<string> => {
  try {
    const response = await fetch(url);
    const blob = await response.blob();

    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        const base64data = reader.result as string;
        // Extract the base64 part without the data URL prefix
        const base64Content = base64data.split(',')[1];
        resolve(base64Content);
      };
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  } catch (error) {
    console.error('Error loading image:', error);
    throw error;
  }
};

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

const getTitleStyle = (): Partial<ExcelJS.Style> => ({
  font: {
    bold: true,
    name: 'Arial',
    size: 9,
    color: { argb: 'FFFFFFFF' }, // White text
  },
  fill: {
    type: 'pattern',
    pattern: 'solid',
    fgColor: { argb: 'FF343e4e' }, // Dark blue background
  },
  alignment: {
    vertical: 'middle',
    horizontal: 'center',
  },
  border: {
    top: { style: 'thin' },
    left: { style: 'thin' },
    bottom: { style: 'thin' },
    right: { style: 'thin' },
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

  // Keep track of the initial startRow to calculate relative row positions
  const initialStartRow = startRow;
  const nColumn = data.rows[0].length;

  // Add section title row if showTitle is true
  if (showTitle) {
    const titleStyle = getTitleStyle();
    const titleRow = worksheet.addRow([data.title]);
    titleRow.eachCell((cell) => {
      cell.font = titleStyle.font as ExcelJS.Font;
      cell.alignment = titleStyle.alignment as ExcelJS.Alignment;
      cell.fill = titleStyle.fill as ExcelJS.Fill;
      cell.border = titleStyle.border as ExcelJS.Borders;
    });
    worksheet.mergeCells(startRow, 1, startRow, nColumn);
    startRow++;
  }

  if (data.headers.length > 0) {
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
  }

  // Add data rows
  data.rows.forEach((rowData) => {
    // Filter out '>' in the row data (used for merging)
    const dataRow = worksheet.addRow(
      rowData.map((cell) => (typeof cell === 'object' ? cell.text : cell))
    );

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

      // Apply cell-specific styles
      const cellData = rowData[colNumber - 1];
      if (typeof cellData === 'object' && cellData.style) {
        // Apply alignment if specified
        if (cellData.style.alignment) {
          cell.alignment = {
            ...cell.alignment,
            ...cellData.style.alignment,
            // Handle wrapText separately to ensure it's properly applied
            wrapText: cellData.style.alignment.wrapText || false,
          };
        }

        // Apply fill/background color if specified
        if (cellData.style.fill) {
          cell.fill = cellData.style.fill as ExcelJS.Fill;
        }

        // Apply font styling if specified
        if (cellData.style.font) {
          cell.font = {
            ...cell.font,
            ...cellData.style.font,
          } as ExcelJS.Font;
        }
      }
    });

    // Handle cell merging in rows
    let rowMergeStart = -1;
    let rowMergeCount = 0;

    rowData.forEach((cell, index) => {
      const cellValue = typeof cell === 'object' ? cell.text : cell;
      if (cellValue !== '>' && rowMergeStart === -1) {
        // Start of a potential merge
        rowMergeStart = index;
        rowMergeCount = 1;
      } else if (cellValue === '>' && rowMergeStart !== -1) {
        // Continue merge
        rowMergeCount++;
      }

      // End of row or next non-merge cell
      if (
        (cellValue !== '>' &&
          rowMergeStart !== -1 &&
          rowMergeStart !== index) ||
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
        if (cellValue !== '>') {
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

  // Process vertical merges if provided
  if (data.verticalMerges && data.verticalMerges.length > 0) {
    data.verticalMerges.forEach((merge) => {
      // Calculate absolute row positions
      const headerOffset = showTitle ? 2 : 1; // Adjust based on whether title is shown
      const absStartRow = initialStartRow + headerOffset + merge.startRow - 1;
      const absEndRow = initialStartRow + headerOffset + merge.endRow - 1;

      // Perform the vertical merge
      worksheet.mergeCells(absStartRow, merge.col, absEndRow, merge.col);
    });
  }

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
    columnWidths: defaultColumnWidths, // Custom column widths for this section
    rows: [
      ['19:52', 'TTM (Table Topic Master) Opening', '>', '>', 4, 'Rui'],
      [
        '19:56',
        'Aging',
        {
          text: 'WOT(Word of Today):',
          style: { alignment: { horizontal: 'right' } },
        },
        'Immortal',
        16,
        'All',
      ],
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
    columnWidths: defaultColumnWidths, // Custom column widths for this section
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
    headers: ['Time', 'Evaluation Session', '>', '>', 'Duration', 'Role Taker'],
    columnWidths: defaultColumnWidths, // Custom column widths for this section
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
const createPreparedSpeechSection = (
  worksheet: ExcelJS.Worksheet,
  startRow: number,
  showTitle: boolean = true,
  fontStyle?: { name?: string; size?: number }
): number => {
  const preparedSpeechData: ArraySectionData = {
    title: 'Prepared Speech Session',
    headers: [
      'Time',
      'Prepared Speech Session',
      '>',
      '>',
      'Duration',
      'Role Taker',
    ],
    columnWidths: defaultColumnWidths,
    rows: [
      // Speech 1 - Row 1
      [
        '20:13',
        'Prepared Speech 1',
        { text: 'Title', style: { alignment: { horizontal: 'center' } } },
        '>',
        7,
        'Frank',
      ],
      // Speech 1 - Row 2
      [
        '', // Time will be merged vertically
        {
          text: 'Engaging humor 3.1:\nEngaging your audience with humor',
          style: { alignment: { vertical: 'middle', wrapText: true } },
        },
        {
          text: 'Failures are learned experiences',
          style: { alignment: { horizontal: 'center' } },
        },
        '>',
        '', // Duration will be merged vertically
        '', // Role Taker will be merged vertically
      ],
      // Speech 2 - Row 1
      [
        '20:21',
        'Prepared Speech 2',
        { text: 'Title', style: { alignment: { horizontal: 'center' } } },
        '>',
        7,
        'Libra',
      ],
      // Speech 2 - Row 2
      [
        '', // Time will be merged vertically
        {
          text: 'Dynamic leadership 3.1:\nEffective body language',
          style: { alignment: { vertical: 'middle', wrapText: true } },
        },
        {
          text: 'Do you fear aging?',
          style: { alignment: { horizontal: 'center' } },
        },
        '>',
        '', // Duration will be merged vertically
        '', // Role Taker will be merged vertically
      ],
    ],
    // Define vertical merges for Time, Duration and Role Taker columns
    verticalMerges: [
      // Speech 1 merges
      { col: 1, startRow: 1, endRow: 2 }, // Time column
      { col: 5, startRow: 1, endRow: 2 }, // Duration column
      { col: 6, startRow: 1, endRow: 2 }, // Role Taker column
      // Speech 2 merges
      { col: 1, startRow: 3, endRow: 4 }, // Time column
      { col: 5, startRow: 3, endRow: 4 }, // Duration column
      { col: 6, startRow: 3, endRow: 4 }, // Role Taker column
    ],
  };

  startRow = createArraySection(
    worksheet,
    preparedSpeechData,
    startRow,
    showTitle,
    fontStyle
  );

  const nSpeeches = preparedSpeechData.rows.length / 2;
  for (let i = 0; i < nSpeeches; i++) {
    worksheet.getRow(startRow - 2 * i - 1).height = 48;
  }

  return startRow;
};

// Function to create Tea Break row
const createTeaBreak = (
  worksheet: ExcelJS.Worksheet,
  startRow: number,
  fontStyle?: { name?: string; size?: number }
): number => {
  // Add the tea break row directly without using createArraySection
  const dataRow = worksheet.addRow([
    '20:29',
    'Tea Break & Group Photos',
    '',
    '',
    12,
    'All',
  ]);

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

  // Apply styling to each cell
  dataRow.eachCell((cell, colNumber) => {
    cell.border = rowStyle.border as ExcelJS.Borders;
    cell.font = rowStyle.font as ExcelJS.Font;

    // Center align for Time, Duration, Role Taker columns
    if (colNumber === 1 || colNumber === 5 || colNumber === 6) {
      cell.alignment = { vertical: 'middle', horizontal: 'center' };
    } else {
      // Left align for activity columns
      cell.alignment = { vertical: 'middle', horizontal: 'left' };
    }
  });

  // Merge the activity cells (columns 2-4)
  worksheet.mergeCells(startRow, 2, startRow, 4);

  // Return the next row
  return startRow + 1;
};

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
    columnWidths: defaultColumnWidths, // Custom column widths for this section
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

// Function to create Time Rules Section
const createTimeRules = (
  worksheet: ExcelJS.Worksheet,
  startRow: number,
  showTitle: boolean = true,
  fontStyle?: { name?: string; size?: number }
): number => {
  const timeRulesData: ArraySectionData = {
    title: 'Time Rules',
    headers: [],
    columnWidths: defaultColumnWidths, // Custom column widths for this section
    rows: [
      // Type row
      [
        'Type',
        {
          text: 'Speech <=3min\nTable Topics & Most Evaluations',
          style: { alignment: { horizontal: 'center', wrapText: true } },
        },
        '>',
        {
          text: '3min < Speech <=10min\nMost prepared speeches & GE',
          style: { alignment: { horizontal: 'center', wrapText: true } },
        },
        {
          text: 'Speech >10min\nLong Speeches & Workshops',
          style: { alignment: { horizontal: 'center', wrapText: true } },
        },
        '>',
      ],

      // Green Card row
      [
        {
          text: 'Green Card',
          style: {
            fill: {
              type: 'pattern',
              pattern: 'solid',
              fgColor: { argb: 'FF00B050' }, // Green color
            },
            font: { color: { argb: 'FFFFFFFF' }, bold: true }, // White text
            alignment: { horizontal: 'center' },
          },
        },
        {
          text: '1 minute left',
          style: { alignment: { horizontal: 'center' } },
        },
        '>',
        {
          text: '1 minute left',
          style: { alignment: { horizontal: 'center' } },
        },
        {
          text: '5 minutes left',
          style: { alignment: { horizontal: 'center' } },
        },
        '>',
      ],
      // Yellow Card row
      [
        {
          text: 'Yellow Card',
          style: {
            fill: {
              type: 'pattern',
              pattern: 'solid',
              fgColor: { argb: 'FFFFC000' }, // Yellow color
            },
            font: { color: { argb: 'FF000000' }, bold: true }, // Black text
            alignment: { horizontal: 'center' },
          },
        },
        {
          text: '30 seconds left',
          style: { alignment: { horizontal: 'center' } },
        },
        '>',
        {
          text: '30 seconds left',
          style: { alignment: { horizontal: 'center' } },
        },
        {
          text: '2 minutes left',
          style: { alignment: { horizontal: 'center' } },
        },
        '>',
      ],
      // Red Card row (with explanation)
      [
        {
          text: 'Red Card',
          style: {
            fill: {
              type: 'pattern',
              pattern: 'solid',
              fgColor: { argb: 'FFFF0000' }, // Red color
            },
            font: { color: { argb: 'FFFFFFFF' }, bold: true }, // White text
            alignment: { horizontal: 'center' },
          },
        },
        {
          text: "Red card means time's up, but you still have extra 30s to conclude/close your speech, \nafter 30s, we will ring the bell, which means the speaker must stop and give back the stage.",
          style: {
            alignment: {
              horizontal: 'left',
              wrapText: true,
            },
          },
        },
        '>',
        '>',
        '>',
        '>',
      ],
    ],
  };

  startRow = createArraySection(
    worksheet,
    timeRulesData,
    startRow,
    showTitle,
    fontStyle
  );

  worksheet.getRow(startRow - 1).height = 32;

  return startRow;
};

// Function to create Team/Officer Section
const createTeam = (
  worksheet: ExcelJS.Worksheet,
  startRow: number,
  showTitle: boolean = true,
  fontStyle?: { name?: string; size?: number }
): number => {
  const teamData: ArraySectionData = {
    title: 'Soarhigh Team',
    headers: [
      'Soarhigh Officer',
      '>',
      'Toastmaster Pathways',
      'Meeting Rules',
      'Features of Soarhigh',
      '>',
    ],
    columnWidths: defaultColumnWidths,
    rows: [
      [
        {
          text: 'President',
          style: {
            fill: {
              type: 'pattern',
              pattern: 'solid',
              fgColor: { argb: 'FF343e4e' },
            },
            font: { color: { argb: 'FFFFFFFF' }, bold: true }, // White text
          },
        },
        { text: 'Libra Lee', style: { alignment: { horizontal: 'center' } } },
        {
          text: 'DL-Dynamic leadership\nMS-Motivational Strategies\nPl-Persuasive Influence\nPM-Presentation Mastery\nVC-Visionary Communication\nEH-Engaging Humor\n\nDL-动态领导力\nMS-激励策略\nPl-有说服力的影响\nPM-精通演讲\nVC-愿景沟通\nEH-善用幽默',
          style: {
            alignment: {
              vertical: 'top',
              horizontal: 'left',
              wrapText: true,
            },
            font: {
              size: 8,
            },
          },
        },
        {
          text: '1. Please keep in mind the 4 taboos: \nSEX\nRELIGION\nPOLITICS\nCOMMERCIALS\n\n2. Please silence your phone during the meeting.\n\n3. Please shake hands with the host when going up and down the stage.',
          style: {
            alignment: {
              vertical: 'top',
              horizontal: 'left',
              wrapText: true,
            },
            font: {
              size: 8,
            },
          },
        },
        {
          text: "Soarhigh Toastmasters Club is the one and only 100% English Club in Bao'an. We are a family to love, to care, to laugh, and to inspire. \n\n搜嗨头马国际演讲俱乐部，深圳宝安区唯一的100%英文俱乐部，主打松弛感第一，包容度第一，以自己的节奏，享受每一步的成长。\n\nOur slogan: Soarhigh, so high, takes me fly!",
          style: {
            alignment: {
              vertical: 'top',
              horizontal: 'left',
              wrapText: true,
            },
            font: {
              size: 8,
            },
          },
        },
        '',
      ],
      [
        {
          text: 'VPE (Vice President Education)',
          style: {
            fill: {
              type: 'pattern',
              pattern: 'solid',
              fgColor: { argb: 'FF343e4e' },
            },
            font: { color: { argb: 'FFFFFFFF' }, bold: true }, // White text
            alignment: {
              wrapText: true,
            },
          },
        },
        { text: 'Rui Zheng', style: { alignment: { horizontal: 'center' } } },
        '',
        '',
        '',
        '',
      ],
      [
        {
          text: 'VPM (Vice President Membership)',
          style: {
            fill: {
              type: 'pattern',
              pattern: 'solid',
              fgColor: { argb: 'FF343e4e' },
            },
            font: { color: { argb: 'FFFFFFFF' }, bold: true }, // White text
            alignment: {
              wrapText: true,
            },
          },
        },
        {
          text: 'Joseph Zhang',
          style: { alignment: { horizontal: 'center' } },
        },
        '',
        '',
        '',
        '',
      ],
      [
        {
          text: 'VPPR (Vice President Public Relations)',
          style: {
            fill: {
              type: 'pattern',
              pattern: 'solid',
              fgColor: { argb: 'FF343e4e' },
            },
            font: { color: { argb: 'FFFFFFFF' }, bold: true }, // White text
            alignment: {
              wrapText: true,
            },
          },
        },
        {
          text: 'Owen Liang',
          style: { alignment: { horizontal: 'center' } },
        },
        '',
        '',
        '',
        '',
      ],
      [
        {
          text: 'Secretary',
          style: {
            fill: {
              type: 'pattern',
              pattern: 'solid',
              fgColor: { argb: 'FF343e4e' },
            },
            font: { color: { argb: 'FFFFFFFF' }, bold: true }, // White text
            alignment: {
              wrapText: true,
            },
          },
        },
        {
          text: 'Jessical Peng',
          style: { alignment: { horizontal: 'center' } },
        },
        '',
        '',
        '',
        '',
      ],
      [
        {
          text: 'Treasurer',
          style: {
            fill: {
              type: 'pattern',
              pattern: 'solid',
              fgColor: { argb: 'FF343e4e' },
            },
            font: { color: { argb: 'FFFFFFFF' }, bold: true }, // White text
            alignment: {
              wrapText: true,
            },
          },
        },
        { text: 'Max Long', style: { alignment: { horizontal: 'center' } } },
        '',
        '',
        '',
        '',
      ],
      [
        {
          text: 'SAA (Sergeant At Arms)',
          style: {
            fill: {
              type: 'pattern',
              pattern: 'solid',
              fgColor: { argb: 'FF343e4e' },
            },
            font: { color: { argb: 'FFFFFFFF' }, bold: true }, // White text
            alignment: {
              wrapText: true,
            },
          },
        },
        {
          text: 'Joyce Feng',
          style: { alignment: { horizontal: 'center' } },
        },
        '',
        '',
        '',
        '',
      ],
      [
        {
          text: 'IPP (Immediate Past President)',
          style: {
            fill: {
              type: 'pattern',
              pattern: 'solid',
              fgColor: { argb: 'FF343e4e' },
            },
            font: { color: { argb: 'FFFFFFFF' }, bold: true }, // White text
            alignment: {
              wrapText: true,
            },
          },
        },
        {
          text: 'Jessical Peng',
          style: { alignment: { horizontal: 'center' } },
        },
        '',
        '',
        '',
        '',
      ],
    ],

    verticalMerges: [
      { col: 3, startRow: 1, endRow: 8 },
      { col: 4, startRow: 1, endRow: 8 },
    ],
  };

  startRow = createArraySection(
    worksheet,
    teamData,
    startRow,
    showTitle,
    fontStyle
  );

  worksheet.mergeCells(startRow - 8, 5, startRow - 1, 6);

  return startRow;
};

// Function to create table header section
const createTableHeader = (
  worksheet: ExcelJS.Worksheet,
  startRow: number,
  showTitle: boolean = true,
  fontStyle?: { name?: string; size?: number }
): number => {
  const tableHeaderData: ArraySectionData = {
    title: 'Agenda Table Header',
    headers: [],
    columnWidths: defaultColumnWidths,
    rows: [
      [
        '',
        {
          text: 'SOARHIGH TOASTMASTERS CLUB',
          style: {
            alignment: { horizontal: 'center' },
            font: { size: 14, color: { argb: 'FFFFFFFF' } },
          },
        },
        '>',
        '>',
        '>',
        {
          text: 'Contact VPM to join us! 👇',
          style: {
            font: { color: { argb: 'FFFFFFFF' } },
          },
        },
      ],
      [
        '',
        '',
        {
          text: '387th Meeting',
          style: {
            font: { size: 12, color: { argb: 'FFFFFFFF' } },
          },
        },
        {
          text: 'Aging',
          style: {
            font: { size: 12, color: { argb: 'FFFFFFFF' } },
          },
        },
        '',
        '',
      ],
      [
        '',
        '',
        {
          text: 'Nov.6, 2024(Wed)',
          style: {
            font: { color: { argb: 'FFFFFFFF' } },
          },
        },
        {
          text: 'Time: 19:15-21:30',
          style: {
            font: { color: { argb: 'FFFFFFFF' } },
          },
        },
        '',
        '',
      ],
      [
        '',
        '',
        {
          text: "Venue: JOININ HUB, 6th Xin'an Rd,Bao'an (Metro line 1 Baoti / line 11 Bao'an)",
          style: {
            font: { color: { argb: 'FFFFFFFF' } },
          },
        },
        '>',
        '>',
        '>',
      ],
      [
        '',
        {
          text: '👆 WeChat Subscription',
          style: {
            font: { color: { argb: 'FFFFFFFF' } },
          },
        },
        {
          text: 'Club#4234120 | Area A4 | Division A | District 118',
          style: {
            font: { color: { argb: 'FFFFFFFF' } },
          },
        },
        '>',
        {
          text: 'Meeting Manager: Rui Zheng',
          style: {
            alignment: { horizontal: 'left' },
            font: { color: { argb: 'FFFFFFFF' } },
          },
        },
        '>',
      ],
      [
        {
          text: 'Toastmasters International Mission: We empower individuals to become more effective communicators and leaders.',
          style: {
            alignment: { horizontal: 'left' },
            font: { size: 10 },
          },
        },
        '>',
        '>',
        '>',
        '>',
        '>',
      ],
      [
        {
          text: 'Toastmasters International Values: Respect, Integrity, Service and Excellence',
          style: {
            alignment: { horizontal: 'left' },
            font: { size: 10 },
          },
        },
        '>',
        '>',
        '>',
        '>',
        '>',
      ],
    ],
  };

  startRow = createArraySection(
    worksheet,
    tableHeaderData,
    startRow,
    showTitle,
    fontStyle
  );

  worksheet.getRows(startRow - 7, startRow - 3)?.forEach((row) => {
    row.height = 20;

    row.eachCell((cell) => {
      cell.border = {
        top: { style: 'thin', color: { argb: 'FF5e3637' } },
        bottom: { style: 'thin', color: { argb: 'FF5e3637' } },
        left: { style: 'thin', color: { argb: 'FF5e3637' } },
        right: { style: 'thin', color: { argb: 'FF5e3637' } },
      };
      cell.fill = {
        type: 'pattern',
        pattern: 'solid',
        fgColor: { argb: 'FF5e3637' },
      };
    });
  });

  return startRow;
};

// Create workbook function that will call the section creation functions
export const createWorkbook = async () => {
  // Create a new workbook and worksheet
  const workbook = new ExcelJS.Workbook();
  const worksheet = workbook.addWorksheet('Meeting Agenda');

  // Set default column widths
  worksheet.columns = defaultColumnWidths.map((width) => ({ width }));

  // Start adding sections - we're starting with row 1
  let currentRow = 1;

  // Add Table Header Section
  currentRow = createTableHeader(worksheet, currentRow, false, {
    name: 'Arial',
    size: 9,
  });

  // Add Opening and Intro Section - Don't show title and set Arial font size 9
  currentRow = createOpeningAndIntro(worksheet, currentRow, false, {
    name: 'Arial',
    size: 9,
  });

  // Add Table Topic Section - Don't show title and set Arial font size 9
  currentRow = createTableTopicSection(worksheet, currentRow, false, {
    name: 'Arial',
    size: 9,
  });

  // Add Prepared Speech Section - Don't show title and set Arial font size 9
  currentRow = createPreparedSpeechSection(worksheet, currentRow, false, {
    name: 'Arial',
    size: 9,
  });

  // Add Tea Break row
  currentRow = createTeaBreak(worksheet, currentRow, {
    name: 'Arial',
    size: 9,
  });

  // Add Evaluation Section - Don't show title and set Arial font size 9
  currentRow = createEvaluation(worksheet, currentRow, false, {
    name: 'Arial',
    size: 9,
  });

  // Add Facilitators' Report Section - Don't show title and set Arial font size 9
  currentRow = createFacilitatorsReport(worksheet, currentRow, false, {
    name: 'Arial',
    size: 9,
  });

  // Add Time Rules Section
  currentRow = createTimeRules(worksheet, currentRow, true, {
    name: 'Arial',
    size: 9,
  });

  // Add Team/Officer Section after Time Rules
  createTeam(worksheet, currentRow, false, {
    name: 'Arial',
    size: 9,
  });

  // Load the image from public directory
  const tmImage = await getImageAsBase64('/images/toastmasters.png');

  const tmImageId = workbook.addImage({
    base64: tmImage,
    extension: 'png',
  });

  const shImage = await getImageAsBase64('/images/soarhighQR.png');

  const shImageId = workbook.addImage({
    base64: shImage,
    extension: 'png',
  });

  const vpmImage = await getImageAsBase64('/images/vpmQR_hack.png');

  const vpmImageId = workbook.addImage({
    base64: vpmImage,
    extension: 'png',
  });

  worksheet.addImage(tmImageId, {
    tl: { col: 0.2, row: 0.5 },
    ext: { width: 100, height: 100 },
    editAs: 'absolute',
  });

  worksheet.addImage(shImageId, {
    tl: { col: 1.2, row: 0.8 },
    ext: { width: 90, height: 90 },
    editAs: 'absolute',
  });

  worksheet.addImage(vpmImageId, {
    tl: { col: 5, row: 1 },
    ext: { width: 120, height: 80 },
    editAs: 'absolute',
  });

  return { workbook, worksheet };
};
