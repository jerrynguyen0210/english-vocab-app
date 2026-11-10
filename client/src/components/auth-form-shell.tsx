import { type PropsWithChildren } from 'react';
import { View } from 'react-native';

export type AuthValues = { name: string; email: string; password: string };
export type AuthFormShellProps = PropsWithChildren<{
  label: string;
  onSubmit: (values?: AuthValues) => void;
}>;

export function AuthFormShell({ children }: AuthFormShellProps) {
  return <View>{children}</View>;
}
