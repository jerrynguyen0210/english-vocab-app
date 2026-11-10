import type { AuthFormShellProps } from './auth-form-shell';

export function AuthFormShell({
  children,
  label,
  onSubmit,
}: AuthFormShellProps) {
  return (
    <form
      aria-label={label}
      autoComplete="on"
      method="post"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        onSubmit({
          name: String(data.get('name') ?? ''),
          email: String(data.get('email') ?? ''),
          password: String(data.get('password') ?? ''),
        });
      }}
      style={{ display: 'flex', flexDirection: 'column', margin: 0 }}
    >
      {children}
    </form>
  );
}
