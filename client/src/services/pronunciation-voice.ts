import type { Voice } from 'expo-speech';
import type { TeacherGender } from '@/services/teachers';

// Expo exposes voice names, languages and identifiers, but no gender metadata.
// Match explicit labels and known system voice names; never guess from order or
// alter pitch to simulate gender. Only use identifiers returned by the device.
const voiceNames: Record<TeacherGender, RegExp> = {
  female:
    /\b(female|samantha|victoria|karen|moira|tessa|fiona|zira|hazel|susan|sonia|jenny)\b/i,
  male: /\b(male|lee|daniel|alex|fred|david|george|james|ryan|guy)\b/i,
};

export function selectPronunciationVoice(
  voices: readonly Voice[],
  gender?: TeacherGender,
): Voice | undefined {
  const australianVoices = voices.filter((voice) =>
    /^en[-_]AU$/i.test(voice.language),
  );
  return (
    (gender
      ? australianVoices.find((voice) =>
          voiceNames[gender].test(`${voice.name} ${voice.identifier}`),
        )
      : undefined) ?? australianVoices[0]
  );
}
