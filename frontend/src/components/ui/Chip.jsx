import React from "react";

export function Chip({ children, bg, fg }) {
  return (
    <span style={{fontFamily:'var(--font-mono)',fontSize:11,fontWeight:500,letterSpacing:'.06em',
      padding:'3px 10px',borderRadius:999,background:bg,color:fg,
      display:'inline-flex',alignItems:'center',gap:6,whiteSpace:'nowrap'}}>
      {children}
    </span>
  );
}

export function StatusChip({ status }) {
  const map = {
    running:    {bg:'rgba(79,143,90,.1)', fg:'#35683F',   label:'RUNNING'},
    awaiting_approval:{bg:'rgba(217,119,87,.14)',fg:'#BC5A3B',label:'AWAITING APPROVAL'},
    approved:   {bg:'rgba(79,143,90,.14)',fg:'#35683F',   label:'APPROVED'},
    edited:     {bg:'rgba(196,154,43,.12)',fg:'#8F6F1A',  label:'EDITED'},
    rejected:   {bg:'rgba(209,67,67,.10)',fg:'#D14343',   label:'REJECTED'},
    error:      {bg:'rgba(209,67,67,.10)',fg:'#D14343',   label:'ERROR'},
  };
  const s = map[status] || {bg:'var(--grey-100)',fg:'var(--fg-3)',label:status};
  return <Chip bg={s.bg} fg={s.fg}>{s.label}</Chip>;
}
