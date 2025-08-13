import * as ExcelJS from 'exceljs';
import { AttendeeIF, MeetingIF, SegmentIF } from '@/interfaces';

// Type definitions (based on existing ArraySectionData type)
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
          fgColor: { argb: string };
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

interface ArraySectionData {
  title: string;
  headers: string[];
  columnWidths?: number[];
  rows: Array<CellData[]>;
  verticalMerges?: VerticalMerge[];
}

const defaultColumnWidths = [18, 21, 24, 30, 8, 24];

// Helper function to get the ordinal suffix for a number
function getOrdinalSuffix(n: number): string {
  const s = String(n);
  const last = s.slice(-1);
  const lastTwo = s.slice(-2);

  if (lastTwo === '11' || lastTwo === '12' || lastTwo === '13') {
    return 'th';
  }
  if (last === '1') {
    return 'st';
  }
  if (last === '2') {
    return 'nd';
  }
  if (last === '3') {
    return 'rd';
  }
  return 'th';
}

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
  fontStyle?: { name?: string; size?: number },
  rowHeight?: number
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

    if (rowHeight) {
      dataRow.height = rowHeight;
    }

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
      const headerOffset = showTitle
        ? 1
        : 0 + (data.headers.length > 0 ? 1 : 0);
      const absStartRow = initialStartRow + headerOffset + merge.startRow - 1;
      const absEndRow = initialStartRow + headerOffset + merge.endRow - 1;

      // Perform the vertical merge
      worksheet.mergeCells(absStartRow, merge.col, absEndRow, merge.col);
    });
  }

  return startRow;
};

const formatDate = (dateString: string): string => {
  const date = new Date(dateString);

  // Get month abbreviation
  const months = [
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec',
  ];
  const month = months[date.getMonth()];

  // Get day of month
  const day = date.getDate();

  // Get year
  const year = date.getFullYear();

  // Get day of week abbreviation
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const dayOfWeek = days[date.getDay()];

  // Return formatted date
  return `${month}.${day}, ${year}(${dayOfWeek})`;
};

interface HeaderDataIF {
  theme: string;
  number: number;
  date: string;
  startTime: string;
  endTime: string;
  location: string;
  manager: AttendeeIF;
}

const getHeaderData = (meeting: MeetingIF): HeaderDataIF => {
  return {
    theme: meeting.theme,
    number: meeting.no || 0,
    date: meeting.date,
    startTime: meeting.start_time,
    endTime: meeting.end_time,
    location:
      meeting.location ||
      "Venue: JOININ HUB, 6th Xin'an Rd,Bao'an (Metro line 1 Baoti / line 11 Bao'an)",
    manager: meeting.manager || { name: '', member_id: '' },
  };
};

