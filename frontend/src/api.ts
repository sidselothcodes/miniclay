import { EnrichmentResult } from './types';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export async function enrichSingle(domain: string): Promise<EnrichmentResult> {
  const response = await fetch(`${API_BASE}/api/enrich-single`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ domain }),
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  return response.json();
}
