'use client';

import { useMemo, useRef } from 'react';
import ReactECharts from 'echarts-for-react';
import { ZoomControls } from './ZoomControls';
import { useChartZoom } from '../hooks/useChartZoom';
import { MemberAttendanceData } from '../utils/types';

interface MemberAttendanceChartProps {
  data: MemberAttendanceData[];
}

export function MemberAttendanceChart({ data }: MemberAttendanceChartProps) {
  const chartRef = useRef<ReactECharts>(null);
  const zoom = useChartZoom();

  // Sync from chart instance before zooming
  const syncFromChart = () => {
    const instance = chartRef.current?.getEchartsInstance();
    if (instance) {
      const option = instance.getOption();
      const dataZoom = option.dataZoom as
        | { start?: number; end?: number }[]
        | undefined;
      if (dataZoom?.[0]) {
        const { start, end } = dataZoom[0];
        if (start !== undefined && end !== undefined) {
          zoom.syncZoom(start, end);
        }
      }
    }
  };

  const handleZoomIn = () => {
    syncFromChart();
    zoom.handleZoomIn();
  };

  const handleZoomOut = () => {
    syncFromChart();
    zoom.handleZoomOut();
  };

  const option = useMemo(() => {
    if (data.length === 0) return null;

    return {
      tooltip: {
        trigger: 'axis',
        triggerOn: 'click',
        axisPointer: { type: 'shadow' },
        enterable: true,
        confine: true,
        formatter: (params: { dataIndex: number }[]) => {
          const d = data[params[0].dataIndex];
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
          start: zoom.zoom.start,
          end: zoom.zoom.end,
          zoomLock: true,
          filterMode: 'none',
        },
      ],
      xAxis: {
        type: 'category',
        data: data.map((d) => d.name),
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
          data: data.map((d) => d.meetingCount),
          itemStyle: {
            color: '#8b5cf6',
            borderRadius: [4, 4, 0, 0],
          },
        },
      ],
    };
  }, [data, zoom.zoom]);

  if (!option) {
    return (
      <p className='text-gray-500 text-center py-8'>
        No data available for the selected date range.
      </p>
    );
  }

  return (
    <div className='relative'>
      <ZoomControls
        window={zoom.window}
        canZoomIn={zoom.canZoomIn}
        canZoomOut={zoom.canZoomOut}
        onZoomIn={handleZoomIn}
        onZoomOut={handleZoomOut}
      />
      <ReactECharts
        ref={chartRef}
        option={option}
        style={{ height: '320px' }}
        notMerge={true}
      />
    </div>
  );
}
