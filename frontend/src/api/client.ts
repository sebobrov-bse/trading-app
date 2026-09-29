const BASE_URL = '/api/v1';

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(`API error ${status}: ${detail}`);
  }
}

async function parseError(response: Response): Promise<string> {
  try {
    const data = await response.json();
    if (typeof data.detail === 'string') return data.detail;
    return JSON.stringify(data.detail ?? data);
  } catch {
    return response.statusText || 'Unknown error';
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`);
  if (!response.ok) {
    throw new ApiError(response.status, await parseError(response));
  }
  return response.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new ApiError(response.status, await parseError(response));
  }
  return response.json() as Promise<T>;
}

export async function apiDelete(path: string): Promise<void> {
  const response = await fetch(`${BASE_URL}${path}`, { method: 'DELETE' });
  if (!response.ok) {
    throw new ApiError(response.status, await parseError(response));
  }
}