import { useCallback, useRef, useState } from 'react';
import { useFocusEffect } from 'expo-router';
import * as Speech from 'expo-speech';
import { SymbolView } from 'expo-symbols';
import { Pressable, StyleSheet, View } from 'react-native';
import { ThemedText } from '@/components/themed-text';
import { WordwellColors as colors } from '@/constants/wordwell-theme';

export function PronunciationButton({
  word,
  active,
  autoSpeak = false,
}: {
  word: string;
  active: boolean;
  autoSpeak?: boolean;
}) {
  const [speaking, setSpeaking] = useState(false);
  const [error, setError] = useState('');
  const pending = useRef(false);
  const session = useRef(0);

  const pronounce = useCallback(async () => {
    if (!active || pending.current) return;
    const current = session.current;
    pending.current = true;
    setSpeaking(true);
    setError('');
    const finish = (failed = false) => {
      if (session.current !== current) return;
      pending.current = false;
      setSpeaking(false);
      if (failed) setError('Could not play pronunciation. Please try again.');
    };
    try {
      await Speech.stop();
      if (session.current !== current) return;
      Speech.speak(word, {
        language: 'en-GB',
        onDone: () => finish(),
        onStopped: () => finish(),
        onError: () => finish(true),
      });
    } catch {
      finish(true);
    }
  }, [active, word]);

  useFocusEffect(
    useCallback(() => {
      setSpeaking(false);
      setError('');
      pending.current = false;
      if (!active || !word) return;
      if (autoSpeak) void pronounce();
      return () => {
        session.current += 1;
        pending.current = false;
        void Speech.stop().catch(() => {});
      };
    }, [word, active, autoSpeak, pronounce]),
  );

  return (
    <View style={styles.container}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`Play pronunciation of ${word}`}
        accessibilityHint="Reads the word aloud in English"
        accessibilityState={{ disabled: !active || speaking, busy: speaking }}
        disabled={!active || speaking}
        onPress={() => void pronounce()}
        style={({ pressed }) => [
          styles.button,
          (pressed || speaking) && styles.pressed,
        ]}
      >
        <SymbolView
          name={{
            ios: 'speaker.wave.2.fill',
            android: 'volume_up',
            web: 'volume_up',
          }}
          size={26}
          tintColor={colors.primary}
        />
      </Pressable>
      {!!error && (
        <ThemedText accessibilityRole="alert" style={styles.error}>
          {error}
        </ThemedText>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { alignSelf: 'center', flexShrink: 1 },
  button: {
    width: 44,
    height: 44,
    borderRadius: 12,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pressed: { opacity: 0.6 },
  error: { color: colors.error, fontSize: 12, lineHeight: 18 },
});
