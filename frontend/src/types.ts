export interface DecisionMaker {
  full_name: string;
  role: string;
  linkedin_url: string;
  work_email: string;
  email_status: 'MX Verified' | 'Pattern Inferred' | 'No MX Records' | 'Unknown';
  source?: 'linkedin' | 'web' | 'knowledge' | 'reference' | 'none' | '';
}

export interface EnrichmentResult {
  domain: string;
  company_name: string | null;
  product_and_icp: string | null;
  gtm_motion: string | null;
  pricing_tier_summary: string | null;
  tech_and_live_signals: string[];
  fit_tier?: 'Strong Fit' | 'Moderate Fit' | 'Low Fit' | null;
  fit_reason?: string | null;
  decision_maker: DecisionMaker | null;
  ai_outreach: string | null;
  email_alternates?: string[];
  status: 'success' | 'error' | 'loading';
  error?: string | null;
}
