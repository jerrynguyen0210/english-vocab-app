import { useCallback, useRef, useState } from 'react';
import { useFocusEffect } from 'expo-router';
import * as Speech from 'expo-speech';
import { SymbolView } from 'expo-symbols';
import { Pressable, StyleSheet, View } from 'react-native';
import { useSelectedTeacher } from '@/context/teacher-selection';
import { selectPronunciationVoice } from '@/services/pronunciation-voice';
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
  const teacher = useSelectedTeacher();
  const gender = teacher?.gender;
  const canSpeak = active && teacher !== undefined;
  const [speaking, setSpeaking] = useState(false);
  const [error, setError] = useState('');
  const pending = useRef(false);
  const session = useRef(0);

  const pronounce = useCallback(async () => {
    if (!canSpeak || pending.current) return;
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
      const voices = await Speech.getAvailableVoicesAsync().catch(() => []);
      if (session.current !== current) return;
      const voice = selectPronunciationVoice(voices, gender);
      Speech.speak(word, {
        language: 'en-AU',
        ...(voice ? { voice: voice.identifier } : {}),
        onDone: () => finish(),
        onStopped: () => finish(),
        onError: () => finish(true),
      });
    } catch {
      finish(true);
    }
  }, [canSpeak, word, gender]);

  useFocusEffect(
    useCallback(() => {
      setSpeaking(false);
      setError('');
      pending.current = false;
      if (!canSpeak || !word) return;
      if (autoSpeak) void pronounce();
      return () => {
        session.current += 1;
        pending.current = false;
        void Speech.stop().catch(() => {});
      };
    }, [word, canSpeak, autoSpeak, pronounce]),
  );

  return (
    <View style={styles.container}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`Play pronunciation of ${word}`}
        accessibilityHint="Reads the word aloud in Australian English"
        accessibilityState={{ disabled: !canSpeak || speaking, busy: speaking }}
        disabled={!canSpeak || speaking}
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
