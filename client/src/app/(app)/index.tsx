import { Image } from 'expo-image';
import { Platform, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { NavigationLink } from '@/components/navigation-link';
import { ThemedText } from '@/components/themed-text';
import { WordwellColors as colors } from '@/constants/wordwell-theme';

// Preview values from the supplied Home design, pending progress integration.
const preview = { due: 12, saved: 48 };
const navigation = [
  {
    label: 'Home',
    href: '/',
    icon: require('@/assets/images/wordwell/home.svg'),
  },
  {
    label: 'Add',
    href: '/add-word',
    icon: require('@/assets/images/wordwell/add.svg'),
  },
  {
    label: 'Review',
    href: '/review',
    icon: require('@/assets/images/wordwell/review.svg'),
  },
  {
    label: 'Account',
    href: '/account',
    icon: require('@/assets/images/wordwell/account.svg'),
  },
] as const;

export default function HomeScreen() {
  return (
    <SafeAreaView style={styles.page} edges={['top', 'left', 'right']}>
      <View style={styles.header}>
        <View style={styles.headerContent}>
          <View style={styles.brand} accessible accessibilityLabel="Wordwell">
            <View style={styles.brandMark}>
              <ThemedText style={styles.brandLetter}>W</ThemedText>
            </View>
            <ThemedText style={styles.brandName}>Wordwell</ThemedText>
          </View>
          <NavigationLink
            href="/account"
            label="Open account"
            style={styles.accountButton}
          >
            <View style={styles.accountCircle}>
              <Image
                source={require('@/assets/images/wordwell/account-primary.svg')}
                style={styles.icon}
                accessible={false}
              />
            </View>
          </NavigationLink>
        </View>
      </View>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
      >
        <View style={styles.content}>
          <ThemedText style={styles.greeting} accessibilityRole="header">
            Good morning
          </ThemedText>
          <ThemedText style={styles.subtitle}>
            Make today a word better.
          </ThemedText>
          <View style={styles.dueCard}>
            <ThemedText style={styles.eyebrow}>WORDS DUE TODAY</ThemedText>
            <ThemedText
              style={styles.dueCount}
              accessibilityLabel={`${preview.due} words due today, sample data`}
            >
              {preview.due}
            </ThemedText>
            <ThemedText style={styles.duePrompt}>
              Ready for a quick review?
            </ThemedText>
            <View style={styles.sparkle}>
              <Image
                source={require('@/assets/images/wordwell/sparkle.svg')}
                style={styles.sparkleIcon}
                accessible={false}
              />
            </View>
          </View>
          <ThemedText style={styles.sectionTitle} accessibilityRole="header">
            What would you like to do?
          </ThemedText>
          <View style={styles.actions}>
            <NavigationLink
              href="/add-word"
              label="Add word"
              style={[styles.action, styles.primaryAction]}
            >
              <Image
                source={require('@/assets/images/wordwell/add-white.svg')}
                style={styles.icon}
                accessible={false}
              />
              <ThemedText style={[styles.actionText, styles.primaryText]}>
                Add word
              </ThemedText>
            </NavigationLink>
            <NavigationLink
              href="/review"
              label="Start review"
              style={[styles.action, styles.secondaryAction]}
            >
              <Image
                source={require('@/assets/images/wordwell/review-dark.svg')}
                style={styles.icon}
                accessible={false}
              />
              <ThemedText style={styles.actionText}>Start review</ThemedText>
            </NavigationLink>
          </View>
          <View style={styles.progressCard}>
            <ThemedText style={styles.progressTitle}>
              Your daily progress
            </ThemedText>
            <ThemedText style={styles.progressDetail}>
              {preview.saved} saved words · {preview.due} ready to review
            </ThemedText>
            <ThemedText style={styles.previewNote}>Sample data</ThemedText>
          </View>
        </View>
      </ScrollView>
      <SafeAreaView edges={['bottom']} style={styles.footer}>
        <View style={styles.navigation}>
          {navigation.map(({ label, href, icon }) => (
            <NavigationLink
              key={label}
              href={href}
              replace={href === '/'}
              label={label}
              selected={href === '/'}
              style={[styles.navItem, href === '/' && styles.navSelected]}
            >
              <Image source={icon} style={styles.icon} accessible={false} />
              <ThemedText
                style={[
                  styles.navLabel,
                  href === '/' && styles.navLabelSelected,
                ]}
              >
                {label}
              </ThemedText>
            </NavigationLink>
          ))}
        </View>
      </SafeAreaView>
    </SafeAreaView>
  );
}

const fontFamily = Platform.select({
  web: 'Arial, sans-serif',
  default: undefined,
});
const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.background },
  header: {
    backgroundColor: colors.surface,
    borderBottomColor: colors.border,
    borderBottomWidth: 1,
  },
  headerContent: {
    width: '100%',
    maxWidth: 600,
    alignSelf: 'center',
    minHeight: 65,
    paddingHorizontal: 21,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  brand: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  brandMark: {
    height: 36,
    width: 36,
    borderRadius: 11,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  brandLetter: {
    fontFamily,
    color: colors.surface,
    fontSize: 21,
    lineHeight: 27,
    fontWeight: '800',
  },
  brandName: {
    fontFamily,
    color: colors.text,
    fontSize: 19,
    lineHeight: 26,
    fontWeight: '800',
  },
  accountButton: {
    minWidth: 44,
    minHeight: 44,
    justifyContent: 'center',
    alignItems: 'center',
    borderRadius: 22,
  },
  accountCircle: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  icon: { width: 24, height: 24 },
  scroll: { flex: 1 },
  scrollContent: { flexGrow: 1 },
  content: {
    width: '100%',
    maxWidth: 600,
    alignSelf: 'center',
    paddingHorizontal: 22,
    paddingTop: 25,
    paddingBottom: 36,
  },
  greeting: {
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
  dueCard: {
    marginTop: 30,
    backgroundColor: colors.primary,
    borderRadius: 18,
    paddingHorizontal: 23,
    paddingVertical: 24,
    minHeight: 174,
  },
  eyebrow: {
    fontFamily,
    color: colors.surface,
    fontSize: 12,
    lineHeight: 17,
    fontWeight: '600',
    letterSpacing: 1.1,
    paddingRight: 56,
  },
  dueCount: {
    fontFamily,
    color: colors.surface,
    fontSize: 67,
    lineHeight: 80,
    fontWeight: '800',
    marginTop: 5,
    paddingRight: 64,
  },
  duePrompt: {
    fontFamily,
    color: colors.surface,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '600',
    marginTop: 4,
  },
  sparkle: {
    position: 'absolute',
    top: 31,
    right: 30,
    width: 57,
    height: 57,
    borderRadius: 17,
    backgroundColor: colors.highlight,
    justifyContent: 'center',
    alignItems: 'center',
  },
  sparkleIcon: { width: 32, height: 32 },
  sectionTitle: {
    fontFamily,
    color: colors.text,
    fontSize: 19,
    lineHeight: 25,
    fontWeight: '700',
    marginTop: 31,
  },
  actions: { gap: 16, marginTop: 22 },
  action: {
    minHeight: 54,
    borderRadius: 13,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 12,
    padding: 14,
  },
  primaryAction: { backgroundColor: colors.primary },
  secondaryAction: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
  },
  actionText: {
    fontFamily,
    color: colors.text,
    fontSize: 15,
    lineHeight: 22,
    fontWeight: '600',
  },
  primaryText: { color: colors.surface },
  progressCard: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 16,
    padding: 17,
    minHeight: 100,
    marginTop: 23,
  },
  progressTitle: {
    fontFamily,
    color: colors.text,
    fontSize: 16,
    lineHeight: 22,
    fontWeight: '600',
  },
  progressDetail: {
    fontFamily,
    color: colors.secondary,
    fontSize: 13,
    lineHeight: 20,
    fontWeight: '400',
    marginTop: 7,
  },
  previewNote: {
    fontFamily,
    color: colors.secondary,
    fontSize: 11,
    lineHeight: 16,
    fontWeight: '400',
    marginTop: 4,
  },
  footer: {
    backgroundColor: colors.surface,
    borderTopColor: colors.border,
    borderTopWidth: 1,
  },
  navigation: {
    width: '100%',
    maxWidth: 600,
    alignSelf: 'center',
    flexDirection: 'row',
    justifyContent: 'space-around',
    paddingHorizontal: 12,
    paddingVertical: 8,
    gap: 8,
  },
  navItem: {
    flex: 1,
    minHeight: 52,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 2,
  },
  navSelected: { backgroundColor: colors.primarySoft },
  navLabel: {
    fontFamily,
    color: colors.placeholder,
    fontSize: 11,
    lineHeight: 16,
    fontWeight: '500',
  },
  navLabelSelected: { color: colors.primary, fontWeight: '600' },
});
