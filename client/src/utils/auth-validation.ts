export function validateName(name: string) {
  if (!name.trim()) return 'Enter your name.';
  if (Array.from(name.trim()).length > 100)
    return 'Use a name with 100 characters or fewer.';
  return undefined;
}

export function validateCredentials(email: string, password: string) {
  const errors: { email?: string; password?: string } = {};
  const normalizedEmail = email.trim();
  if (!normalizedEmail) errors.email = 'Enter your email address.';
  else if (
    normalizedEmail.length > 320 ||
    !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizedEmail)
  )
    errors.email = 'Enter a valid email address.';

  const length = Array.from(password).length;
  if (!password) errors.password = 'Enter your password.';
  else if (length < 12 || length > 128)
    errors.password = 'Use a password with 12–128 characters.';
  return errors;
}

export function authErrorMessage(status: number | undefined, signUp: boolean) {
  if (status === 401)
    return 'The email or password is incorrect. Please try again.';
  if (status === 409 && signUp)
    return 'Unable to create an account with this email. Try signing in instead.';
  if (status === 429)
    return 'Too many attempts. Please wait a few minutes and try again.';
  if (status === 422) return 'Check your email and password, then try again.';
  if (status === 403)
    return 'This request was not allowed. Please try again later.';
  if (status !== undefined && status >= 500)
    return 'The service is temporarily unavailable. Please try again later.';
  return 'Unable to connect. Check your connection and try again.';
}
