import { Image } from 'expo-image';
import { StyleSheet, View } from 'react-native';
import { NavigationLink } from '@/components/navigation-link';
import { ThemedText } from '@/components/themed-text';
import { WordwellColors as colors } from '@/constants/wordwell-theme';
import { type ReviewEmptyKind } from '@/services/review';

const messages = {
  empty_bank: {
    title: 'Empty word bank',
    detail: 'Save a word to start building your vocabulary.',
    action: 'Add your first word',
  },
  nothing_due: {
    title: 'Nothing due',
    detail: "You're all caught up",
    action: 'Add word',
  },
  no_matches: {
    title: 'No words match this review',
    detail: 'Try another topic, source or time period, or add a word.',
    action: 'Add word',
  },
};
export function ReviewEmptyState({
  kind,
  showAction = true,
}: {
  kind: ReviewEmptyKind;
  showAction?: boolean;
}) {
  const message = messages[kind];
  return (
    <View style={styles.card}>
      <Image
        source={require('@/assets/images/wordwell/review-empty.svg')}
        style={styles.image}
        accessible={false}
      />
      <ThemedText style={styles.title} accessibilityRole="header">
        {message.title}
      </ThemedText>
      <ThemedText style={styles.detail} accessibilityLiveRegion="polite">
        {message.detail}
      </ThemedText>
      {showAction && (
        <NavigationLink
          href="/add-word"
          label={message.action}
          style={styles.button}
        >
          <ThemedText style={styles.buttonText}>{message.action}</ThemedText>
        </NavigationLink>
      )}
    </View>
  );
}
const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 16,
    padding: 22,
    gap: 16,
    alignItems: 'stretch',
    marginTop: 20,
  },
  image: { width: 78, height: 78, alignSelf: 'center' },
  title: {
    color: colors.text,
    fontSize: 24,
    lineHeight: 30,
    fontWeight: '800',
    textAlign: 'center',
  },
  detail: {
    color: colors.secondary,
    fontSize: 14,
    lineHeight: 23,
    textAlign: 'center',
  },
  button: {
    backgroundColor: colors.primary,
    minHeight: 53,
    padding: 14,
    borderRadius: 13,
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonText: { color: colors.surface, fontSize: 15, fontWeight: '600' },
});
