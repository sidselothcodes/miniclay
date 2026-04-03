export interface EnrichmentResult {
  domain: string;
  companyName: string | null;
  description: string | null;
  industry: string | null;
  companySize: string | null;
  outreachLine: string | null;
  sources?: string[];
  status: 'success' | 'error' | 'loading';
  error?: string;
}
