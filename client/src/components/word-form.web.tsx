import type { WordFormProps } from './word-form';

export function WordForm({ children, onSubmit }: WordFormProps) {
  return (
    <form
      aria-label="Add a word"
      noValidate
      style={{ display: 'flex', flexDirection: 'column' }}
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
      onKeyDownCapture={(event) => {
        const target = event.target;
        if (
          (target instanceof HTMLInputElement ||
            target instanceof HTMLTextAreaElement) &&
          event.key === 'Enter' &&
          !event.shiftKey &&
          !event.nativeEvent.isComposing &&
          event.nativeEvent.keyCode !== 229
        ) {
          event.preventDefault();
          event.stopPropagation();
          if (!event.repeat) onSubmit();
        }
      }}
    >
      {children}
    </form>
  );
}
