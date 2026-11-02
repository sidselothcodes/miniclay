import { EnrichmentResult } from './types';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export async function enrichSingle(domain: string, sellerContext: string): Promise<EnrichmentResult> {
  const response = await fetch(`${API_BASE}/api/enrich-single`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ domain, seller_context: sellerContext }),
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  return response.json();
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Clipboard API is unavailable on plain http.
    const area = document.createElement('textarea');
    area.value = text;
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(area);
    return ok;
  }
}