// Group meeting segments by table section
const getSegmentsWithSection = (meeting: MeetingIF) => {
  // Helper function to check if a segment type matches any keywords
  const matchesAny = (type: string, keywords: string[]): boolean => {
    return keywords.some((keyword) =>
      type.toLowerCase().includes(keyword.toLowerCase())
    );
  };

  // Helper function to calculate minutes difference between two times in hh:mm format
  const getMinutesDifference = (time1: string, time2: string): number => {
    const [hours1, minutes1] = time1.split(':').map(Number);
    const [hours2, minutes2] = time2.split(':').map(Number);

    // Convert both times to minutes
    const totalMinutes1 = hours1 * 60 + minutes1;
    const totalMinutes2 = hours2 * 60 + minutes2;

    return Math.abs(totalMinutes1 - totalMinutes2);
  };

  // Categorize each segment based on type
  const segmentsWithSectionName = meeting.segments.map((segment) => {
    const type = segment.type;
    let sectionName = 'orphan';

    // Opening and Intro section
    if (
      matchesAny(type, [
        'Registration',
        'Warm up',
        'Meeting Rules Introduction',
        'SAA',
        'Opening Remarks',
        'Toastmaster of Meeting',
        'Timer',
        'Ah-Counter',
        'Hark Master',
        'Grammarian',
        'Guests Self Introduction',
      ]) &&
      // segment start time is within 60 minutes of meeting start time
      getMinutesDifference(segment.start_time, meeting.start_time) < 60
    ) {
      sectionName = 'openingAndIntro';
    }
    // Table Topics section
    else if (
      matchesAny(type, ['Table Topic']) &&
      !matchesAny(type, ['Evaluation'])
    ) {
      sectionName = 'tableTopics';
    }
    // Prepared Speeches section
    else if (
      type.includes('Prepared Speech') &&
      !matchesAny(type, ['Evaluation'])
    ) {
      sectionName = 'preparedSpeeches';
    }
    // Workshop section
    else if (type.includes('Workshop')) {
      sectionName = 'workshop';
    }
    // Tea Break section
    else if (type.includes('Tea Break')) {
      sectionName = 'teaBreak';
    }
    // Evaluation section
    else if (
      matchesAny(type, ['Table Topic', 'Prepared Speech']) &&
      matchesAny(type, ['Evaluation'])
    ) {
      sectionName = 'evaluation';
    }
    // Facilitators' Report section
    else if (
      matchesAny(type, [
        'Report',
        'Grammarian',
        'Pop Quiz',
        'General Evaluation',
        'Voting',
        'Moment of Truth',
        'Awards',
        'Closing Remarks',
      ]) &&
      // segment start time is within 60 minutes of meeting end time
      getMinutesDifference(segment.start_time, meeting.end_time) < 45
    ) {
      sectionName = 'facilitatorsReport';
    }

    return { segment, sectionName };
  });

  segmentsWithSectionName.sort((a, b) =>
    a.segment.start_time.localeCompare(b.segment.start_time)
  );

  return segmentsWithSectionName;
};

