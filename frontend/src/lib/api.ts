// Central API URL config — reads from environment variable in production
// Set NEXT_PUBLIC_API_URL in Vercel dashboard to your Railway backend URL
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function apiFetch(path: string, options?: RequestInit) {
  const url = `${API_BASE_URL}${path}`;
  const res = await fetch(url, {
    credentials: 'include',
    ...options,
  });
  return res;
}
