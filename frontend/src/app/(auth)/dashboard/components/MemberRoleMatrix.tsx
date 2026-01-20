'use client';

import { useMemo, useRef } from 'react';
import { MemberMeetingRecordIF } from '@/interfaces';
import {
  MATRIX_ROLES,
  MatrixRoleKey,
  normalizeRoleToMatrixKey,
} from '../utils/roleMapping';
import {
  MatrixData,
  MemberInfo,
  MeetingInfo,
  MatrixCellData,
} from '../utils/matrixTypes';
import { getHeatmapColor, getHeatmapTextColor } from '../utils/heatmapColors';
import { useMatrixHighlight } from '../hooks/useMatrixHighlight';
import { MeetingPillsList } from './MeetingPillsList';

interface MemberRoleMatrixProps {
  memberMeetings: MemberMeetingRecordIF[];
}

// Header height constant
const HEADER_HEIGHT = 70; // px

export function MemberRoleMatrix({ memberMeetings }: MemberRoleMatrixProps) {
  const roleColumnRef = useRef<HTMLDivElement>(null);
  const dataContainerRef = useRef<HTMLDivElement>(null);

  // Sync vertical scroll between role column and data table
  const handleDataScroll = () => {
    if (roleColumnRef.current && dataContainerRef.current) {
      roleColumnRef.current.scrollTop = dataContainerRef.current.scrollTop;
    }
  };

  // Process data into matrix format
  const matrixData = useMemo<MatrixData>(() => {
    if (!memberMeetings || memberMeetings.length === 0) {
      const emptyMatrix = {} as Record<
        MatrixRoleKey,
        Record<string, MatrixCellData>
      >;
      const emptyRoleMeetings = {} as Record<MatrixRoleKey, string[]>;
      MATRIX_ROLES.forEach((role) => {
        emptyMatrix[role.key] = {};
        emptyRoleMeetings[role.key] = [];
      });
      return {
        members: [],
        meetings: [],
        matrix: emptyMatrix,
        memberMeetings: {},
        roleMeetings: emptyRoleMeetings,
      };
    }

    const membersMap = new Map<string, MemberInfo>();
    const meetingsMap = new Map<string, MeetingInfo>();
    const matrix: Record<string, Record<string, MatrixCellData>> = {};
    const memberMeetingsLookup: Record<string, Set<string>> = {};
    const roleMeetingsLookup: Record<string, Set<string>> = {};

    // Initialize matrix structure
    MATRIX_ROLES.forEach((role) => {
      matrix[role.key] = {};
      roleMeetingsLookup[role.key] = new Set();
    });

    // Process each record
    memberMeetings.forEach((record) => {
      // Track member
      if (!membersMap.has(record.member_id)) {
        membersMap.set(record.member_id, {
          memberId: record.member_id,
          fullName: record.full_name,
          shortName: record.full_name.split(' ')[0],
        });
        memberMeetingsLookup[record.member_id] = new Set();
      }

      // Track meeting
      if (!meetingsMap.has(record.meeting_id)) {
        meetingsMap.set(record.meeting_id, {
          meetingId: record.meeting_id,
          date: record.meeting_date,
          theme: record.meeting_theme,
          meetingNo: record.meeting_no,
        });
      }

      // Normalize role and update matrix
      const roleKey = normalizeRoleToMatrixKey(record.role);
      if (roleKey) {
        if (!matrix[roleKey][record.member_id]) {
          matrix[roleKey][record.member_id] = { count: 0, meetingIds: [] };
        }
        matrix[roleKey][record.member_id].count++;
        matrix[roleKey][record.member_id].meetingIds.push(record.meeting_id);

        memberMeetingsLookup[record.member_id].add(record.meeting_id);
        roleMeetingsLookup[roleKey].add(record.meeting_id);
      }
    });

    // Sort members by total role count (most active first)
    const members = Array.from(membersMap.values()).sort((a, b) => {
      const countA = Object.values(matrix).reduce(
        (sum, roleData) => sum + (roleData[a.memberId]?.count || 0),
        0
      );
      const countB = Object.values(matrix).reduce(
        (sum, roleData) => sum + (roleData[b.memberId]?.count || 0),
        0
      );
      return countB - countA;
    });

    // Sort meetings by date (newest first)
    const meetings = Array.from(meetingsMap.values()).sort(
      (a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()
    );

    return {
      members,
      meetings,
      matrix: matrix as Record<MatrixRoleKey, Record<string, MatrixCellData>>,
      memberMeetings: Object.fromEntries(
        Object.entries(memberMeetingsLookup).map(([k, v]) => [k, Array.from(v)])
      ),
      roleMeetings: Object.fromEntries(
        Object.entries(roleMeetingsLookup).map(([k, v]) => [k, Array.from(v)])
      ) as Record<MatrixRoleKey, string[]>,
    };
  }, [memberMeetings]);

  const highlightState = useMatrixHighlight(matrixData);
  const hasHighlight = highlightState.highlight.type !== 'none';

  if (matrixData.members.length === 0) {
    return (
      <div className='bg-white p-6 rounded-lg shadow-sm'>
        <h2 className='text-xl font-semibold mb-4 text-gray-900'>
          Member-Role Matrix
        </h2>
        <p className='text-gray-500 text-center py-8'>
          No data available for the selected date range.
        </p>
      </div>
    );
  }

  return (
    <div className='bg-white p-6 rounded-lg shadow-sm'>
      <h2 className='text-xl font-semibold mb-4 text-gray-900'>
        Member-Role Matrix
      </h2>
      <p className='text-sm text-gray-600 mb-4'>
        Click on cells, rows, or columns to highlight related meetings
      </p>

      {/* Meeting Pills */}
      <MeetingPillsList
        meetings={matrixData.meetings}
        highlightState={highlightState}
      />

      {/* Matrix Container - Flex layout */}
      <div className='mt-4 flex border rounded-lg overflow-hidden'>
        {/* Role Column - horizontally scrollable */}
        <div className='flex-shrink-0 border-r-2 border-gray-200 bg-white w-[90px] sm:w-[160px]'>
          {/* Role column header (empty corner) */}
          <div
            className='border-b-2 border-gray-200 bg-white'
            style={{ height: HEADER_HEIGHT }}
          />
          {/* Role labels container - horizontally scrollable */}
          <div
            ref={roleColumnRef}
            className='overflow-x-auto overflow-y-hidden scrollbar-none w-[90px] sm:w-[160px]'
            style={{ maxHeight: `calc(500px - ${HEADER_HEIGHT}px)` }}
          >
            <div className='whitespace-nowrap'>
              {MATRIX_ROLES.map((role) => {
                const isRowHighlighted = highlightState.isRowHeaderHighlighted(
                  role.key
                );
                const isRowDimmed = hasHighlight && !isRowHighlighted;

                return (
                  <div
                    key={role.key}
                    className={`px-1 text-[10px] sm:text-xs cursor-pointer hover:bg-gray-100 transition-colors flex items-center h-7 sm:h-9 ${
                      isRowHighlighted
                        ? 'bg-purple-100 font-semibold'
                        : isRowDimmed
                          ? 'bg-white text-gray-300'
                          : 'bg-white font-medium'
                    }`}
                    onClick={() => highlightState.handleRowClick(role.key)}
                    title={role.label}
                  >
                    {role.label}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Data Table Container - scrollable both ways */}
        <div
          ref={dataContainerRef}
          className='flex-1 overflow-auto'
          style={{ maxHeight: 500 }}
          onScroll={handleDataScroll}
        >
          <table className='border-collapse w-full'>
            <thead>
              <tr>
                {/* Member column headers */}
                {matrixData.members.map((member) => {
                  const isHighlighted =
                    highlightState.isColumnHeaderHighlighted(member.memberId);
                  const isDimmed = hasHighlight && !isHighlighted;

                  return (
                    <th
                      key={member.memberId}
                      className={`sticky top-0 z-20 border-b-2 border-gray-200 px-1 py-1 sm:py-2 text-[10px] sm:text-xs cursor-pointer hover:bg-gray-100 transition-colors ${
                        isHighlighted
                          ? 'bg-purple-100 font-semibold'
                          : isDimmed
                            ? 'bg-white text-gray-300'
                            : 'bg-white font-medium'
                      }`}
                      onClick={() =>
                        highlightState.handleColumnClick(member.memberId)
                      }
                      title={member.fullName}
                      style={{
                        writingMode: 'vertical-rl',
                        textOrientation: 'mixed',
                        transform: 'rotate(180deg)',
                        height: HEADER_HEIGHT,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {member.shortName}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {MATRIX_ROLES.map((role) => (
                <tr key={role.key} className='h-7 sm:h-9'>
                  {/* Data cells */}
                  {matrixData.members.map((member) => {
                    const cellData =
                      matrixData.matrix[role.key]?.[member.memberId];
                    const count = cellData?.count || 0;
                    const isCellHighlighted = highlightState.isCellHighlighted(
                      member.memberId,
                      role.key
                    );
                    // Only highlight cells with actual values (count > 0)
                    const shouldHighlight = isCellHighlighted && count > 0;
                    const isCellDimmed = hasHighlight && !shouldHighlight;

                    return (
                      <td
                        key={member.memberId}
                        className={`px-1 sm:px-2 text-center text-[10px] sm:text-xs cursor-pointer transition-all duration-150 min-w-[32px] sm:min-w-[40px] border border-gray-100 ${getHeatmapColor(count)} ${getHeatmapTextColor(count)} ${shouldHighlight ? 'ring-1 ring-purple-500 ring-inset' : ''} ${isCellDimmed ? 'opacity-40' : ''}`}
                        onClick={() =>
                          highlightState.handleCellClick(
                            member.memberId,
                            role.key
                          )
                        }
                        title={`${member.fullName}: ${role.label} (${count})`}
                      >
                        {count > 0 ? count : '-'}
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
}
