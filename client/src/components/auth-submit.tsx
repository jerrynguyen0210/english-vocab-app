import { type PropsWithChildren } from 'react';
import { Pressable, type StyleProp, type ViewStyle } from 'react-native';

export type AuthSubmitProps = PropsWithChildren<{
  onPress: () => void;
  disabled: boolean;
  label: string;
  style: StyleProp<ViewStyle>;
}>;

export function AuthSubmit({
  children,
  disabled,
  label,
  style,
  onPress,
}: AuthSubmitProps) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled, busy: disabled }}
      style={({ pressed }) => [style, pressed && { opacity: 0.7 }]}
    >
      {children}
    </Pressable>
  );
}
