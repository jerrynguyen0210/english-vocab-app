import { type CSSProperties } from 'react';
import { StyleSheet } from 'react-native';
import type { AuthLabelProps } from './auth-label';

export function AuthLabel({ id, inputId, children, style }: AuthLabelProps) {
  const textStyle = StyleSheet.flatten(style);
  return (
    <label
      id={id}
      htmlFor={inputId}
      style={
        {
          ...textStyle,
          lineHeight:
            textStyle?.lineHeight === undefined
              ? undefined
              : `${textStyle.lineHeight}px`,
        } as CSSProperties
      }
    >
      {children}
    </label>
  );
}
