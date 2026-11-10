import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  type CSSProperties,
} from 'react';
import { StyleSheet } from 'react-native';
import type { AuthInputHandle, AuthInputProps } from './auth-input';

export const AuthInput = forwardRef<AuthInputHandle, AuthInputProps>(
  function AuthInput(props, ref) {
    const input = useRef<HTMLInputElement>(null);
    const initialValue = useRef(props.value);
    const previousValue = useRef(props.value);
    // Preserve browser/password-manager writes across unrelated focus renders.
    // React owns explicit value changes; FormData owns the value at submission.
    useEffect(() => {
      if (previousValue.current !== props.value && input.current)
        input.current.value = props.value ?? '';
      previousValue.current = props.value;
    }, [props.value]);
    useImperativeHandle(
      ref,
      () => ({ focus: () => input.current?.focus() }),
      [],
    );
    const { paddingHorizontal, paddingVertical, ...inputStyle } =
      StyleSheet.flatten(props.style) ?? {};
    return (
      <input
        ref={input}
        id={props.nativeID}
        name={props.name}
        aria-label={props.accessibilityLabel}
        aria-labelledby={
          typeof props.accessibilityLabelledBy === 'string'
            ? props.accessibilityLabelledBy
            : undefined
        }
        aria-describedby={props.describedBy}
        aria-invalid={props['aria-invalid']}
        aria-required={props['aria-required']}
        required={props['aria-required']}
        type={
          props.secureTextEntry
            ? 'password'
            : props.keyboardType === 'email-address'
              ? 'email'
              : 'text'
        }
        autoComplete={props.autoComplete}
        enterKeyHint="go"
        autoCapitalize={props.autoCapitalize}
        spellCheck={false}
        readOnly={props.editable === false}
        placeholder={props.placeholder}
        defaultValue={initialValue.current}
        onChange={(event) => props.onChangeText?.(event.currentTarget.value)}
        onFocus={props.onFocus}
        onBlur={props.onBlur}
        style={
          {
            border: '0 solid',
            boxSizing: 'border-box',
            background: 'transparent',
            margin: 0,
            ...inputStyle,
            paddingInline: paddingHorizontal,
            paddingBlock: paddingVertical,
          } as CSSProperties
        }
      />
    );
  },
);
