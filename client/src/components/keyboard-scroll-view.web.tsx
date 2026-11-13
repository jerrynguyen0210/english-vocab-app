import {
  forwardRef,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ComponentRef,
} from 'react';
import { ScrollView, type ScrollViewProps } from 'react-native';

type ScrollHandle = ComponentRef<typeof ScrollView>;

export const KeyboardScrollView = forwardRef<ScrollHandle, ScrollViewProps>(
  function KeyboardScrollView(
    { style, onFocusCapture, onLayout, ...props },
    ref,
  ) {
    const scroll = useRef<ScrollHandle | null>(null);
    const frame = useRef<number | null>(null);
    const [maxHeight, setMaxHeight] = useState<number>();

    const revealInput = useCallback(() => {
      if (frame.current !== null) cancelAnimationFrame(frame.current);
      frame.current = requestAnimationFrame(() => {
        frame.current = null;
        const container = scroll.current as unknown as HTMLElement | null;
        const input = document.activeElement;
        if (
          !container ||
          !(input instanceof HTMLElement) ||
          !container.contains(input) ||
          !input.matches('input, textarea, [contenteditable="true"]')
        )
          return;
        const viewport = window.visualViewport;
        const bounds = container.getBoundingClientRect();
        const viewportBottom = viewport
          ? viewport.offsetTop + viewport.height
          : window.innerHeight;
        // Mobile browsers can shrink only the visual viewport, leaving the
        // page and its scroll container behind the on-screen keyboard.
        setMaxHeight(
          viewport && viewport.height < window.innerHeight - 1
            ? Math.max(0, viewportBottom - bounds.top - 16)
            : undefined,
        );
        const inputBounds = input.getBoundingClientRect();
        const bottom = Math.min(bounds.bottom, viewportBottom) - 16;
        const top = Math.max(bounds.top, viewport?.offsetTop ?? 0) + 16;
        const delta =
          inputBounds.bottom > bottom
            ? inputBounds.bottom - bottom
            : inputBounds.top < top
              ? inputBounds.top - top
              : 0;
        if (delta !== 0) container.scrollTop += delta;
      });
    }, []);

    // Retry after the container shrinks so the browser can scroll through the
    // newly available content instead of clamping to its previous scroll range.
    useLayoutEffect(() => {
      if (maxHeight !== undefined) revealInput();
    }, [maxHeight, revealInput]);

    useEffect(() => {
      const viewport = window.visualViewport;
      const resize = () => {
        if (!viewport || viewport.height >= window.innerHeight - 1)
          setMaxHeight(undefined);
        revealInput();
      };
      viewport?.addEventListener('resize', resize);
      viewport?.addEventListener('scroll', revealInput);
      window.addEventListener('resize', resize);
      return () => {
        viewport?.removeEventListener('resize', resize);
        viewport?.removeEventListener('scroll', revealInput);
        window.removeEventListener('resize', resize);
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
        style={[style, maxHeight === undefined ? undefined : { maxHeight }]}
        keyboardShouldPersistTaps="handled"
        onFocusCapture={(event) => {
          onFocusCapture?.(event);
          revealInput();
        }}
        onLayout={(event) => {
          onLayout?.(event);
          revealInput();
        }}
      />
    );
  },
);
