import { useState, useCallback } from 'react';
import { HighlightMode, MatrixData } from '../utils/matrixTypes';
import { MatrixRoleKey } from '../utils/roleMapping';

export function useMatrixHighlight(matrixData: MatrixData) {
  const [highlight, setHighlight] = useState<HighlightMode>({ type: 'none' });

  const handleCellClick = useCallback(
    (memberId: string, roleKey: MatrixRoleKey) => {
      const meetingIds =
        matrixData.matrix[roleKey]?.[memberId]?.meetingIds || [];
      setHighlight((prev) => {
        // Toggle off if same cell clicked
        if (
          prev.type === 'cell' &&
          prev.memberId === memberId &&
          prev.roleKey === roleKey
        ) {
          return { type: 'none' };
        }
        return { type: 'cell', memberId, roleKey, meetingIds };
      });
    },
    [matrixData]
  );

  const handleColumnClick = useCallback(
    (memberId: string) => {
      const meetingIds = matrixData.memberMeetings[memberId] || [];
      setHighlight((prev) => {
        if (prev.type === 'column' && prev.memberId === memberId) {
          return { type: 'none' };
        }
        return { type: 'column', memberId, meetingIds };
      });
    },
    [matrixData]
  );

  const handleRowClick = useCallback(
    (roleKey: MatrixRoleKey) => {
      const meetingIds = matrixData.roleMeetings[roleKey] || [];
      setHighlight((prev) => {
        if (prev.type === 'row' && prev.roleKey === roleKey) {
          return { type: 'none' };
        }
        return { type: 'row', roleKey, meetingIds };
      });
    },
    [matrixData]
  );

  const clearHighlight = useCallback(() => {
    setHighlight({ type: 'none' });
  }, []);

  // Helper functions to check highlight status
  const isCellHighlighted = useCallback(
    (memberId: string, roleKey: MatrixRoleKey) => {
      if (highlight.type === 'none') return false;
      if (highlight.type === 'cell') {
        return highlight.memberId === memberId && highlight.roleKey === roleKey;
      }
      if (highlight.type === 'column') {
        return highlight.memberId === memberId;
      }
      if (highlight.type === 'row') {
        return highlight.roleKey === roleKey;
      }
      return false;
    },
    [highlight]
  );

  const isMeetingHighlighted = useCallback(
    (meetingId: string) => {
      if (highlight.type === 'none') return false;
      return highlight.meetingIds.includes(meetingId);
    },
    [highlight]
  );

  const isColumnHeaderHighlighted = useCallback(
    (memberId: string) => {
      if (highlight.type === 'column' && highlight.memberId === memberId)
        return true;
      if (highlight.type === 'cell' && highlight.memberId === memberId)
        return true;
      // When a row is selected, highlight member columns that have data for that role
      if (highlight.type === 'row') {
        const count =
          matrixData.matrix[highlight.roleKey]?.[memberId]?.count || 0;
        return count > 0;
      }
      return false;
    },
    [highlight, matrixData]
  );

  const isRowHeaderHighlighted = useCallback(
    (roleKey: MatrixRoleKey) => {
      if (highlight.type === 'row' && highlight.roleKey === roleKey)
        return true;
      if (highlight.type === 'cell' && highlight.roleKey === roleKey)
        return true;
      // When a column is selected, highlight role rows that have data for that member
      if (highlight.type === 'column') {
        const count =
          matrixData.matrix[roleKey]?.[highlight.memberId]?.count || 0;
        return count > 0;
      }
      return false;
    },
    [highlight, matrixData]
  );

  return {
    highlight,
    handleCellClick,
    handleColumnClick,
    handleRowClick,
    clearHighlight,
    isCellHighlighted,
    isMeetingHighlighted,
    isColumnHeaderHighlighted,
    isRowHeaderHighlighted,
  };
}

export type MatrixHighlightState = ReturnType<typeof useMatrixHighlight>;
