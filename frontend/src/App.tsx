import { useEffect, useState } from 'react';
import InputSection from './components/InputSection';
import EnrichmentTable from './components/EnrichmentTable';
import Footer from './components/Footer';
import { enrichSingle } from './api';
import { EnrichmentResult } from './types';
import seedRows from './data/seed.json';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const DEFAULT_DOMAINS = 'stripe.com\nnotion.so\nvercel.com\nlinear.app\nramp.com';
const DEFAULT_SELLER_CONTEXT =
  'We build an automated LLM evaluation and observability engine that catches hallucinations, retrieval regressions, and latency spikes in production AI workflows.';
const MAX_DOMAINS = 25;
const CONCURRENCY = 4;

const SEED = seedRows as EnrichmentResult[];

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
    sources_used: [],
    status: 'loading',
  };
}

function App() {
  const [input, setInput] = useState(DEFAULT_DOMAINS);
  const [sellerContext, setSellerContext] = useState(DEFAULT_SELLER_CONTEXT);
  // Pre-loaded rows for the default domains, so the table is populated on first paint.
  const [results, setResults] = useState<EnrichmentResult[]>(SEED);
  const [showingSnapshot, setShowingSnapshot] = useState(SEED.length > 0);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/api/health`).catch(() => {});
  }, []);

  const handleEnrich = async () => {
    const domains = parseDomains(input).slice(0, MAX_DOMAINS);
    if (domains.length === 0) return;

    setIsLoading(true);
    setShowingSnapshot(false);
    setResults(domains.map(loadingRow));

    const update = (index: number, row: EnrichmentResult) =>
      setResults((prev) => prev.map((r, i) => (i === index ? row : r)));

    // Small worker pool: rows fill in as soon as each domain finishes.
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

  const snapshotDate = SEED[0]?.snapshot_date;

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

      {showingSnapshot && (
        <p className="table-note">
          <span className="table-note-dot" />
          Pre-loaded snapshot{snapshotDate ? ` · researched ${formatDate(snapshotDate)}` : ''} · hit Enrich → to run the
          live pipeline
        </p>
      )}

      <EnrichmentTable results={results} />

      <Footer />
    </div>
  );
}

function formatDate(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

export default App;
