import {
  createContext,
  useContext,
  useEffect,
  useState,
  type PropsWithChildren,
} from 'react';
import * as auth from '@/services/auth';

const SessionContext = createContext<{
  signedIn: boolean;
  loading: boolean;
  signIn: typeof auth.signIn;
  signUp: typeof auth.register;
  signOut: typeof auth.signOut;
} | null>(null);

export function SessionProvider({ children }: PropsWithChildren) {
  const [signedIn, setSignedIn] = useState(false);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    auth
      .refreshSession()
      .then(
        () => {
          if (active) setSignedIn(true);
        },
        () => {
          if (active) setSignedIn(false);
        },
      )
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);
  return (
    <SessionContext.Provider
      value={{
        signedIn,
        loading,
        signIn: async (email, password) => {
          await auth.signIn(email, password);
          setSignedIn(true);
        },
        signUp: async (email, password, name) => {
          await auth.register(email, password, name);
          setSignedIn(true);
        },
        signOut: async () => {
          await auth.signOut();
          setSignedIn(false);
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
