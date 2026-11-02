import { useEffect, useState } from 'react';
import InputSection from './components/InputSection';
import EnrichmentTable from './components/EnrichmentTable';
import Footer from './components/Footer';
import { enrichSingle } from './api';
import { EnrichmentResult } from './types';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const DEFAULT_DOMAINS = 'vercel.com\nnotion.so\nsarvam.ai\nbolna.ai\nrazorpay.com';
const DEFAULT_SELLER_CONTEXT =
  'We build an automated LLM evaluation and observability engine that catches hallucinations, retrieval regressions, and latency spikes in production AI workflows.';
const MAX_DOMAINS = 25;
const CONCURRENCY = 4;

function normalizeDomain(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/^[a-z]+:\/\//, '')
    .replace(/^www\./, '')
    .split(/[/?#]/)[0];
}

function parseDomains(input: string): string[] {
  const seen = new Set<string>();
  for (const part of input.split(/[\n,\s]+/)) {
    const domain = normalizeDomain(part);
    if (domain) seen.add(domain);
  }
  return [...seen];
}

function loadingRow(domain: string): EnrichmentResult {
  return {
    domain,
    company_name: null,
    product_and_icp: null,
    gtm_motion: null,
    pricing_tier_summary: null,
    tech_and_live_signals: [],
    decision_maker: null,
    ai_outreach: null,
    status: 'loading',
  };
}

function App() {
  const [input, setInput] = useState(DEFAULT_DOMAINS);
  const [sellerContext, setSellerContext] = useState(DEFAULT_SELLER_CONTEXT);
  const [results, setResults] = useState<EnrichmentResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/api/health`).catch(() => {});
  }, []);

  const handleEnrich = async () => {
    const domains = parseDomains(input).slice(0, MAX_DOMAINS);
    if (domains.length === 0) return;

    setIsLoading(true);
    setResults(domains.map(loadingRow));

    const update = (index: number, row: EnrichmentResult) =>
      setResults((prev) => prev.map((r, i) => (i === index ? row : r)));

    let next = 0;
    const worker = async () => {
      while (next < domains.length) {
        const index = next++;
        try {
          const result = await enrichSingle(domains[index], sellerContext);
          update(index, { ...result, status: result.status || 'success' });
        } catch {
          update(index, { ...loadingRow(domains[index]), status: 'error', error: 'request failed — check your connection' });
        }
      }
    };
    await Promise.all(Array.from({ length: Math.min(CONCURRENCY, domains.length) }, worker));

    setIsLoading(false);
  };

  return (
    <div className="app">
      <header className="header">
        <h1 className="header-title">MiniClay</h1>
        <p className="header-subtitle">GTM intelligence &amp; outbound lead enrichment in seconds</p>
      </header>

      <InputSection
        value={input}
        onChange={setInput}
        sellerContext={sellerContext}
        onSellerContextChange={setSellerContext}
        onEnrich={handleEnrich}
        isLoading={isLoading}
        domainCount={parseDomains(input).length}
        maxDomains={MAX_DOMAINS}
      />

      <EnrichmentTable results={results} />

      <Footer />
    </div>
  );
}

export default App;
