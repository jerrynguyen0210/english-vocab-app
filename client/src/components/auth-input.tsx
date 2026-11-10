import {
  forwardRef,
  useImperativeHandle,
  useRef,
  type ComponentRef,
} from 'react';
import { TextInput, type TextInputProps } from 'react-native';

export type AuthInputHandle = { focus: () => void };
export type AuthInputProps = Omit<TextInputProps, 'onFocus' | 'onBlur'> & {
  name: string;
  'aria-invalid'?: boolean;
  'aria-required'?: boolean;
  describedBy?: string;
  onFocus?: () => void;
  onBlur?: () => void;
};

export const AuthInput = forwardRef<AuthInputHandle, AuthInputProps>(
  function AuthInput(
    { name: _name, describedBy: _describedBy, ...props },
    ref,
  ) {
    const input = useRef<ComponentRef<typeof TextInput>>(null);
    useImperativeHandle(
      ref,
      () => ({ focus: () => input.current?.focus() }),
      [],
    );
    return <TextInput {...props} ref={input} />;
  },
);
