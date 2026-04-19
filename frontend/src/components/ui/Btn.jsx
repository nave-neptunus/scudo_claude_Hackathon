import React from "react";

export function Btn({ children, onClick, variant='primary', disabled=false, small=false, style={} }) {
  const base = {
    fontFamily:'var(--font-sans)',fontWeight:500,border:'none',cursor:disabled?'not-allowed':'pointer',
    borderRadius:'var(--radius-2)',transition:'all var(--motion-fast)',
    fontSize: small ? 12 : 14, padding: small ? '6px 12px' : '11px 18px',
    ...style,
  };
  const variants = {
    primary:{ background:disabled?'rgba(20,21,25,.08)':'var(--accent)', color:disabled?'var(--fg-3)':'#fff',
      boxShadow:disabled?'none':'0 1px 0 rgba(255,255,255,.3) inset,0 6px 20px -8px rgba(217,119,87,.5)'},
    danger:{ background:'transparent',color:'var(--status-danger)',
      border:'1px solid rgba(209,67,67,.4)'},
    ghost:{ background:'rgba(255,255,255,.6)',color:'var(--fg-2)',
      border:'1px solid var(--glass-border-lo)'},
  };
  return <button onClick={onClick} disabled={disabled} style={{...base,...variants[variant]}}>{children}</button>;
}
