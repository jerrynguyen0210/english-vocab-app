import { type CSSProperties } from 'react';
import { StyleSheet } from 'react-native';
import type { AuthSubmitProps } from './auth-submit';

export function AuthSubmit({
  children,
  disabled,
  label,
  style,
}: AuthSubmitProps) {
  return (
    <button
      type="submit"
      disabled={disabled}
      aria-label={label}
      aria-busy={disabled}
      style={
        {
          border: 0,
          font: 'inherit',
          cursor: disabled ? 'default' : 'pointer',
          boxSizing: 'border-box',
          display: 'flex',
          ...StyleSheet.flatten(style),
        } as CSSProperties
      }
    >
      {children}
    </button>
  );
}
