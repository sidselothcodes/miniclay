export interface EnrichmentResult {
  domain: string;
  companyName: string | null;
  description: string | null;
  industry: string | null;
  companySize: string | null;
  outreachLine: string | null;
  status: 'success' | 'error' | 'loading';
  error?: string;
}
