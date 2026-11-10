import { Link, type Href } from 'expo-router';
import {
  forwardRef,
  type ComponentProps,
  type ComponentRef,
  type ReactNode,
} from 'react';
import {
  Platform,
  Pressable,
  type StyleProp,
  type ViewStyle,
} from 'react-native';

type TargetProps = ComponentProps<typeof Pressable> & {
  baseStyle: StyleProp<ViewStyle>;
  selected?: boolean;
};

// Keep Pressable's dynamic style inside the target: Router's Slot flattens the
// direct child's style and cannot merge a Pressable style callback.
const Target = forwardRef<ComponentRef<typeof Pressable>, TargetProps>(
  function Target(
    { baseStyle, selected, style, accessibilityState, ...props },
    ref,
  ) {
    return (
      <Pressable
        {...props}
        ref={ref}
        {...(Platform.OS === 'web' && selected
          ? { 'aria-current': 'page' as const }
          : {})}
        accessibilityState={{ ...accessibilityState, selected }}
        style={(state) => [
          baseStyle,
          typeof style === 'function' ? style(state) : style,
          state.pressed && { opacity: 0.7 },
        ]}
      />
    );
  },
);

export function NavigationLink({
  href,
  label,
  children,
  style,
  selected,
  replace = false,
}: {
  href: Href;
  label: string;
  children: ReactNode;
  style: StyleProp<ViewStyle>;
  selected?: boolean;
  replace?: boolean;
}) {
  return (
    <Link href={href} replace={replace} asChild>
      <Target accessibilityLabel={label} baseStyle={style} selected={selected}>
        {children}
      </Target>
    </Link>
  );
}
