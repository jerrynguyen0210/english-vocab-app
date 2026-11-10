import { connectionMessage } from '@/services/connectivity';
import { Link } from 'expo-router';
import { useEffect, useId, useRef, useState, type ComponentRef } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import {
  AuthInput as TextInput,
  type AuthInputHandle,
} from '@/components/auth-input';
import { AuthLabel } from '@/components/auth-label';
import { AuthSubmit } from '@/components/auth-submit';
import { AuthFormShell, type AuthValues } from '@/components/auth-form-shell';
import { ThemedText } from '@/components/themed-text';
import { AuthColors as colors } from '@/constants/auth-theme';
import { useSession } from '@/context/session';
import { AuthError } from '@/services/auth';
import {
  authErrorMessage,
  validateCredentials,
  validateName,
} from '@/utils/auth-validation';

type Field = 'name' | 'email' | 'password';
type InputInstance = AuthInputHandle;

function FieldError({ message, id }: { message?: string; id: string }) {
  return message ? (
    <ThemedText
      nativeID={id}
      style={styles.fieldError}
      accessibilityRole="alert"
      accessibilityLiveRegion="polite"
    >
      {message}
    </ThemedText>
  ) : null;
}

export function AuthForm({
  signUp = false,
  reauthenticate = false,
}: {
  signUp?: boolean;
  reauthenticate?: boolean;
}) {
  const session = useSession();
  const fieldId = useId();
  const nameInput = useRef<InputInstance>(null);
  const emailInput = useRef<InputInstance>(null);
  const passwordInput = useRef<InputInstance>(null);
  const submitting = useRef(false);
  const errorSummary = useRef<ComponentRef<typeof View>>(null);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [visible, setVisible] = useState(false);
  const [focused, setFocused] = useState<Field | null>(null);
  const [touched, setTouched] = useState({
    name: false,
    email: false,
    password: false,
  });
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    if (error) errorSummary.current?.focus();
  }, [error]);
  const validation = validateCredentials(email, password);
  const invalidName = signUp ? validateName(name) : undefined;
  const nameError = touched.name ? invalidName : undefined;
  const emailError = touched.email ? validation.email : undefined;
  const passwordError = touched.password ? validation.password : undefined;
  const action = signUp ? 'Create account' : 'Sign in';
  useEffect(() => {
    if (Platform.OS === 'web' || reauthenticate)
      (signUp ? nameInput : emailInput).current?.focus();
  }, [signUp, reauthenticate]);

  function blur() {
    // Validate on submit, then while editing. Adding errors during pointer blur
    // can move the next label/button between mouse-down and mouse-up.
    setFocused(null);
  }
  function fieldStyle(field: Field, invalid?: string) {
    return [
      styles.input,
      focused === field && styles.focused,
      !!invalid && styles.invalid,
    ];
  }
  async function submit(values?: AuthValues) {
    if (submitting.current) return;
    const submitted = values ?? { name, email, password };
    setName(submitted.name);
    setEmail(submitted.email);
    setPassword(submitted.password);
    const errors = validateCredentials(submitted.email, submitted.password);
    const nameIssue = signUp ? validateName(submitted.name) : undefined;
    setTouched({ name: true, email: true, password: true });
    setError('');
    if (nameIssue || errors.email || errors.password) {
      (nameIssue
        ? nameInput
        : errors.email
          ? emailInput
          : passwordInput
      ).current?.focus();
      return;
    }
    submitting.current = true;
    setPending(true);
    try {
      if (signUp)
        await session.signUp(
          submitted.email.trim(),
          submitted.password,
          submitted.name.trim(),
        );
      else await session.signIn(submitted.email.trim(), submitted.password);
    } catch (cause) {
      setError(
        connectionMessage(
          cause,
          authErrorMessage(
            cause instanceof AuthError ? cause.status : undefined,
            signUp,
          ),
        ),
      );
    } finally {
      submitting.current = false;
      setPending(false);
    }
  }

  return (
    <SafeAreaView style={styles.page}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView
          contentContainerStyle={styles.scroll}
          keyboardShouldPersistTaps="handled"
        >
          <View style={styles.content}>
            <View style={styles.brand} accessible accessibilityLabel="Wordwell">
              <View style={styles.brandMark}>
                <ThemedText style={styles.brandLetter}>W</ThemedText>
              </View>
              <ThemedText style={styles.brandName}>Wordwell</ThemedText>
            </View>
            <View
              style={[styles.introduction, signUp && styles.signUpIntroduction]}
            >
              <ThemedText style={styles.title} accessibilityRole="header">
                {signUp ? 'Create your account' : 'Welcome back'}
              </ThemedText>
              <ThemedText style={styles.subtitle}>
                {reauthenticate
                  ? 'Sign in to continue where you left off.'
                  : signUp
                    ? 'Begin your English vocabulary journey.'
                    : 'Sign in to continue learning.'}
              </ThemedText>
            </View>
            <AuthFormShell label={action} onSubmit={submit}>
              <View style={[styles.form, signUp && styles.signUpForm]}>
                {signUp ? (
                  <View style={[styles.field, styles.nameField]}>
                    <AuthLabel
                      style={styles.label}
                      id={`${fieldId}-name-label`}
                      inputId={`${fieldId}-name`}
                    >
                      Your name
                    </AuthLabel>
                    <TextInput
                      ref={nameInput}
                      nativeID={`${fieldId}-name`}
                      name="name"
                      aria-required
                      importantForAutofill="yes"
                      describedBy={
                        nameError ? `${fieldId}-name-error` : undefined
                      }
                      accessibilityLabel="Your name"
                      accessibilityLabelledBy={`${fieldId}-name-label`}
                      accessibilityHint={nameError}
                      aria-invalid={!!nameError}
                      placeholder="e.g. Alex"
                      placeholderTextColor={colors.placeholder}
                      style={fieldStyle('name', nameError)}
                      value={name}
                      onChangeText={(value) => {
                        setName(value);
                        setError('');
                      }}
                      onFocus={() => setFocused('name')}
                      onBlur={blur}
                      autoCapitalize="words"
                      autoComplete="name"
                      textContentType="name"
                      editable={!pending}
                      returnKeyType="next"
                      submitBehavior="submit"
                      onSubmitEditing={
                        Platform.OS === 'web'
                          ? undefined
                          : () => emailInput.current?.focus()
                      }
                    />
                    <FieldError
                      id={`${fieldId}-name-error`}
                      message={nameError}
                    />
                  </View>
                ) : null}
                <View style={styles.field}>
                  <AuthLabel
                    style={styles.label}
                    id={`${fieldId}-email-label`}
                    inputId={`${fieldId}-email`}
                  >
                    Email address
                  </AuthLabel>
                  <TextInput
                    ref={emailInput}
                    nativeID={`${fieldId}-email`}
                    name="email"
                    aria-required
                    importantForAutofill="yes"
                    describedBy={
                      emailError ? `${fieldId}-email-error` : undefined
                    }
                    accessibilityLabel="Email address"
                    accessibilityLabelledBy={`${fieldId}-email-label`}
                    accessibilityHint={emailError}
                    aria-invalid={!!emailError}
                    placeholder="you@example.com"
                    placeholderTextColor={colors.placeholder}
                    style={fieldStyle('email', emailError)}
                    value={email}
                    onChangeText={(value) => {
                      setEmail(value);
                      setError('');
                    }}
                    onFocus={() => setFocused('email')}
                    onBlur={blur}
                    autoCapitalize="none"
                    autoCorrect={false}
                    keyboardType="email-address"
                    autoComplete="username"
                    textContentType="username"
                    editable={!pending}
                    returnKeyType="next"
                    submitBehavior="submit"
                    onSubmitEditing={
                      Platform.OS === 'web'
                        ? undefined
                        : () => passwordInput.current?.focus()
                    }
                  />
                  <FieldError
                    id={`${fieldId}-email-error`}
                    message={emailError}
                  />
                </View>
                <View style={styles.field}>
                  <AuthLabel
                    style={styles.label}
                    id={`${fieldId}-password-label`}
                    inputId={`${fieldId}-password`}
                  >
                    Password
                  </AuthLabel>
                  <View
                    style={[
                      ...fieldStyle('password', passwordError),
                      styles.passwordRow,
                    ]}
                  >
                    <TextInput
                      ref={passwordInput}
                      nativeID={`${fieldId}-password`}
                      name="password"
                      aria-required
                      importantForAutofill="yes"
                      describedBy={
                        passwordError
                          ? `${fieldId}-password-error`
                          : signUp
                            ? `${fieldId}-password-help`
                            : undefined
                      }
                      accessibilityLabel="Password"
                      accessibilityLabelledBy={`${fieldId}-password-label`}
                      accessibilityHint={
                        passwordError ?? 'Use 12 to 128 characters.'
                      }
                      aria-invalid={!!passwordError}
                      placeholder="••••••••"
                      placeholderTextColor={colors.placeholder}
                      style={styles.passwordInput}
                      value={password}
                      onChangeText={(value) => {
                        setPassword(value);
                        setError('');
                      }}
                      onFocus={() => setFocused('password')}
                      onBlur={blur}
                      secureTextEntry={!visible}
                      autoCapitalize="none"
                      autoCorrect={false}
                      autoComplete={
                        signUp ? 'new-password' : 'current-password'
                      }
                      textContentType={signUp ? 'newPassword' : 'password'}
                      editable={!pending}
                      returnKeyType="go"
                      onSubmitEditing={
                        Platform.OS === 'web' ? undefined : () => submit()
                      }
                    />
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel={
                        visible ? 'Hide password' : 'Show password'
                      }
                      accessibilityState={{ disabled: pending }}
                      disabled={pending}
                      onPress={() => setVisible((value) => !value)}
                      style={({ pressed }) => [
                        styles.visibility,
                        pressed && styles.pressed,
                      ]}
                    >
                      <ThemedText style={styles.visibilityText}>
                        {visible ? 'Hide' : 'Show'}
                      </ThemedText>
                    </Pressable>
                  </View>
                  {passwordError ? (
                    <FieldError
                      id={`${fieldId}-password-error`}
                      message={passwordError}
                    />
                  ) : signUp ? (
                    <ThemedText
                      nativeID={`${fieldId}-password-help`}
                      style={styles.helper}
                    >
                      Use 12–128 characters.
                    </ThemedText>
                  ) : null}
                </View>
              </View>
              <View style={[styles.actions, signUp && styles.signUpActions]}>
                {error ? (
                  <View
                    ref={errorSummary}
                    tabIndex={-1}
                    accessibilityRole="alert"
                    accessibilityLabel={error}
                  >
                    <ThemedText style={styles.errorBanner}>{error}</ThemedText>
                  </View>
                ) : null}
                <AuthSubmit
                  onPress={() => submit()}
                  disabled={pending}
                  label={
                    pending
                      ? signUp
                        ? 'Creating your account'
                        : 'Signing in'
                      : action
                  }
                  style={[styles.primary, pending && styles.pressed]}
                >
                  {pending ? (
                    <ActivityIndicator color={colors.surface} />
                  ) : null}
                  <ThemedText style={styles.primaryText}>
                    {pending
                      ? signUp
                        ? 'Creating account…'
                        : 'Signing in…'
                      : action}
                  </ThemedText>
                </AuthSubmit>
                <View style={styles.linkSlot}>
                  {pending || reauthenticate ? null : (
                    <Link
                      replace
                      href={signUp ? '/sign-in' : '/sign-up'}
                      style={styles.link}
                    >
                      {signUp
                        ? 'Already have an account?  Sign in'
                        : 'New here?  Create an account'}
                    </Link>
                  )}
                </View>
              </View>
            </AuthFormShell>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const fontFamily = Platform.select({
  web: 'Arial, sans-serif',
  default: undefined,
});
const styles = StyleSheet.create({
  flex: { flex: 1 },
  page: { flex: 1, backgroundColor: colors.background },
  scroll: { flexGrow: 1 },
  content: {
    width: '100%',
    maxWidth: 441,
    alignSelf: 'center',
    paddingHorizontal: 24,
    paddingTop: Platform.OS === 'web' ? 107 : 60,
    paddingBottom: 40,
  },
  brand: { flexDirection: 'row', alignItems: 'center', gap: 11 },
  brandMark: {
    height: 48,
    width: 48,
    borderRadius: 15,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  brandLetter: {
    fontFamily,
    color: colors.surface,
    fontSize: 26,
    lineHeight: 32,
    fontWeight: '800',
  },
  brandName: {
    fontFamily,
    color: colors.text,
    fontSize: 23,
    lineHeight: 30,
    fontWeight: '800',
  },
  introduction: { marginTop: 60 },
  signUpIntroduction: { marginTop: 38 },
  title: {
    fontFamily,
    color: colors.text,
    fontSize: 29,
    lineHeight: 35,
    fontWeight: '800',
  },
  subtitle: {
    fontFamily,
    color: colors.secondary,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '400',
    marginTop: 16,
  },
  form: { marginTop: 56, gap: 20 },
  signUpForm: { marginTop: 28 },
  field: { gap: 10 },
  nameField: { marginBottom: -3 },
  label: {
    fontFamily,
    color: colors.text,
    fontSize: 13,
    lineHeight: 16,
    fontWeight: '600',
  },
  input: {
    fontFamily,
    color: colors.text,
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 10,
    minHeight: 50,
    paddingHorizontal: 14,
    paddingVertical: 14,
    fontSize: 14,
  },
  focused: { borderColor: colors.primary },
  invalid: {
    borderColor: colors.error,
    backgroundColor: colors.errorBackground,
  },
  passwordRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 0,
    paddingHorizontal: 0,
  },
  passwordInput: {
    fontFamily,
    color: colors.text,
    flex: 1,
    minWidth: 0,
    paddingHorizontal: 14,
    paddingVertical: 14,
    fontSize: 14,
    minHeight: 48,
  },
  visibility: {
    minHeight: 48,
    minWidth: 58,
    paddingHorizontal: 12,
    justifyContent: 'center',
    alignItems: 'center',
    borderRadius: 10,
  },
  visibilityText: {
    fontFamily,
    color: colors.primary,
    fontSize: 13,
    fontWeight: '600',
  },
  helper: {
    fontFamily,
    color: colors.secondary,
    fontSize: 12,
    lineHeight: 18,
    fontWeight: '400',
  },
  fieldError: {
    fontFamily,
    color: colors.error,
    fontSize: 12,
    lineHeight: 18,
    fontWeight: '600',
  },
  actions: { marginTop: 48, gap: 16 },
  signUpActions: { marginTop: 20 },
  primary: {
    backgroundColor: colors.primary,
    borderRadius: 13,
    minHeight: 53,
    padding: 16,
    flexDirection: 'row',
    gap: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryText: {
    fontFamily,
    color: colors.surface,
    fontSize: 15,
    lineHeight: 21,
    fontWeight: '600',
  },
  pressed: { opacity: 0.7 },
  linkSlot: { minHeight: 44, justifyContent: 'flex-start' },
  link: {
    fontFamily,
    color: colors.primary,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '600',
    textAlign: 'center',
    paddingVertical: 2,
  },
  errorBanner: {
    fontFamily,
    color: colors.error,
    backgroundColor: colors.errorBackground,
    borderRadius: 10,
    padding: 14,
    fontSize: 13,
    lineHeight: 20,
  },
});
