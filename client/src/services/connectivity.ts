export const CONNECTIVITY_MESSAGE =
  "You're offline or the server is unreachable. Check your connection and try again.";

export class ConnectivityError extends Error {
  constructor() {
    super(CONNECTIVITY_MESSAGE);
  }
}

/** R0 requires a server response. Never queue or automatically replay writes. */
export async function reachableFetch(
  url: string,
  init: RequestInit = {},
  timeoutMs = 15000,
): Promise<Response> {
  const controller = new AbortController();
  const cancel = () => controller.abort();
  init.signal?.addEventListener('abort', cancel, { once: true });
  if (init.signal?.aborted) cancel();
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const response = await Promise.race([
      fetch(url, { ...init, signal: controller.signal }),
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => {
          controller.abort();
          reject(new ConnectivityError());
        }, timeoutMs);
      }),
    ]);
    if ([502, 503, 504].includes(response.status))
      throw new ConnectivityError();
    return response;
  } catch (error) {
    if (init.signal?.aborted) throw error;
    throw new ConnectivityError();
  } finally {
    clearTimeout(timer);
    init.signal?.removeEventListener('abort', cancel);
  }
}

export function connectionMessage(error: unknown, fallback: string): string {
  return error instanceof ConnectivityError ? CONNECTIVITY_MESSAGE : fallback;
}
