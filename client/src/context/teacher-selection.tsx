import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type PropsWithChildren,
} from 'react';
import {
  loadTeachers,
  saveTeacher,
  TeacherSelectionError,
  type TeacherOptions,
} from '@/services/teachers';
import { connectionMessage } from '@/services/connectivity';

const TeacherSelectionContext = createContext<{
  teachers: TeacherOptions['teachers'];
  teacherId: string | null;
  loading: boolean;
  saving: boolean;
  error: string;
  reload: () => void;
  selectTeacher: (id: string) => Promise<boolean>;
} | null>(null);

// Backend owns the options and selection. This provider only caches confirmed
// responses while the authenticated navigator is mounted.
export function TeacherSelectionProvider({ children }: PropsWithChildren) {
  const [options, setOptions] = useState<TeacherOptions>({
    teachers: [],
    selected_teacher_id: null,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const controller = useRef<AbortController | null>(null);
  const busy = useRef(false);

  useEffect(() => {
    const request = new AbortController();
    controller.current = request;
    void loadTeachers(request.signal)
      .then((result) => {
        if (!request.signal.aborted) setOptions(result);
      })
      .catch((cause: unknown) => {
        if (!request.signal.aborted)
          setError(
            connectionMessage(
              cause,
              'Unable to load teachers. Please try again.',
            ),
          );
      })
      .finally(() => {
        if (!request.signal.aborted) setLoading(false);
      });
    return () => request.abort();
  }, [revision]);

  async function selectTeacher(id: string): Promise<boolean> {
    const request = controller.current;
    if (
      !request ||
      request.signal.aborted ||
      busy.current ||
      loading ||
      !options.teachers.some((teacher) => teacher.id === id)
    )
      return false;
    busy.current = true;
    setSaving(true);
    setError('');
    try {
      const teacherId = await saveTeacher(id, request.signal);
      if (request.signal.aborted) return false;
      setOptions((previous) => ({
        ...previous,
        selected_teacher_id: teacherId,
      }));
      return true;
    } catch (cause) {
      if (!request.signal.aborted)
        setError(
          connectionMessage(
            cause,
            cause instanceof TeacherSelectionError
              ? cause.message
              : 'Unable to save your teacher. Please try again.',
          ),
        );
      return false;
    } finally {
      busy.current = false;
      if (!request.signal.aborted) setSaving(false);
    }
  }

  return (
    <TeacherSelectionContext.Provider
      value={{
        teachers: options.teachers,
        teacherId: options.selected_teacher_id,
        loading,
        saving,
        error,
        reload: () => {
          if (busy.current) return;
          setLoading(true);
          setError('');
          setRevision((value) => value + 1);
        },
        selectTeacher,
      }}
    >
      {children}
    </TeacherSelectionContext.Provider>
  );
}

export function useTeacherSelection() {
  const selection = useContext(TeacherSelectionContext);
  if (!selection)
    throw new Error('useTeacherSelection requires TeacherSelectionProvider.');
  return selection;
}

// Pronunciation can also be used outside the signed-in navigator, where the
// device default voice applies until a teacher is available.
export function useSelectedTeacher() {
  const selection = useContext(TeacherSelectionContext);
  if (selection?.loading) return undefined;
  return (
    selection?.teachers.find(({ id }) => id === selection.teacherId) ?? null
  );
}
