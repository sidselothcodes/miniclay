import React from 'react';
import { EnrichmentResult } from '../types';
import LoadingRow from './LoadingRow';

interface EnrichmentTableProps {
  results: EnrichmentResult[];
}

const INDUSTRY_COLORS: Record<string, { bg: string; text: string }> = {
  'fintech': { bg: '#FEF0E8', text: '#FB7232' },
  'payments': { bg: '#FEF0E8', text: '#FB7232' },
  'devtools': { bg: '#EFF6FF', text: '#3B82F6' },
  'developer tools': { bg: '#EFF6FF', text: '#3B82F6' },
  'ai/ml': { bg: '#F3E8FF', text: '#9333EA' },
  'ai': { bg: '#F3E8FF', text: '#9333EA' },
  'saas': { bg: '#ECFDF5', text: '#059669' },
  'healthcare': { bg: '#F0FDFA', text: '#0D9488' },
  'e-commerce': { bg: '#FDF2F8', text: '#DB2777' },
  'ecommerce': { bg: '#FDF2F8', text: '#DB2777' },
};

const SIZE_COLORS: Record<string, { bg: string; text: string }> = {
  'startup': { bg: '#ECFDF5', text: '#059669' },
  'mid-market': { bg: '#EFF6FF', text: '#3B82F6' },
  'enterprise': { bg: '#F3E8FF', text: '#9333EA' },
  'unknown': { bg: '#F3F4F6', text: '#6B7280' },
};

function getIndustryStyle(industry: string | null) {
  if (!industry) return { bg: '#F3F4F6', text: '#6B7280' };
  const key = industry.toLowerCase().split('/')[0].trim();
  for (const [k, v] of Object.entries(INDUSTRY_COLORS)) {
    if (key.includes(k) || k.includes(key)) return v;
  }
  return { bg: '#F3F4F6', text: '#6B7280' };
}

function getSizeStyle(size: string | null) {
  if (!size) return SIZE_COLORS['unknown'];
  return SIZE_COLORS[size.toLowerCase()] || SIZE_COLORS['unknown'];
}

const SOURCE_LABELS: Record<string, string> = {
  'website': 'Website \u2713',
  'github': 'GitHub \u2713',
  'ai_knowledge': 'AI \u2713',
};

const EnrichmentTable: React.FC<EnrichmentTableProps> = ({ results }) => {
  if (results.length === 0) return null;

  return (
    <div className="table-container">
      <table className="enrichment-table">
        <thead>
          <tr>
            <th className="table-header" style={{ width: 140 }}>DOMAIN</th>
            <th className="table-header" style={{ width: 130 }}>COMPANY</th>
            <th className="table-header" style={{ width: 220 }}>DESCRIPTION</th>
            <th className="table-header" style={{ width: 120 }}>INDUSTRY</th>
            <th className="table-header" style={{ width: 100 }}>SIZE</th>
            <th className="table-header">AI OUTREACH</th>
            <th className="table-header" style={{ width: 140 }}>SOURCES</th>
          </tr>
        </thead>
        <tbody>
          {results.map((result) => {
            if (result.status === 'loading') {
              return <LoadingRow key={result.domain} domain={result.domain} />;
            }

            if (result.status === 'error') {
              return (
                <tr key={result.domain} className="table-row error-row">
                  <td className="table-cell cell-domain">
                    <span className="domain-icon">🌐</span>
                    {result.domain}
                  </td>
                  <td className="table-cell" colSpan={6}>
                    <span className="error-message">
                      ⚠ Could not enrich — {result.error || 'website unreachable'}
                    </span>
                  </td>
                </tr>
              );
            }

            const industryStyle = getIndustryStyle(result.industry);
            const sizeStyle = getSizeStyle(result.companySize);

            return (
              <tr key={result.domain} className="table-row fade-in">
                <td className="table-cell cell-domain">
                  <span className="domain-icon">🌐</span>
                  {result.domain}
                </td>
                <td className="table-cell cell-company">{result.companyName}</td>
                <td className="table-cell cell-description">{result.description}</td>
                <td className="table-cell">
                  <span
                    className="pill"
                    style={{ backgroundColor: industryStyle.bg, color: industryStyle.text }}
                  >
                    {result.industry}
                  </span>
                </td>
                <td className="table-cell">
                  <span
                    className="pill"
                    style={{ backgroundColor: sizeStyle.bg, color: sizeStyle.text }}
                  >
                    {result.companySize}
                  </span>
                </td>
                <td className="table-cell cell-outreach">{result.outreachLine}</td>
                <td className="table-cell">
                  <div className="source-badges">
                    {(result.sources || []).map((src) => (
                      <span key={src} className="source-badge">
                        {SOURCE_LABELS[src] || src}
                      </span>
                    ))}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

export default EnrichmentTable;
