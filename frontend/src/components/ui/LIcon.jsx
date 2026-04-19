import React from "react";
import * as icons from "lucide-react";

export function LIcon({ name, size = 16, color, style }) {
  // Convert 'shield-check' to 'ShieldCheck'
  const componentName = name.split('-').map(part => part.charAt(0).toUpperCase() + part.slice(1)).join('');
  const IconComponent = icons[componentName];
  if (!IconComponent) return null;
  return <IconComponent size={size} color={color} style={style} strokeWidth={1.5} />;
}
