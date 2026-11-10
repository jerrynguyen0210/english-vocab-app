import type { PropsWithChildren } from 'react';

export type WordFormProps = PropsWithChildren<{ onSubmit: () => void }>;

export function WordForm({ children }: WordFormProps) {
  return <>{children}</>;
}
