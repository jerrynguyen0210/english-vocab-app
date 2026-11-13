import {
  forwardRef,
  useCallback,
  useEffect,
  useRef,
  type ComponentRef,
} from 'react';
import {
  Keyboard,
  ScrollView,
  TextInput,
  type ScrollViewProps,
} from 'react-native';

type ScrollHandle = ComponentRef<typeof ScrollView>;

// The surrounding screen handles keyboard resizing. This also handles switching
// fields while the keyboard is already open, when no new show event is emitted.
export const KeyboardScrollView = forwardRef<ScrollHandle, ScrollViewProps>(
  function KeyboardScrollView({ onFocus, onLayout, onScroll, ...props }, ref) {
    const scroll = useRef<ScrollHandle | null>(null);
    const offset = useRef(0);
    const ownedInput =
      useRef<ReturnType<typeof TextInput.State.currentlyFocusedInput>>(null);
    const frame = useRef<ReturnType<typeof requestAnimationFrame> | null>(null);

    const revealInput = useCallback(() => {
      if (frame.current !== null) cancelAnimationFrame(frame.current);
      frame.current = requestAnimationFrame(() => {
        frame.current = null;
        const input = TextInput.State.currentlyFocusedInput();
        const container = scroll.current;
        if (!input || !container || input !== ownedInput.current) return;
        container.measureInWindow((_x, top, _width, height) => {
          input.measureInWindow(
            (_inputX, inputTop, _inputWidth, inputHeight) => {
              if (
                scroll.current !== container ||
                TextInput.State.currentlyFocusedInput() !== input
              )
                return;
              const keyboardTop = Keyboard.metrics()?.screenY ?? Infinity;
              const bottom = Math.min(top + height, keyboardTop) - 16;
              const delta =
                inputTop + inputHeight > bottom
                  ? inputTop + inputHeight - bottom
                  : inputTop < top + 16
                    ? inputTop - top - 16
                    : 0;
              if (delta !== 0)
                container.scrollTo({
                  y: Math.max(0, offset.current + delta),
                  animated: true,
                });
            },
          );
        });
      });
    }, []);

    useEffect(() => {
      const show = Keyboard.addListener('keyboardDidShow', revealInput);
      const change = Keyboard.addListener(
        'keyboardDidChangeFrame',
        revealInput,
      );
      return () => {
        show.remove();
        change.remove();
        if (frame.current !== null) cancelAnimationFrame(frame.current);
      };
    }, [revealInput]);

    return (
      <ScrollView
        {...props}
        ref={useCallback(
          (node: ScrollHandle | null) => {
            scroll.current = node;
            if (typeof ref === 'function') ref(node);
            else if (ref) ref.current = node;
          },
          [ref],
        )}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
        scrollEventThrottle={16}
        onFocus={(event) => {
          ownedInput.current = TextInput.State.currentlyFocusedInput();
          onFocus?.(event);
          revealInput();
        }}
        onLayout={(event) => {
          onLayout?.(event);
          revealInput();
        }}
        onScroll={(event) => {
          offset.current = event.nativeEvent.contentOffset.y;
          onScroll?.(event);
        }}
      />
    );
  },
);
