import { Screen } from '@/components/screen';
import { ThemedText } from '@/components/themed-text';
export default function Page() {
  return (
    <Screen>
      <ThemedText type="title">Review</ThemedText>
      <ThemedText>Your vocabulary review will go here.</ThemedText>
    </Screen>
  );
}