// Section data converters
const sectionConverters = {
  openingAndIntro: function (segments: SegmentIF[]): ArraySectionData {
    return {
      title: 'Opening and Intro Session',
      headers: ['Time', 'Activities', '>', '>', 'Duration', 'Role Taker'],
      columnWidths: defaultColumnWidths,
      rows: segments.map((segment) => [
        segment.start_time,
        segment.type,
        '>',
        '>',
        Number(segment.duration),
        segment.role_taker?.name || '',
      ]),
    };
  },

  tableTopics: function (segments: SegmentIF[]): ArraySectionData {
    return {
      title: 'Table Topic Session',
      headers: [
        'Time',
        'Table Topic Session',
        '>',
        '>',
        'Duration',
        'Role Taker',
      ],
      columnWidths: defaultColumnWidths,
      rows: segments.map((segment) => {
        if (segment.type.toLowerCase().includes('opening')) {
          return [
            segment.start_time,
            segment.type,
            '>',
            '>',
            Number(segment.duration),
            segment.role_taker?.name || '',
          ];
        } else {
          // Table Topic Session - may have Word of Today in content
          return [
            segment.start_time,
            'Meeting Theme',
            {
              text: 'WOT(Word of Today):',
              style: { alignment: { horizontal: 'right' } },
            },
            segment.content?.split(' ').pop() || '',
            Number(segment.duration),
            segment.role_taker?.name || 'All',
          ];
        }
      }),
    };
  },

  preparedSpeeches: function (segments: SegmentIF[]): ArraySectionData {
    const rows: CellData[][] = [];
    const verticalMerges: VerticalMerge[] = [];

    segments.forEach((segment) => {
      const rowIndex = rows.length + 1;

      // Row 1 - Basic info
      rows.push([
        segment.start_time,
        `${segment.type} ${Math.ceil(rowIndex / 2)}`,
        { text: 'Title', style: { alignment: { horizontal: 'center' } } },
        '>',
        Number(segment.duration),
        segment.role_taker?.name || '',
      ]);

      // Row 2 - Details
      rows.push([
        '', // Time will be merged vertically
        {
          text: segment.content || '',
          style: { alignment: { vertical: 'middle', wrapText: true } },
        },
        {
          text: segment.title || '',
          style: { alignment: { horizontal: 'center' } },
        },
        '>',
        '', // Duration will be merged vertically
        '', // Role Taker will be merged vertically
      ]);

      // Define vertical merges
      verticalMerges.push(
        { col: 1, startRow: rowIndex, endRow: rowIndex + 1 }, // Time column
        { col: 5, startRow: rowIndex, endRow: rowIndex + 1 }, // Duration column
        { col: 6, startRow: rowIndex, endRow: rowIndex + 1 } // Role Taker column
      );
    });

    return {
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
      rows,
      verticalMerges,
    };
  },

  workshop: function (segments: SegmentIF[]): ArraySectionData {
    return {
      title: 'Workshop',
      headers: ['Time', 'Workshop', '>', '>', 'Duration', 'Role Taker'],
      columnWidths: defaultColumnWidths,
      rows: segments.map((segment) => [
        segment.start_time,
        {
          text: segment.title || '',
          style: { alignment: { horizontal: 'center' } },
        },
        '>',
        '>',
        Number(segment.duration),
        segment.role_taker?.name || '',
      ]),
    };
  },

  teaBreak: function (segments: SegmentIF[]): ArraySectionData {
    // Tea break is typically just one segment
    const segment = segments[0] || {
      start_time: '',
      duration: '',
      type: 'Tea Break & Group Photos',
    };

    return {
      title: 'Tea Break',
      headers: [],
      columnWidths: defaultColumnWidths,
      rows: [
        [
          segment.start_time,
          'Tea Break & Group Photos',
          '>',
          '>',
          Number(segment.duration),
          'All',
        ],
      ],
    };
  },

  evaluation: function (segments: SegmentIF[]): ArraySectionData {
    let idxOfPreparedSpeech = 1;
    return {
      title: 'Evaluation Session',
      headers: [
        'Time',
        'Evaluation Session',
        '>',
        '>',
        'Duration',
        'Role Taker',
      ],
      columnWidths: defaultColumnWidths,
      rows: segments.map((segment) => [
        segment.start_time,
        segment.type.includes('Prepared Speech')
          ? `Prepared Speech ${idxOfPreparedSpeech++} Evaluation`
          : segment.type,
        '>',
        '>',
        Number(segment.duration),
        segment.role_taker?.name || '',
      ]),
    };
  },

  facilitatorsReport: function (segments: SegmentIF[]): ArraySectionData {
    return {
      title: "Facilitators' Report",
      headers: [
        'Time',
        "Facilitators' Report",
        '>',
        '>',
        'Duration',
        'Role Taker',
      ],
      columnWidths: defaultColumnWidths,
      rows: segments.map((segment) => [
        segment.start_time,
        segment.type,
        '>',
        '>',
        Number(segment.duration),
        segment.role_taker?.name || '',
      ]),
    };
  },

  orphan: function (segments: SegmentIF[]): ArraySectionData {
    return {
      title: 'Orphan',
      headers: [],
      columnWidths: defaultColumnWidths,
      rows: segments.map((segment) => [
        segment.start_time,
        {
          text: segment.type,
          style: { alignment: { horizontal: 'center' } },
        },
        '>',
        '>',
        Number(segment.duration),
        segment.role_taker?.name || '',
      ]),
    };
  },
};

