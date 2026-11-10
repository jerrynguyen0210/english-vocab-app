import type React from 'react';

// Keep the screens and their controls real; isolate navigation and device chrome.
jest.mock('@/components/app-screen', () => ({
  AppScreen: ({ children }: React.PropsWithChildren) => <>{children}</>,
}));
jest.mock('expo-router', () => ({
  useLocalSearchParams: jest.fn(() => ({
    source: 'time',
    period: 'Weekly',
    includeOverdue: 'true',
  })),
  useFocusEffect: (callback: React.EffectCallback) =>
    jest.requireActual('react').useEffect(callback, [callback]),
  Link: ({ children }: React.PropsWithChildren) => <>{children}</>,
}));
jest.mock('@/context/session', () => ({
  useSession: () => ({ signedIn: true }),
}));
jest.mock('@/services/auth', () => ({
  authenticatedFetch: jest.fn(),
  AuthError: class AuthError extends Error {},
}));
