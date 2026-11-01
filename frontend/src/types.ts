export interface DecisionMaker {
  full_name: string;
  role: string;
  linkedin_url: string;
  work_email: string;
  email_status: string; // "MX Verified" | "Pattern Inferred" | "No MX Records" | "Unknown"
}

export type SourceName = 'Website' | 'Pricing' | 'GitHub' | 'News' | 'LinkedIn';

export interface EnrichmentResult {
  domain: string;
  company_name: string | null;
  product_and_icp: string | null;
  gtm_motion: string | null;
  pricing_tier_summary: string | null;
  tech_and_live_signals: string[];
  decision_maker: DecisionMaker | null;
  ai_outreach: string | null;
  sources_used: string[];
  source_urls?: Record<string, string[]>;
  email_alternates?: string[];
  fallbacks?: string[];
  generated_by?: string;
  cached?: boolean;
  snapshot_date?: string | null;
  status: 'success' | 'error' | 'loading';
  error?: string | null;
}
