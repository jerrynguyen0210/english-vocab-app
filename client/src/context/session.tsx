import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type PropsWithChildren,
} from 'react';
import { AppState } from 'react-native';
import * as auth from '@/services/auth';

const SessionContext = createContext<{
  signedIn: boolean;
  loading: boolean;
  needsSignIn: boolean;
  restoreError: boolean;
  appKey: number;
  retryRestore: () => Promise<void>;
  signIn: typeof auth.signIn;
  signUp: typeof auth.register;
  signOut: typeof auth.signOut;
} | null>(null);

export function SessionProvider({ children }: PropsWithChildren) {
  const [signedIn, setSignedIn] = useState(false);
  const [loading, setLoading] = useState(true);
  const [needsSignIn, setNeedsSignIn] = useState(false);
  const [restoreError, setRestoreError] = useState(false);
  const [appKey, setAppKey] = useState(0);
  const hadSession = useRef(false);
  const userId = useRef<string | null>(null);
  const mounted = useRef(false);
  const lifecycle = useRef(0);
  const restoring = useRef<Promise<void> | null>(null);

  const acceptSession = useCallback(async (version = lifecycle.current) => {
    const response = await auth.authenticatedFetch('/auth/me');
    if (!response.ok) throw new auth.AuthError(response.status);
    const profile: { id: string } = await response.json();
    if (!profile.id) throw new Error('Missing profile identity.');
    if (!mounted.current || version !== lifecycle.current) return;
    // Retain drafts only for the same account; another account gets fresh screens.
    if (userId.current && userId.current !== profile.id)
      setAppKey((key) => key + 1);
    userId.current = profile.id;
    hadSession.current = true;
    setSignedIn(true);
    setNeedsSignIn(false);
    setRestoreError(false);
  }, []);

  const retryRestore = useCallback((): Promise<void> => {
    if (restoring.current) return restoring.current;
    if (!hadSession.current) setLoading(true);
    setRestoreError(false);
    const version = lifecycle.current;
    restoring.current = (async () => {
      try {
        await auth.refreshSession();
        await acceptSession(version);
      } catch (error) {
        if (!mounted.current || version !== lifecycle.current) return;
        if (error instanceof auth.AuthError && error.status === 401) {
          setSignedIn(false);
          setNeedsSignIn(hadSession.current);
        } else {
          // Preserve saved credentials, screens, and drafts when connectivity fails.
          setRestoreError(true);
        }
      } finally {
        restoring.current = null;
        if (mounted.current && version === lifecycle.current) setLoading(false);
      }
    })();
    return restoring.current;
  }, [acceptSession]);

  useEffect(() => {
    mounted.current = true;
    const unsubscribe = auth.onSessionExpired(() => {
      if (!mounted.current) return;
      setSignedIn(false);
      setNeedsSignIn(hadSession.current);
    });
    void retryRestore();
    let previousState = AppState.currentState;
    const subscription = AppState.addEventListener('change', (state) => {
      if (
        state === 'active' &&
        previousState !== 'active' &&
        hadSession.current
      ) {
        void retryRestore();
      }
      previousState = state;
    });
    return () => {
      mounted.current = false;
      unsubscribe();
      subscription.remove();
    };
  }, [retryRestore]);

  return (
    <SessionContext.Provider
      value={{
        signedIn,
        loading,
        needsSignIn,
        restoreError,
        appKey,
        retryRestore,
        signIn: async (email, password) => {
          const version = ++lifecycle.current;
          await auth.signIn(email, password);
          await acceptSession(version);
        },
        signUp: async (email, password, name) => {
          const version = ++lifecycle.current;
          await auth.register(email, password, name);
          await acceptSession(version);
        },
        signOut: async () => {
          const version = ++lifecycle.current;
          await auth.signOut();
          if (version !== lifecycle.current) return;
          setLoading(false);
          hadSession.current = false;
          userId.current = null;
          setSignedIn(false);
          setNeedsSignIn(false);
          setRestoreError(false);
          setAppKey((key) => key + 1);
        },
      }}
    >
      {children}
    </SessionContext.Provider>
  );
}

export function useSession() {
  const session = useContext(SessionContext);
  if (!session) throw new Error('useSession requires SessionProvider.');
  return session;
}
