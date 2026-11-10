import { Image } from 'expo-image';
import { Platform, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { type PropsWithChildren } from 'react';
import { NavigationLink } from '@/components/navigation-link';
import { ThemedText } from '@/components/themed-text';
import { WordwellColors as colors } from '@/constants/wordwell-theme';

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

export function AppScreen({
  children,
  selected,
}: PropsWithChildren<{ selected: 'Home' | 'Add' | 'Review' | 'Account' }>) {
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
            replace={selected === 'Account'}
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
        automaticallyAdjustKeyboardInsets
        keyboardShouldPersistTaps="handled"
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
      >
        {children}
      </ScrollView>
      <SafeAreaView edges={['bottom']} style={styles.footer}>
        <View style={styles.navigation}>
          {navigation.map(({ label, href, icon }) => (
            <NavigationLink
              key={label}
              href={href}
              replace={label === selected}
              label={label}
              selected={label === selected}
              style={[styles.navItem, label === selected && styles.navSelected]}
            >
              <Image
                source={
                  label === 'Home' && selected !== 'Home'
                    ? require('@/assets/images/wordwell/home-muted.svg')
                    : label === 'Add' && selected === 'Add'
                      ? require('@/assets/images/wordwell/add-active.svg')
                      : label === 'Account' && selected === 'Account'
                        ? require('@/assets/images/wordwell/account-active.svg')
                        : icon
                }
                style={styles.icon}
                accessible={false}
              />
              <ThemedText
                style={[
                  styles.navLabel,
                  label === selected && styles.navLabelSelected,
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
