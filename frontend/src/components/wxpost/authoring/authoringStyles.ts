export const PANEL_CLASS =
  'min-w-0 overflow-hidden rounded-2xl border border-[#d9e1ec] bg-white shadow-sm max-[480px]:rounded-[14px]';
export const PANEL_HEADER_CLASS =
  'flex min-h-[66px] items-center justify-between gap-[18px] border-b border-[#e4e9f1] px-[22px] py-[18px] max-[480px]:min-h-[60px] max-[480px]:p-4';
export const PANEL_TITLE_CLASS =
  'm-0 text-[19px] font-bold leading-[1.35] tracking-[-0.012em] text-[#172033] max-[480px]:text-lg';
export const FOCUS_RING_CLASS =
  'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-blue-600';
export const PRIMARY_BUTTON_CLASS = `inline-flex min-h-11 items-center justify-center gap-2 rounded-[11px] border border-[#245feb] bg-[#245feb] px-4 py-[10px] text-sm font-bold text-white hover:border-[#184bc7] hover:bg-[#184bc7] ${FOCUS_RING_CLASS} disabled:cursor-not-allowed disabled:border-[#dce3ec] disabled:bg-[#eef2f6] disabled:text-[#96a2b2] [&_svg]:h-[17px] [&_svg]:w-[17px]`;
export const SECONDARY_BUTTON_CLASS = `inline-flex min-h-11 items-center justify-center gap-2 rounded-[11px] border border-[#cfd9e6] bg-white px-4 py-[10px] text-sm font-bold text-[#40506a] hover:border-[#9fb1c8] hover:bg-slate-50 ${FOCUS_RING_CLASS} disabled:cursor-not-allowed disabled:border-[#dce3ec] disabled:bg-[#eef2f6] disabled:text-[#96a2b2] [&_svg]:h-[17px] [&_svg]:w-[17px]`;
export const STAGE_BUTTON_CLASS = `relative flex min-h-[60px] items-center justify-center gap-[9px] border-r border-[#e4e9f1] bg-transparent text-sm font-semibold text-[#68758a] last:border-r-0 ${FOCUS_RING_CLASS} max-[760px]:min-h-[54px] max-[760px]:gap-[5px] max-[760px]:text-xs max-[480px]:min-w-0 max-[480px]:flex-col max-[480px]:gap-[3px] max-[480px]:px-0.5 max-[480px]:py-[7px] max-[480px]:leading-[1.15] [&>span]:grid [&>span]:h-[25px] [&>span]:w-[25px] [&>span]:place-items-center [&>span]:rounded-full [&>span]:bg-[#eef2f7] [&>span]:text-xs max-[760px]:[&>span]:h-[21px] max-[760px]:[&>span]:w-[21px] [&>span>svg]:h-[14px] [&>span>svg]:w-[14px]`;
