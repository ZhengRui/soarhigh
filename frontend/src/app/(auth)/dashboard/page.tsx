'use client';

import React, { useState, useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { useDashboardStats } from '@/hooks/useDashboard';
import { MemberMeetingRecordIF, MeetingAttendanceRecordIF } from '@/interfaces';

// Helper to format date to YYYY-MM-DD (local timezone)
const formatDate = (date: Date): string => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

// Get default date range (past 3 months)
const getDefaultDateRange = () => {
  const endDate = new Date();
  const startDate = new Date();
  startDate.setMonth(startDate.getMonth() - 3);
  return {
    startDate: formatDate(startDate),
    endDate: formatDate(endDate),
  };
};

// Aggregated data for Chart 1
interface MemberAttendanceData {
  name: string;
  fullName: string;
  meetingCount: number;
  meetings: { theme: string; date: string; roles: string[] }[];
}

// Chart 2 data structure
interface MeetingAttendanceChartData {
  label: string;
  date: string;
  theme: string;
  memberCount: number;
  guestCount: number;
  memberNames: string[];
  guestNames: string[];
}

// Zoom state: start and end percentages (0-100)
interface ZoomState {
  start: number;
  end: number;
}

const getZoomWindow = (state: ZoomState) => state.end - state.start;

const zoomIn = (state: ZoomState): ZoomState => {
  const window = getZoomWindow(state);
  if (window <= 20) return state; // Already at min zoom

  const center = (state.start + state.end) / 2;
  const newWindow = Math.max(20, window - 20);
  let newStart = center - newWindow / 2;
  let newEnd = center + newWindow / 2;

  // Clamp to bounds
  if (newStart < 0) {
    newEnd -= newStart;
    newStart = 0;
  }
  if (newEnd > 100) {
    newStart -= newEnd - 100;
    newEnd = 100;
  }

  return { start: Math.max(0, newStart), end: Math.min(100, newEnd) };
};

const zoomOut = (state: ZoomState): ZoomState => {
  const window = getZoomWindow(state);
  if (window >= 100) return state; // Already at max zoom out

  const center = (state.start + state.end) / 2;
  const newWindow = Math.min(100, window + 20);
  let newStart = center - newWindow / 2;
  let newEnd = center + newWindow / 2;

  // Clamp to bounds
  if (newStart < 0) {
    newEnd -= newStart;
    newStart = 0;
  }
  if (newEnd > 100) {
    newStart -= newEnd - 100;
    newEnd = 100;
  }

  return { start: Math.max(0, newStart), end: Math.min(100, newEnd) };
};

// Zoom controls component
const ZoomControls = ({
  zoomState,
  onZoomIn,
  onZoomOut,
}: {
  zoomState: ZoomState;
  onZoomIn: () => void;
  onZoomOut: () => void;
}) => {
  const window = getZoomWindow(zoomState);
  const canZoomOut = window < 100;
  const canZoomIn = window > 20;

  return (
    <div className='absolute top-0 right-[4%] flex items-center gap-1 z-10'>
      <span className='text-xs text-gray-500 mr-1'>{Math.round(window)}%</span>
      <button
        onClick={onZoomOut}
        disabled={!canZoomOut}
        className={`w-7 h-7 border rounded shadow-sm flex items-center justify-center text-base font-medium ${
          canZoomOut
            ? 'bg-white border-gray-300 text-gray-600 hover:bg-gray-50 active:bg-gray-100'
            : 'bg-gray-100 border-gray-200 text-gray-300 cursor-not-allowed'
        }`}
      >
        −
      </button>
      <button
        onClick={onZoomIn}
        disabled={!canZoomIn}
        className={`w-7 h-7 border rounded shadow-sm flex items-center justify-center text-base font-medium ${
          canZoomIn
            ? 'bg-white border-gray-300 text-gray-600 hover:bg-gray-50 active:bg-gray-100'
            : 'bg-gray-100 border-gray-200 text-gray-300 cursor-not-allowed'
        }`}
      >
        +
      </button>
    </div>
  );
};

export default function DashboardPage() {
  const defaultRange = getDefaultDateRange();
  const [startDate, setStartDate] = useState(defaultRange.startDate);
  const [endDate, setEndDate] = useState(defaultRange.endDate);

  // Zoom state for charts (start and end percentages)
  const [chart1Zoom, setChart1Zoom] = useState<ZoomState>({
    start: 0,
    end: 100,
  });
  const [chart2Zoom, setChart2Zoom] = useState<ZoomState>({
    start: 0,
    end: 100,
  });

  const { data, isPending, error } = useDashboardStats({ startDate, endDate });

  // Process data for Chart 1: Member Attendance
  const memberAttendanceData = useMemo<MemberAttendanceData[]>(() => {
    if (!data?.member_meetings) return [];

    // Group by member
    const memberMap = new Map<
      string,
      {
        fullName: string;
        meetings: Map<string, { theme: string; date: string; roles: string[] }>;
      }
    >();

    data.member_meetings.forEach((record: MemberMeetingRecordIF) => {
      if (!memberMap.has(record.member_id)) {
        memberMap.set(record.member_id, {
          fullName: record.full_name,
          meetings: new Map(),
        });
      }

      const memberData = memberMap.get(record.member_id)!;
      if (!memberData.meetings.has(record.meeting_id)) {
        memberData.meetings.set(record.meeting_id, {
          theme: record.meeting_theme,
          date: record.meeting_date,
          roles: [],
        });
      }
      memberData.meetings.get(record.meeting_id)!.roles.push(record.role);
    });

    // Convert to array and sort by meeting count
    const result: MemberAttendanceData[] = [];
    memberMap.forEach((value) => {
      const meetings = Array.from(value.meetings.values()).sort(
        (a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()
      );
      result.push({
        name: value.fullName.split(' ')[0], // First name for chart label
        fullName: value.fullName,
        meetingCount: meetings.length,
        meetings,
      });
    });

    return result.sort((a, b) => b.meetingCount - a.meetingCount);
  }, [data?.member_meetings]);

  // Process data for Chart 2: Meeting Attendance
  const meetingAttendanceData = useMemo<MeetingAttendanceChartData[]>(() => {
    if (!data?.meeting_attendance) return [];

    return data.meeting_attendance.map((record: MeetingAttendanceRecordIF) => ({
      label:
        record.meeting_theme.length > 10
          ? record.meeting_theme.slice(0, 10) + '...'
          : record.meeting_theme,
      date: record.meeting_date,
      theme: record.meeting_theme,
      memberCount: record.member_count,
      guestCount: record.guest_count,
      memberNames: record.member_names,
      guestNames: record.guest_names,
    }));
  }, [data?.meeting_attendance]);

  // ECharts option for Chart 1: Member Attendance
  const chart1Option = useMemo(() => {
    if (memberAttendanceData.length === 0) return null;

    return {
      tooltip: {
        trigger: 'axis',
        triggerOn: 'click',
        axisPointer: { type: 'shadow' },
        enterable: true,
        confine: true,
        formatter: (params: { dataIndex: number }[]) => {
          const d = memberAttendanceData[params[0].dataIndex];
          const meetingsList = d.meetings
            .map(
              (m) =>
                `<div style="margin-bottom:4px;"><span style="font-weight:500;">${m.date}</span>: ${m.theme}<br/><span style="color:#8b5cf6;">${m.roles.join(', ')}</span></div>`
            )
            .join('');
          return `
            <div style="max-width:280px;word-wrap:break-word;white-space:normal;">
              <div style="font-weight:600;margin-bottom:4px;">${d.fullName}</div>
              <div style="color:#666;margin-bottom:8px;">${d.meetingCount} meeting${d.meetingCount !== 1 ? 's' : ''}</div>
              <div style="max-height:180px;overflow-y:auto;font-size:12px;">${meetingsList}</div>
            </div>
          `;
        },
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '15%',
        containLabel: true,
      },
      dataZoom: [
        {
          type: 'inside',
          xAxisIndex: 0,
          start: chart1Zoom.start,
          end: chart1Zoom.end,
          zoomLock: true,
          filterMode: 'none',
        },
      ],
      xAxis: {
        type: 'category',
        data: memberAttendanceData.map((d) => d.name),
        axisLabel: {
          rotate: 45,
          fontSize: 12,
        },
      },
      yAxis: {
        type: 'value',
        minInterval: 1,
      },
      series: [
        {
          type: 'bar',
          data: memberAttendanceData.map((d) => d.meetingCount),
          itemStyle: {
            color: '#8b5cf6',
            borderRadius: [4, 4, 0, 0],
          },
        },
      ],
    };
  }, [memberAttendanceData, chart1Zoom]);

  // ECharts option for Chart 2: Meeting Attendance
  const chart2Option = useMemo(() => {
    if (meetingAttendanceData.length === 0) return null;

    return {
      tooltip: {
        trigger: 'axis',
        triggerOn: 'click',
        axisPointer: { type: 'shadow' },
        enterable: true,
        confine: true,
        formatter: (
          params: { seriesName: string; value: number; dataIndex: number }[]
        ) => {
          const idx = params[0].dataIndex;
          const d = meetingAttendanceData[idx];
          return `
            <div style="max-width:280px;word-wrap:break-word;white-space:normal;">
              <div style="font-weight:600;margin-bottom:4px;">${d.theme}</div>
              <div style="color:#666;font-size:12px;margin-bottom:8px;">${d.date}</div>
              <div style="margin-bottom:8px;">
                <div style="font-weight:500;color:#3b82f6;">Members (${d.memberCount}):</div>
                <div style="font-size:12px;color:#666;max-height:80px;overflow-y:auto;">${d.memberNames.join(', ') || 'None'}</div>
              </div>
              <div>
                <div style="font-weight:500;color:#22c55e;">Guests (${d.guestCount}):</div>
                <div style="font-size:12px;color:#666;max-height:80px;overflow-y:auto;">${d.guestNames.join(', ') || 'None'}</div>
              </div>
            </div>
          `;
        },
      },
      legend: {
        data: ['Members', 'Guests'],
        top: 0,
        left: 'center',
      },
      media: [
        {
          query: { maxWidth: 640 },
          option: {
            legend: { left: 0 },
          },
        },
      ],
      grid: {
        left: '3%',
        right: '4%',
        top: '10%',
        bottom: '15%',
        containLabel: true,
      },
      dataZoom: [
        {
          type: 'inside',
          xAxisIndex: 0,
          start: chart2Zoom.start,
          end: chart2Zoom.end,
          zoomLock: true,
          filterMode: 'none',
        },
      ],
      xAxis: {
        type: 'category',
        data: meetingAttendanceData.map((d) => d.label),
        axisLabel: {
          rotate: 45,
          fontSize: 12,
        },
      },
      yAxis: {
        type: 'value',
        minInterval: 1,
      },
      series: [
        {
          name: 'Members',
          type: 'bar',
          stack: 'total',
          data: meetingAttendanceData.map((d) => d.memberCount),
          itemStyle: {
            color: '#3b82f6',
          },
        },
        {
          name: 'Guests',
          type: 'bar',
          stack: 'total',
          data: meetingAttendanceData.map((d) => d.guestCount),
          itemStyle: {
            color: '#22c55e',
            borderRadius: [4, 4, 0, 0],
          },
        },
      ],
    };
  }, [meetingAttendanceData, chart2Zoom]);

  // Zoom handlers
  const handleChart1ZoomIn = () => setChart1Zoom((prev) => zoomIn(prev));
  const handleChart1ZoomOut = () => setChart1Zoom((prev) => zoomOut(prev));
  const handleChart2ZoomIn = () => setChart2Zoom((prev) => zoomIn(prev));
  const handleChart2ZoomOut = () => setChart2Zoom((prev) => zoomOut(prev));

  return (
    <div className='min-h-screen bg-gray-50 py-12 px-4 sm:px-6 lg:px-8'>
      <div className='max-w-7xl mx-auto'>
        <div className='text-center mb-8'>
          <h1 className='text-3xl font-bold text-gray-900'>Dashboard</h1>
          <p className='mt-2 text-gray-600'>
            Meeting statistics and member participation insights
          </p>
        </div>

        {/* Date Range Picker */}
        <div className='bg-white p-4 rounded-lg shadow-sm mb-8'>
          <div className='flex flex-wrap items-center gap-4'>
            <label className='text-sm font-medium text-gray-700'>
              Date Range:
            </label>
            <div className='flex items-center gap-2'>
              <input
                type='date'
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className='px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-purple-500'
              />
              <span className='text-gray-500'>to</span>
              <input
                type='date'
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className='px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-purple-500'
              />
            </div>
          </div>
        </div>

        {isPending && (
          <div className='flex flex-col items-center justify-center py-24'>
            <div className='animate-spin rounded-full h-8 w-8 border-b-2 border-purple-600'></div>
            <p className='mt-2 text-gray-600'>Loading statistics...</p>
          </div>
        )}

        {error && (
          <div className='bg-red-50 border border-red-200 rounded-lg p-4 mb-8'>
            <p className='text-red-600'>
              Failed to load dashboard data. Please try again.
            </p>
          </div>
        )}

        {data && (
          <div className='space-y-8'>
            {/* Chart 1: Member Attendance */}
            <div className='bg-white p-6 rounded-lg shadow-sm'>
              <h2 className='text-xl font-semibold mb-4 text-gray-900'>
                Member Attendance
              </h2>
              <p className='text-sm text-gray-600 mb-4'>
                Number of meetings attended by each member (tap bar for details,
                drag to pan)
              </p>
              {chart1Option ? (
                <div className='relative'>
                  <ZoomControls
                    zoomState={chart1Zoom}
                    onZoomIn={handleChart1ZoomIn}
                    onZoomOut={handleChart1ZoomOut}
                  />
                  <ReactECharts
                    option={chart1Option}
                    style={{ height: '320px' }}
                    notMerge={true}
                  />
                </div>
              ) : (
                <p className='text-gray-500 text-center py-8'>
                  No data available for the selected date range.
                </p>
              )}
            </div>

            {/* Chart 2: Meeting Attendance */}
            <div className='bg-white p-6 rounded-lg shadow-sm'>
              <h2 className='text-xl font-semibold mb-4 text-gray-900'>
                Attendance per Meeting
              </h2>
              <p className='text-sm text-gray-600 mb-4'>
                Number of members and guests per meeting (tap bar for names,
                drag to pan)
              </p>
              {chart2Option ? (
                <div className='relative'>
                  <ZoomControls
                    zoomState={chart2Zoom}
                    onZoomIn={handleChart2ZoomIn}
                    onZoomOut={handleChart2ZoomOut}
                  />
                  <ReactECharts
                    option={chart2Option}
                    style={{ height: '320px' }}
                    notMerge={true}
                  />
                </div>
              ) : (
                <p className='text-gray-500 text-center py-8'>
                  No data available for the selected date range.
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
