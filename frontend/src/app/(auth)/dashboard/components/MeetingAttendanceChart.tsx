'use client';

import { useMemo, useRef } from 'react';
import ReactECharts from 'echarts-for-react';
import { ZoomControls } from './ZoomControls';
import { useChartZoom } from '../hooks/useChartZoom';
import { MeetingAttendanceChartData } from '../utils/types';

interface MeetingAttendanceChartProps {
  data: MeetingAttendanceChartData[];
}

export function MeetingAttendanceChart({ data }: MeetingAttendanceChartProps) {
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
        formatter: (
          params: { seriesName: string; value: number; dataIndex: number }[]
        ) => {
          const idx = params[0].dataIndex;
          const d = data[idx];
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
          start: zoom.zoom.start,
          end: zoom.zoom.end,
          zoomLock: true,
          filterMode: 'none',
        },
      ],
      xAxis: {
        type: 'category',
        data: data.map((d) => d.label),
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
          data: data.map((d) => d.memberCount),
          itemStyle: {
            color: '#3b82f6',
          },
        },
        {
          name: 'Guests',
          type: 'bar',
          stack: 'total',
          data: data.map((d) => d.guestCount),
          itemStyle: {
            color: '#22c55e',
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
