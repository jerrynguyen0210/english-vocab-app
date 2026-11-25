import { authenticatedFetch } from '@/services/auth';

export type TeacherGender = 'male' | 'female';
export type Teacher = {
  id: string;
  name: string;
  model: string;
  gender: TeacherGender;
};
export type TeacherOptions = {
  teachers: Teacher[];
  selected_teacher_id: string | null;
};

export class TeacherSelectionError extends Error {}

export async function loadTeachers(
  signal: AbortSignal,
): Promise<TeacherOptions> {
  const response = await authenticatedFetch('/teachers', { signal });
  if (!response.ok)
    throw new TeacherSelectionError(
      'Unable to load teachers. Please try again.',
    );
  const data: unknown = await response.json();
  if (!data || typeof data !== 'object') throw new Error('Invalid teachers');
  const { teachers, selected_teacher_id } = data as TeacherOptions;
  if (
    !Array.isArray(teachers) ||
    !teachers.every(
      (teacher) =>
        teacher &&
        typeof teacher.id === 'string' &&
        teacher.id.trim().length > 0 &&
        typeof teacher.name === 'string' &&
        teacher.name.trim().length > 0 &&
        typeof teacher.model === 'string' &&
        teacher.model.trim().length > 0 &&
        (teacher.gender === 'male' || teacher.gender === 'female'),
    ) ||
    new Set(teachers.map(({ id }) => id)).size !== teachers.length ||
    (selected_teacher_id !== null &&
      !teachers.some(({ id }) => id === selected_teacher_id))
  )
    throw new Error('Invalid teachers');
  return { teachers, selected_teacher_id };
}

export async function saveTeacher(
  teacherId: string,
  signal: AbortSignal,
): Promise<string> {
  const response = await authenticatedFetch('/teachers/selection', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ teacher_id: teacherId }),
    signal,
  });
  if (!response.ok)
    throw new TeacherSelectionError(
      'Unable to save your teacher. Please try again.',
    );
  const data: unknown = await response.json();
  if (
    !data ||
    typeof data !== 'object' ||
    !('teacher_id' in data) ||
    data.teacher_id !== teacherId
  )
    throw new Error('Invalid teacher selection');
  return teacherId;
}
