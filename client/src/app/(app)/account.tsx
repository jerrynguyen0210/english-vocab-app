import { useRef, useState, type ComponentRef } from 'react';
import {
  ActivityIndicator,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
} from 'react-native';
import { AppScreen } from '@/components/app-screen';
import { ThemedText } from '@/components/themed-text';
import { WordwellColors as colors } from '@/constants/wordwell-theme';
import { useSession } from '@/context/session';
import { AuthError } from '@/services/auth';

export default function AccountScreen() {
  const { profile, signOut, deleteAccount } = useSession();
  const [confirming, setConfirming] = useState(false);
  const [pending, setPending] = useState<'logout' | 'delete' | null>(null);
  const [error, setError] = useState('');
  const busy = useRef(false);
  const cancelButton = useRef<ComponentRef<typeof Pressable>>(null);
  const deleteButton = useRef<ComponentRef<typeof Pressable>>(null);
  const initials = (
    profile?.name
      ?.trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((part) => Array.from(part)[0])
      .join('') ||
    profile?.email?.[0] ||
    'W'
  ).toUpperCase();

  function cancel() {
    if (busy.current) return;
    setConfirming(false);
    setError('');
    deleteButton.current?.focus();
  }
  async function perform(action: 'logout' | 'delete') {
    if (busy.current) return;
    busy.current = true;
    setPending(action);
    setError('');
    try {
      await (action === 'delete' ? deleteAccount() : signOut());
    } catch (cause) {
      setError(
        cause instanceof AuthError && cause.status === 401
          ? 'Your session expired. Sign in and try again.'
          : action === 'delete'
            ? 'Unable to delete your account. Check your connection and try again.'
            : 'Unable to sign out. Check your connection and try again.',
      );
    } finally {
      busy.current = false;
      setPending(null);
    }
  }

  return (
    <AppScreen selected="Account">
      <View style={styles.content}>
        <ThemedText style={styles.title} accessibilityRole="header">
          Your account
        </ThemedText>
        <ThemedText style={styles.subtitle}>
          Manage your learning profile.
        </ThemedText>
        <View style={styles.profileCard}>
          <View style={styles.profileRow}>
            <View style={styles.avatar} accessible={false}>
              <ThemedText style={styles.initials}>{initials}</ThemedText>
            </View>
            <View style={styles.profileDetails}>
              <ThemedText style={styles.profileTitle}>
                {profile?.name || 'Your profile'}
              </ThemedText>
              <ThemedText
                style={styles.email}
                numberOfLines={2}
                ellipsizeMode="middle"
                selectable
              >
                {profile?.email || 'Email unavailable'}
              </ThemedText>
            </View>
          </View>
          <View style={styles.divider} />
          <ThemedText style={styles.security}>Signed in securely</ThemedText>
          <View style={styles.status}>
            <ThemedText style={styles.statusText}>ACTIVE</ThemedText>
          </View>
        </View>
        {error && !confirming ? (
          <ThemedText
            style={styles.error}
            accessibilityRole="alert"
            accessibilityLiveRegion="polite"
          >
            {error}
          </ThemedText>
        ) : null}
        <View style={styles.actions}>
          <Pressable
            accessibilityRole="button"
            disabled={!!pending}
            accessibilityState={{
              disabled: !!pending,
              busy: pending === 'logout',
            }}
            onPress={() => perform('logout')}
            style={({ pressed }) => [
              styles.button,
              styles.secondaryButton,
              (pressed || !!pending) && styles.dimmed,
            ]}
          >
            {pending === 'logout' ? (
              <ActivityIndicator color={colors.text} />
            ) : null}
            <ThemedText style={styles.buttonText}>
              {pending === 'logout' ? 'Signing out…' : 'Sign out'}
            </ThemedText>
          </Pressable>
          <Pressable
            ref={deleteButton}
            accessibilityRole="button"
            disabled={!!pending}
            accessibilityState={{ disabled: !!pending }}
            onPress={() => {
              setError('');
              setConfirming(true);
            }}
            style={({ pressed }) => [
              styles.button,
              styles.dangerButton,
              (pressed || !!pending) && styles.dimmed,
            ]}
          >
            <ThemedText style={[styles.buttonText, styles.dangerText]}>
              Delete account
            </ThemedText>
          </Pressable>
        </View>
      </View>
      <Modal
        visible={confirming}
        transparent
        animationType="fade"
        onRequestClose={cancel}
        onShow={() => cancelButton.current?.focus()}
      >
        <View style={styles.backdrop}>
          <ScrollView
            contentContainerStyle={styles.dialogScroll}
            bounces={false}
          >
            <View style={styles.dialog} accessibilityViewIsModal>
              <View style={styles.warningIcon} accessible={false}>
                <ThemedText style={styles.warningMark}>!</ThemedText>
              </View>
              <ThemedText style={styles.dialogTitle} accessibilityRole="header">
                Delete your account?
              </ThemedText>
              <ThemedText style={styles.description}>
                This permanently deletes your account and saved words. It cannot
                be undone.
              </ThemedText>
              {error ? (
                <ThemedText
                  style={styles.error}
                  accessibilityRole="alert"
                  accessibilityLiveRegion="polite"
                >
                  {error}
                </ThemedText>
              ) : null}
              <View style={styles.dialogActions}>
                <Pressable
                  ref={cancelButton}
                  accessibilityRole="button"
                  disabled={!!pending}
                  accessibilityState={{ disabled: !!pending }}
                  onPress={cancel}
                  style={({ pressed }) => [
                    styles.button,
                    styles.dialogButton,
                    styles.secondaryButton,
                    (pressed || !!pending) && styles.dimmed,
                  ]}
                >
                  <ThemedText style={styles.buttonText}>Cancel</ThemedText>
                </Pressable>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={
                    pending === 'delete'
                      ? 'Deleting account'
                      : 'Yes, delete account'
                  }
                  disabled={!!pending}
                  accessibilityState={{
                    disabled: !!pending,
                    busy: pending === 'delete',
                  }}
                  onPress={() => perform('delete')}
                  style={({ pressed }) => [
                    styles.button,
                    styles.dialogButton,
                    styles.dangerButton,
                    (pressed || !!pending) && styles.dimmed,
                  ]}
                >
                  {pending === 'delete' ? (
                    <ActivityIndicator color={colors.surface} />
                  ) : null}
                  <ThemedText style={[styles.buttonText, styles.dangerText]}>
                    {pending === 'delete'
                      ? 'Deleting account…'
                      : 'Yes, delete account'}
                  </ThemedText>
                </Pressable>
              </View>
            </View>
          </ScrollView>
        </View>
      </Modal>
    </AppScreen>
  );
}
const fontFamily = Platform.select({
  web: 'Arial, sans-serif',
  default: undefined,
});
const styles = StyleSheet.create({
  content: {
    width: '100%',
    maxWidth: 600,
    alignSelf: 'center',
    paddingHorizontal: 22,
    paddingTop: 25,
    paddingBottom: 36,
  },
  title: {
    fontFamily,
    color: colors.text,
    fontSize: 28,
    lineHeight: 34,
    fontWeight: '800',
  },
  subtitle: {
    fontFamily,
    color: colors.secondary,
    fontSize: 13,
    lineHeight: 20,
    fontWeight: '400',
    marginTop: 9,
  },
  profileCard: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 16,
    padding: 18,
    minHeight: 209,
    marginTop: 42,
  },
  profileRow: { flexDirection: 'row', gap: 17, alignItems: 'center' },
  avatar: {
    width: 58,
    height: 58,
    borderRadius: 29,
    backgroundColor: colors.primarySoft,
    justifyContent: 'center',
    alignItems: 'center',
  },
  initials: {
    fontFamily,
    color: colors.primary,
    fontSize: 19,
    lineHeight: 26,
    fontWeight: '700',
  },
  profileDetails: { flex: 1, minWidth: 0, gap: 10 },
  profileTitle: {
    fontFamily,
    color: colors.text,
    fontSize: 16,
    lineHeight: 22,
    fontWeight: '700',
  },
  email: {
    fontFamily,
    color: colors.secondary,
    fontSize: 13,
    lineHeight: 20,
    fontWeight: '400',
  },
  divider: {
    height: 1,
    backgroundColor: colors.border,
    marginTop: 28,
    marginBottom: 24,
  },
  security: {
    fontFamily,
    color: colors.secondary,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '500',
  },
  status: {
    alignSelf: 'flex-start',
    minWidth: 81,
    minHeight: 27,
    borderRadius: 14,
    backgroundColor: colors.successBackground,
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 10,
    paddingHorizontal: 12,
  },
  statusText: {
    fontFamily,
    color: colors.success,
    fontSize: 10,
    lineHeight: 16,
    fontWeight: '800',
  },
  actions: { gap: 15, marginTop: 30 },
  button: {
    minHeight: 54,
    borderRadius: 13,
    paddingHorizontal: 14,
    paddingVertical: 14,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 10,
  },
  secondaryButton: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
  },
  dangerButton: { backgroundColor: colors.error },
  buttonText: {
    fontFamily,
    color: colors.text,
    fontSize: 15,
    lineHeight: 22,
    fontWeight: '600',
  },
  dangerText: { color: colors.surface },
  dimmed: { opacity: 0.7 },
  error: {
    fontFamily,
    color: colors.error,
    backgroundColor: colors.errorBackground,
    borderRadius: 10,
    padding: 12,
    fontSize: 13,
    lineHeight: 20,
    marginTop: 16,
  },
  backdrop: { flex: 1, backgroundColor: colors.overlay },
  dialogScroll: {
    flexGrow: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 21,
    paddingVertical: 24,
  },
  dialog: {
    backgroundColor: colors.surface,
    borderRadius: 20,
    width: '100%',
    maxWidth: 351,
    padding: 23,
  },
  warningIcon: {
    height: 42,
    width: 42,
    borderRadius: 21,
    backgroundColor: colors.errorBackground,
    alignItems: 'center',
    justifyContent: 'center',
  },
  warningMark: {
    fontFamily,
    color: colors.error,
    fontSize: 22,
    lineHeight: 28,
    fontWeight: '800',
  },
  dialogTitle: {
    fontFamily,
    color: colors.text,
    fontSize: 22,
    lineHeight: 28,
    fontWeight: '800',
    marginTop: 14,
  },
  description: {
    fontFamily,
    color: colors.secondary,
    fontSize: 14,
    lineHeight: 22,
    fontWeight: '400',
    marginTop: 22,
  },
  dialogActions: { gap: 15, marginTop: 32 },
  dialogButton: { minHeight: 45, paddingVertical: 11 },
});
