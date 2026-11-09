import { Link } from 'expo-router';
import { useId, useRef, useState, type ComponentRef } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  TextInput,
  StyleSheet,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
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
type InputInstance = ComponentRef<typeof TextInput>;

function FieldError({ message }: { message?: string }) {
  return message ? (
    <ThemedText
      style={styles.fieldError}
      accessibilityRole="alert"
      accessibilityLiveRegion="polite"
    >
      {message}
    </ThemedText>
  ) : null;
}

export function AuthForm({ signUp = false }: { signUp?: boolean }) {
  const session = useSession();
  const fieldId = useId();
  const nameInput = useRef<InputInstance>(null);
  const emailInput = useRef<InputInstance>(null);
  const passwordInput = useRef<InputInstance>(null);
  const submitting = useRef(false);
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
  const validation = validateCredentials(email, password);
  const invalidName = signUp ? validateName(name) : undefined;
  const nameError = touched.name ? invalidName : undefined;
  const emailError = touched.email ? validation.email : undefined;
  const passwordError = touched.password ? validation.password : undefined;
  const action = signUp ? 'Create account' : 'Sign in';

  function blur(field: Field) {
    setFocused(null);
    setTouched((previous) => ({ ...previous, [field]: true }));
  }
  function fieldStyle(field: Field, invalid?: string) {
    return [
      styles.input,
      focused === field && styles.focused,
      !!invalid && styles.invalid,
    ];
  }
  async function submit() {
    if (submitting.current) return;
    setTouched({ name: true, email: true, password: true });
    setError('');
    if (invalidName || validation.email || validation.password) {
      (invalidName
        ? nameInput
        : validation.email
          ? emailInput
          : passwordInput
      ).current?.focus();
      return;
    }
    submitting.current = true;
    setPending(true);
    try {
      if (signUp) await session.signUp(email.trim(), password, name.trim());
      else await session.signIn(email.trim(), password);
    } catch (cause) {
      setError(
        authErrorMessage(
          cause instanceof AuthError ? cause.status : undefined,
          signUp,
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
                {signUp
                  ? 'Begin your English vocabulary journey.'
                  : 'Sign in to continue learning.'}
              </ThemedText>
            </View>
            <View style={[styles.form, signUp && styles.signUpForm]}>
              {signUp ? (
                <View style={[styles.field, styles.nameField]}>
                  <ThemedText
                    style={styles.label}
                    nativeID={`${fieldId}-name-label`}
                  >
                    Your name
                  </ThemedText>
                  <TextInput
                    ref={nameInput}
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
                    onBlur={() => blur('name')}
                    autoCapitalize="words"
                    autoComplete="name"
                    editable={!pending}
                    returnKeyType="next"
                    submitBehavior="submit"
                    onSubmitEditing={() => emailInput.current?.focus()}
                  />
                  <FieldError message={nameError} />
                </View>
              ) : null}
              <View style={styles.field}>
                <ThemedText
                  style={styles.label}
                  nativeID={`${fieldId}-email-label`}
                >
                  Email address
                </ThemedText>
                <TextInput
                  ref={emailInput}
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
                  onBlur={() => blur('email')}
                  autoCapitalize="none"
                  autoCorrect={false}
                  keyboardType="email-address"
                  autoComplete="email"
                  editable={!pending}
                  returnKeyType="next"
                  submitBehavior="submit"
                  onSubmitEditing={() => passwordInput.current?.focus()}
                />
                <FieldError message={emailError} />
              </View>
              <View style={styles.field}>
                <ThemedText
                  style={styles.label}
                  nativeID={`${fieldId}-password-label`}
                >
                  Password
                </ThemedText>
                <View
                  style={[
                    ...fieldStyle('password', passwordError),
                    styles.passwordRow,
                  ]}
                >
                  <TextInput
                    ref={passwordInput}
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
                    onBlur={() => blur('password')}
                    secureTextEntry={!visible}
                    autoCapitalize="none"
                    autoCorrect={false}
                    autoComplete={signUp ? 'new-password' : 'current-password'}
                    editable={!pending}
                    returnKeyType="go"
                    onSubmitEditing={submit}
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
                  <FieldError message={passwordError} />
                ) : signUp ? (
                  <ThemedText style={styles.helper}>
                    Use 12–128 characters.
                  </ThemedText>
                ) : null}
              </View>
            </View>
            <View style={[styles.actions, signUp && styles.signUpActions]}>
              {error ? (
                <ThemedText
                  style={styles.errorBanner}
                  accessibilityRole="alert"
                  accessibilityLiveRegion="polite"
                >
                  {error}
                </ThemedText>
              ) : null}
              <Pressable
                onPress={submit}
                disabled={pending}
                accessibilityRole="button"
                accessibilityLabel={
                  pending
                    ? signUp
                      ? 'Creating your account'
                      : 'Signing in'
                    : action
                }
                accessibilityState={{ disabled: pending, busy: pending }}
                style={({ pressed }) => [
                  styles.primary,
                  (pressed || pending) && styles.pressed,
                ]}
              >
                {pending ? <ActivityIndicator color={colors.surface} /> : null}
                <ThemedText style={styles.primaryText}>
                  {pending
                    ? signUp
                      ? 'Creating account…'
                      : 'Signing in…'
                    : action}
                </ThemedText>
              </Pressable>
              <View style={styles.linkSlot}>
                {pending ? null : (
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
