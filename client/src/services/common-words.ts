export type CommonWordQuestion = {
  id: string;
  word: string;
  partOfSpeech: string;
  explanation: string;
  example: string;
  choices: readonly [string, string, string, string];
  correctIndex: number;
};

// UI fixtures only. Replace this loader when the question-bank API is ready.
// Answer validation here is for sample practice, not scheduled Review scoring.
const sampleQuestions: readonly CommonWordQuestion[] = [
  {
    id: 'reliable',
    word: 'reliable',
    partOfSpeech: 'adjective',
    explanation: 'Someone or something you can depend on.',
    example: 'She is a reliable colleague.',
    choices: [
      'Easy to forget',
      'Able to be trusted',
      'Very expensive',
      'Difficult to understand',
    ],
    correctIndex: 1,
  },
  {
    id: 'eager',
    word: 'eager',
    partOfSpeech: 'adjective',
    explanation: 'Very interested and excited about doing something.',
    example: 'He was eager to learn more.',
    choices: [
      'Ready and excited',
      'Quiet and tired',
      'Hard to find',
      'Unwilling to help',
    ],
    correctIndex: 0,
  },
  {
    id: 'afford',
    word: 'afford',
    partOfSpeech: 'verb',
    explanation: 'To have enough money or time for something.',
    example: 'We can afford a short holiday this year.',
    choices: [
      'To give something away',
      'To refuse an offer',
      'To have enough to pay',
      'To borrow from someone',
    ],
    correctIndex: 2,
  },
  {
    id: 'brief',
    word: 'brief',
    partOfSpeech: 'adjective',
    explanation: 'Lasting only a short time.',
    example: 'We had a brief conversation before work.',
    choices: [
      'Very noisy',
      'Full of detail',
      'Difficult to follow',
      'Short in duration',
    ],
    correctIndex: 3,
  },
  {
    id: 'notice',
    word: 'notice',
    partOfSpeech: 'verb',
    explanation: 'To become aware of something by seeing or hearing it.',
    example: 'Did you notice the new sign?',
    choices: [
      'To pay for something',
      'To become aware of something',
      'To hide an object',
      'To make a promise',
    ],
    correctIndex: 1,
  },
  {
    id: 'patient',
    word: 'patient',
    partOfSpeech: 'adjective',
    explanation: 'Able to wait calmly without becoming annoyed.',
    example: 'Thank you for being patient while we fix the problem.',
    choices: [
      'Able to wait calmly',
      'Always in a hurry',
      'Feeling very hungry',
      'Unable to decide',
    ],
    correctIndex: 0,
  },
  {
    id: 'improve',
    word: 'improve',
    partOfSpeech: 'verb',
    explanation: 'To become better, or to make something better.',
    example: 'Daily practice will improve your English.',
    choices: [
      'To start again',
      'To stay the same',
      'To make or become better',
      'To move away',
    ],
    correctIndex: 2,
  },
  {
    id: 'essential',
    word: 'essential',
    partOfSpeech: 'adjective',
    explanation: 'Completely necessary or very important.',
    example: 'Water is essential for life.',
    choices: [
      'Easy to replace',
      'Rarely used',
      'Pleasant to look at',
      'Absolutely necessary',
    ],
    correctIndex: 3,
  },
  {
    id: 'consider',
    word: 'consider',
    partOfSpeech: 'verb',
    explanation: 'To think carefully about something before deciding.',
    example: 'Please consider all the options.',
    choices: [
      'To think carefully about',
      'To finish immediately',
      'To copy exactly',
      'To forget completely',
    ],
    correctIndex: 0,
  },
  {
    id: 'grateful',
    word: 'grateful',
    partOfSpeech: 'adjective',
    explanation: 'Feeling or showing thanks for something.',
    example: 'I am grateful for your help.',
    choices: [
      'Feeling disappointed',
      'Feeling thankful',
      'Being uncertain',
      'Being very busy',
    ],
    correctIndex: 1,
  },
];

export async function loadCommonWords(): Promise<
  readonly CommonWordQuestion[]
> {
  return sampleQuestions;
}
