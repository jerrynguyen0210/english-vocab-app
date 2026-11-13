import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { Keyboard, TextInput, type KeyboardEvent } from 'react-native';
import { KeyboardScrollView } from '@/components/keyboard-scroll-view';
import { KeyboardScrollView as WebScrollView } from '@/components/keyboard-scroll-view.web';

const mockScroll = { measureInWindow: jest.fn(), scrollTo: jest.fn() };
jest.mock('react-native/Libraries/Components/ScrollView/ScrollView', () => {
  const React = require('react');
  const { View } = require('react-native');
  return {
    __esModule: true,
    default: React.forwardRef((props: object, ref: React.Ref<unknown>) => {
      React.useImperativeHandle(ref, () => mockScroll);
      return <View {...props} />;
    }),
  };
});

const input = { measureInWindow: jest.fn() };
const subscriptions = new Map<string, () => void>();
const removed = jest.fn();
async function settle() {
  await act(async () => {
    jest.advanceTimersByTime(20);
  });
}
async function focus() {
  await fireEvent(screen.getByTestId('scroll'), 'focus', {});
  await settle();
}

beforeEach(() => {
  jest.useFakeTimers();
  mockScroll.scrollTo.mockReset();
  mockScroll.measureInWindow.mockImplementation((callback) =>
    callback(0, 80, 360, 350),
  );
  input.measureInWindow.mockImplementation((callback) =>
    callback(0, 500, 300, 50),
  );
  jest
    .spyOn(TextInput.State, 'currentlyFocusedInput')
    .mockReturnValue(input as never);
  jest
    .spyOn(Keyboard, 'metrics')
    .mockReturnValue({ screenY: 500 } as KeyboardEvent['endCoordinates']);
  jest.spyOn(Keyboard, 'addListener').mockImplementation((event, callback) => {
    subscriptions.set(event, callback as () => void);
    return { remove: removed };
  });
  removed.mockClear();
});
afterEach(() => {
  jest.restoreAllMocks();
  subscriptions.clear();
  jest.useRealTimers();
});

test('keeps the focused field above the scroll boundary, including the navigation footer', async () => {
  const ref = React.createRef<React.ComponentRef<typeof KeyboardScrollView>>();
  await render(<KeyboardScrollView ref={ref} testID="scroll" />);
  await fireEvent.scroll(screen.getByTestId('scroll'), {
    nativeEvent: { contentOffset: { y: 100 } },
  });
  await focus();
  expect(mockScroll.scrollTo).toHaveBeenLastCalledWith({
    y: 236,
    animated: true,
  });
  expect(ref.current).toBe(mockScroll);
});

test('rechecks keyboard size changes and focus changes without another keyboard show event', async () => {
  await render(<KeyboardScrollView testID="scroll" />);
  await focus();
  mockScroll.measureInWindow.mockImplementation((callback) =>
    callback(0, 80, 360, 600),
  );
  await act(async () => {
    subscriptions.get('keyboardDidChangeFrame')?.();
  });
  await settle();
  expect(mockScroll.scrollTo).toHaveBeenLastCalledWith({
    y: 66,
    animated: true,
  });
  input.measureInWindow.mockImplementation((callback) =>
    callback(0, 300, 300, 50),
  );
  mockScroll.scrollTo.mockClear();
  await focus();
  expect(mockScroll.scrollTo).not.toHaveBeenCalled();
});

test('does not scroll an unfocused screen when a keyboard opens in another screen or modal', async () => {
  await render(<KeyboardScrollView testID="scroll" />);
  await act(async () => {
    subscriptions.get('keyboardDidShow')?.();
  });
  await settle();
  expect(mockScroll.scrollTo).not.toHaveBeenCalled();
});

test('removes keyboard listeners and cancels pending work on unmount', async () => {
  const view = await render(<KeyboardScrollView testID="scroll" />);
  await fireEvent(screen.getByTestId('scroll'), 'focus', {});
  await view.unmount();
  await settle();
  expect(removed).toHaveBeenCalledTimes(2);
  expect(mockScroll.scrollTo).not.toHaveBeenCalled();
});

// Exercise the browser implementation against visual-viewport changes without
// requiring a real on-screen keyboard in the component test environment.
test('mobile web shrinks its scroll area, reveals the field, and restores after keyboard dismissal', async () => {
  const names = ['window', 'document', 'HTMLElement'] as const;
  const original = names.map((name) =>
    Object.getOwnPropertyDescriptor(globalThis, name),
  );
  const viewport = Object.assign(new EventTarget(), {
    height: 400,
    offsetTop: 0,
  });
  const browser = Object.assign(new EventTarget(), {
    innerHeight: 800,
    visualViewport: viewport,
  });
  class Element {
    getBoundingClientRect() {
      return { top: 500, bottom: 550 };
    }
    matches() {
      return true;
    }
  }
  const field = new Element();
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: browser,
  });
  Object.defineProperty(globalThis, 'document', {
    configurable: true,
    value: { activeElement: field },
  });
  Object.defineProperty(globalThis, 'HTMLElement', {
    configurable: true,
    value: Element,
  });
  const browserScroll = Object.assign(mockScroll, {
    contains: (node: unknown) => node === field,
    getBoundingClientRect: () => ({ top: 80, bottom: 700 }),
    scrollTop: 0,
  });
  const view = await render(<WebScrollView testID="scroll" />);
  try {
    await fireEvent(screen.getByTestId('scroll'), 'focusCapture', {});
    await settle();
    expect(screen.getByTestId('scroll')).toHaveStyle({ maxHeight: 304 });
    expect(browserScroll.scrollTop).toBe(166);
    // Let the post-layout retry settle using the field's new visible position.
    field.getBoundingClientRect = () => ({ top: 300, bottom: 350 });
    await settle();
    expect(browserScroll.scrollTop).toBe(166);
    viewport.height = 800;
    await act(async () => {
      viewport.dispatchEvent(new Event('resize'));
    });
    await settle();
    expect(screen.getByTestId('scroll').props.style[1]).toBeUndefined();
  } finally {
    await view.unmount();
    names.forEach((name, index) => {
      const descriptor = original[index];
      if (descriptor) Object.defineProperty(globalThis, name, descriptor);
      else Reflect.deleteProperty(globalThis, name);
    });
  }
});
