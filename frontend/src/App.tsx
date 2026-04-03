import { useEffect, useState } from 'react';
import InputSection from './components/InputSection';
import EnrichmentTable from './components/EnrichmentTable';
import Footer from './components/Footer';
import { enrichSingle } from './api';
import { EnrichmentResult } from './types';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const DEFAULT_DOMAINS = 'stripe.com\nnotion.so\nvercel.com\nlinear.app\nramp.com';

function App() {
  const [input, setInput] = useState(DEFAULT_DOMAINS);
  const [results, setResults] = useState<EnrichmentResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/api/health`).catch(() => {});
  }, []);

  const handleEnrich = async () => {
    const domains = input
      .split('\n')
      .map((d) => d.trim())
      .filter((d) => d.length > 0)
      .slice(0, 5);

    if (domains.length === 0) return;

    setIsLoading(true);

    const initialResults: EnrichmentResult[] = domains.map((domain) => ({
      domain,
      companyName: null,
      description: null,
      industry: null,
      companySize: null,
      outreachLine: null,
      status: 'loading',
    }));
    setResults(initialResults);

    for (let i = 0; i < domains.length; i++) {
      try {
        const result = await enrichSingle(domains[i]);
        setResults((prev) =>
          prev.map((r) => (r.domain === domains[i] ? { ...result, status: result.status || 'success' } : r))
        );
      } catch {
        setResults((prev) =>
          prev.map((r) =>
            r.domain === domains[i]
              ? { ...r, status: 'error', error: 'Request failed — check your connection' }
              : r
          )
        );
      }

      if (i < domains.length - 1) {
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
    }

    setIsLoading(false);
  };

  return (
    <div className="app">
      <header className="header">
        <h1 className="header-title">MiniClay</h1>
        <p className="header-subtitle">AI-powered lead enrichment in seconds</p>
      </header>

      <InputSection
        value={input}
        onChange={setInput}
        onEnrich={handleEnrich}
        isLoading={isLoading}
      />

      <EnrichmentTable results={results} />

      <Footer />
    </div>
  );
}

export default App;
