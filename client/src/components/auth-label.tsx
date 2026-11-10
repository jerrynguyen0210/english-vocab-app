import { type PropsWithChildren } from 'react';
import { type StyleProp, type TextStyle } from 'react-native';
import { ThemedText } from './themed-text';

export type AuthLabelProps = PropsWithChildren<{
  id: string;
  inputId: string;
  style: StyleProp<TextStyle>;
}>;
export function AuthLabel({ id, children, style }: AuthLabelProps) {
  return (
    <ThemedText nativeID={id} style={style}>
      {children}
    </ThemedText>
  );
}
