import { Screen } from '@/components/screen';
import { ThemedText } from '@/components/themed-text';
export default function Page() {
  return (
    <Screen>
      <ThemedText type="title">Add word</ThemedText>
      <ThemedText>Your new words will go here.</ThemedText>
    </Screen>
  );
}