// Function to create a table header
const createTableHeader = (
  worksheet: ExcelJS.Worksheet,
  startRow: number,
  showTitle: boolean = true,
  fontStyle: { name?: string; size?: number } = {},
  headerData: HeaderDataIF
): number => {
  // Create a standard section for the header
  const headerSection: ArraySectionData = {
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
          text: `${headerData.number}${getOrdinalSuffix(headerData.number)} Meeting`,
          style: {
            font: { size: 12, color: { argb: 'FFFFFFFF' } },
          },
        },
        {
          text: headerData.theme,
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
          text: formatDate(headerData.date),
          style: {
            font: { color: { argb: 'FFFFFFFF' } },
          },
        },
        {
          text: `Time: ${headerData.startTime.slice(0, 5)}-${headerData.endTime.slice(0, 5)}`,
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
          text: headerData.location,
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
          text: `Meeting Manager: ${headerData.manager.name}`,
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
    headerSection,
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

// Function to create time rules section
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
    fontStyle,
    13
  );

  worksheet.getRow(startRow - 4).height = 28;
  worksheet.getRow(startRow - 1).height = 28;

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
        { text: 'Rui Zheng', style: { alignment: { horizontal: 'center' } } },
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
          // text: "Soarhigh Toastmasters Club is the one and only 100% English Club in Bao'an. We are a family to love, to care, to laugh, and to inspire. \n\n搜嗨头马国际演讲俱乐部，深圳宝安区唯一的100%英文俱乐部，主打松弛感第一，包容度第一，以自己的节奏，享受每一步的成长。\n\nOur slogan: Soarhigh, so high, takes me fly! \n\nAbout the Membership Fee: 6months - ¥906; 12months - ¥1515; (Includes registration on the Toastmasters International Website $20, venue fees, refreshments, and other membership activity costs.)",
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
        { text: 'Max Long', style: { alignment: { horizontal: 'center' } } },
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
          text: 'Jessica Peng',
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
          text: 'Homer',
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
          text: 'Leta Li',
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
        { text: 'Jenny', style: { alignment: { horizontal: 'center' } } },
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
          text: 'Frank Zeng',
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
          text: 'Libra Lee',
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

  [3, 4, 8].forEach((row) => {
    worksheet.getRow(startRow - row).height = 16;
  });

  [1, 2, 5, 6, 7].forEach((row) => {
    worksheet.getRow(startRow - row).height = 34;
  });

  worksheet.mergeCells(startRow - 8, 5, startRow - 1, 6);

  return startRow;
};

// Main function to create a meeting workbook
export const createMeetingWorkbook = async (
  meeting: MeetingIF,
  fontStyle = { name: 'Arial', size: 9 }
) => {
  // Create workbook and worksheet
  const workbook = new ExcelJS.Workbook();
  const worksheet = workbook.addWorksheet('Meeting Agenda');

  // Set default column widths
  worksheet.columns = defaultColumnWidths.map((width) => ({ width }));

  // Group segments by section
  const segmentsWithSectionName = getSegmentsWithSection(meeting);

  // Start adding sections - we're starting with row 1
  let currentRow = 1;

  // Add Table Header with meeting metadata
  currentRow = createTableHeader(
    worksheet,
    currentRow,
    false,
    fontStyle,
    getHeaderData(meeting)
  );

  // Add segments grouped by section
  let nSpeeches = 0;
  let nSpeechEvaluations = 0;
  let prevSectionName = '';
  for (const segmentWithSectionName of segmentsWithSectionName) {
    const sectionName = segmentWithSectionName.sectionName;
    const segment = segmentWithSectionName.segment;

    const sectionData = sectionConverters[
      sectionName as keyof typeof sectionConverters
    ]([segment]);

    if (sectionName === 'tableTopics' && !segment.type.includes('Opening')) {
      sectionData.rows[0][1] = meeting.theme;
    }

    if (sectionName === 'preparedSpeeches') {
      nSpeeches++;
      sectionData.rows[0][1] = `Prepared Speech ${nSpeeches}`;
    }

    if (
      sectionName === 'evaluation' &&
      segment.type.includes('Prepared Speech')
    ) {
      nSpeechEvaluations++;
      sectionData.rows[0][1] = `Prepared Speech ${nSpeechEvaluations} Evaluation`;
    }

    currentRow = createArraySection(
      worksheet,
      sectionName !== prevSectionName
        ? sectionData
        : { ...sectionData, headers: [] },
      currentRow,
      false,
      fontStyle,
      13
    );

    if (sectionName === 'preparedSpeeches') {
      worksheet.getRow(currentRow - 1).height = 60;
    }

    prevSectionName = sectionName;
  }

  // Add Time Rules Section (static content)
  currentRow = createTimeRules(worksheet, currentRow, true, fontStyle);

  // Add Team/Officer Section (static content)
  createTeam(worksheet, currentRow, false, fontStyle);

  // Add header section images
  try {
    // Load the images from public directory
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

    // Position the images
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
  } catch (error) {
    console.error('Error loading images:', error);
    // Continue without images if there's an error
  }

  return { workbook, worksheet };
};
