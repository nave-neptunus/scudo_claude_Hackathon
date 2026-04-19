import React from "react";

export function Glass({ children, style, thick, dark, padding = 24 }) {
  return (
    <div style={{
      position:'relative',
      background: dark ? 'rgba(20,21,25,.86)' : thick ? 'var(--glass-thick-bg)' : 'var(--glass-bg)',
      backdropFilter: thick ? 'blur(28px) saturate(160%)' : 'blur(18px) saturate(140%)',
      WebkitBackdropFilter: thick ? 'blur(28px) saturate(160%)' : 'blur(18px) saturate(140%)',
      border: dark ? '1px solid rgba(255,255,255,.08)' : '1px solid var(--glass-border-lo)',
      borderRadius:'var(--radius-3)',
      boxShadow: thick ? 'var(--shadow-glass-2)' : 'var(--shadow-glass-1)',
      padding, overflow:'hidden',
      color: dark ? 'var(--fg-on-dark)' : 'var(--fg-1)',
      ...style,
    }}>
      {!dark && <div style={{position:'absolute',inset:0,background:'var(--specular)',pointerEvents:'none',borderRadius:'inherit'}}/>}
      <div style={{position:'relative'}}>{children}</div>
    </div>
  );
}
