// Central API URL config — reads from environment variable in production
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function apiFetch(path: string, options?: RequestInit) {
  const url = `${API_BASE_URL}${path}`;
  const res = await fetch(url, {
    ...options,
    credentials: 'include', // Mandatory for cross-domain cookies
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error(error.message || 'API request failed');
  }
  return res.json();
}

export const api = {
  auth: {
    me: () => apiFetch('/api/auth/me'),
    google: (token: string) => apiFetch('/api/auth/google', {
      method: 'POST',
      body: JSON.stringify({ token }),
    }),
    register: (data: any) => apiFetch('/api/register', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
    login: (data: any) => apiFetch('/api/login', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
    logout: () => apiFetch('/api/auth/logout', { method: 'POST' }),
  },
  dashboard: {
    stats: () => apiFetch('/api/dashboard/stats'),
  },
  onboarding: {
    syncLinkedin: () => apiFetch('/api/onboarding/sync-linkedin'),
    confirmLinkedin: (url: string) => apiFetch('/api/onboarding/confirm-linkedin', {
      method: 'POST',
      body: JSON.stringify({ url }),
    }),
  },
  jobs: {
    list: () => apiFetch('/api/jobs'),
    updateStatus: (id: number, status: string) => apiFetch(`/api/jobs/${id}/status`, {
      method: 'POST',
      body: JSON.stringify({ status }),
    }),
  },
  coach: {
    chat: (message: string, voice: boolean) => apiFetch('/api/coach/chat', {
      method: 'POST',
      body: JSON.stringify({ message, voice }),
    }),
  },
};
