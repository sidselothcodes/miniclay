import React from 'react';
import { DecisionMaker, EnrichmentResult } from '../types';
import CopyButton from './CopyButton';
import Favicon from './Favicon';
import LoadingRow from './LoadingRow';

interface EnrichmentTableProps {
  results: EnrichmentResult[];
}

const GRAY = { bg: '#F3F4F6', text: '#6B7280' };

const GTM_COLORS: [RegExp, { bg: string; text: string }][] = [
  [/usage/i, { bg: '#FEF0E8', text: '#FB7232' }],
  [/freemium|plg|product-led/i, { bg: '#ECFDF5', text: '#059669' }],
  [/sales|enterprise/i, { bg: '#F3E8FF', text: '#9333EA' }],
  [/self-serve|saas|subscription/i, { bg: '#EFF6FF', text: '#3B82F6' }],
];

function getGtmStyle(motion: string | null) {
  if (!motion) return GRAY;
  return GTM_COLORS.find(([re]) => re.test(motion))?.[1] || GRAY;
}

const FIT_COLORS: Record<string, { bg: string; text: string }> = {
  'strong fit': { bg: '#ECFDF5', text: '#059669' },
  'moderate fit': { bg: '#FFFBEB', text: '#D97706' },
  'low fit': GRAY,
};

function getFitStyle(tier: string | null | undefined) {
  return (tier && FIT_COLORS[tier.toLowerCase()]) || GRAY;
}

function splitPrefix(signal: string): [string, string] {
  const match = signal.match(/^\s*([^:]{2,24}):\s*(.*)$/s);
  return match ? [match[1], match[2]] : ['', signal];
}

function linkedinLabel(url: string): string {
  const match = url.match(/linkedin\.com\/in\/([^/?#]+)/i);
  return match ? `in/${decodeURIComponent(match[1])}` : 'Find on LinkedIn';
}

const DecisionMakerCell: React.FC<{ dm: DecisionMaker | null; alternates?: string[] }> = ({ dm, alternates }) => {
  if (!dm || dm.full_name === 'Not found') {
    return (
      <>
        <div className="dm-name dm-missing">Not found</div>
        <div className="dm-role">{dm?.role || 'No public founder, CTO or VP Eng profile found'}</div>
        {dm?.linkedin_url && (
          <a className="linkedin-badge" href={dm.linkedin_url} target="_blank" rel="noopener noreferrer">
            Search LinkedIn ↗
          </a>
        )}
      </>
    );
  }

  const mxVerified = dm.email_status === 'MX Verified';
  const emailTitle = [
    `${dm.email_status}${mxVerified ? ' (domain accepts mail; mailbox not verified)' : ''} · click to copy`,
    alternates && alternates.length ? `Also try: ${alternates.join(', ')}` : '',
  ]
    .filter(Boolean)
    .join('\n');

  return (
    <>
      <div className="dm-name">{dm.full_name}</div>
      <div className="dm-role">{dm.role}</div>
      <div className="dm-links">
        <a className="linkedin-badge" href={dm.linkedin_url} target="_blank" rel="noopener noreferrer" title={dm.linkedin_url}>
          {linkedinLabel(dm.linkedin_url)} ↗
        </a>
        {dm.work_email && (
          <CopyButton text={dm.work_email} className="email-pill" title={emailTitle}>
            <span className="email-text">{dm.work_email}</span>
            {mxVerified ? <span className="mx-ok">MX ✓</span> : <span className="mx-muted">pattern</span>}
            <span className="copy-icon" aria-hidden="true">⧉</span>
          </CopyButton>
        )}
      </div>
    </>
  );
};

const EnrichmentTable: React.FC<EnrichmentTableProps> = ({ results }) => {
  if (results.length === 0) return null;

  return (
    <div className="table-container">
      <table className="enrichment-table">
        <thead>
          <tr>
            <th className="table-header" style={{ width: 160 }}>COMPANY</th>
            <th className="table-header" style={{ width: 185 }}>PRODUCT &amp; ICP</th>
            <th className="table-header" style={{ width: 140 }}>GTM &amp; PRICING</th>
            <th className="table-header" style={{ width: 245 }}>KEY SIGNALS</th>
            <th className="table-header" style={{ width: 175 }}>WHY THEY FIT</th>
            <th className="table-header" style={{ width: 195 }}>POINT OF CONTACT</th>
            <th className="table-header">OUTREACH DRAFT</th>
          </tr>
        </thead>
        <tbody>
          {results.map((result) => {
            if (result.status === 'loading') {
              return <LoadingRow key={result.domain} domain={result.domain} />;
            }

            const companyCell = (
              <td className="table-cell">
                <div className="company-stack">
                  <Favicon domain={result.domain} />
                  <div className="company-text">
                    <div className="company-name">{result.company_name || result.domain}</div>
                    <div className="company-domain">{result.domain}</div>
                  </div>
                </div>
              </td>
            );

            if (result.status === 'error') {
              return (
                <tr key={result.domain} className="table-row error-row">
                  {companyCell}
                  <td className="table-cell" colSpan={6}>
                    <span className="error-message">⚠ Could not enrich — {result.error || 'website unreachable'}</span>
                  </td>
                </tr>
              );
            }

            const gtmStyle = getGtmStyle(result.gtm_motion);
            const fitStyle = getFitStyle(result.fit_tier);

            return (
              <tr key={result.domain} className="table-row fade-in">
                {companyCell}

                <td className="table-cell cell-description">{result.product_and_icp}</td>

                <td className="table-cell">
                  <span className="pill" style={{ backgroundColor: gtmStyle.bg, color: gtmStyle.text }}>
                    {result.gtm_motion}
                  </span>
                  <div className="pricing-sub">{result.pricing_tier_summary}</div>
                </td>

                <td className="table-cell">
                  <ul className="signal-list">
                    {result.tech_and_live_signals.map((signal, i) => {
                      const [prefix, rest] = splitPrefix(signal);
                      return (
                        <li key={i}>
                          {prefix && <strong>{prefix}:</strong>} {rest}
                        </li>
                      );
                    })}
                  </ul>
                </td>

                <td className="table-cell">
                  {result.fit_tier && (
                    <span className="pill" style={{ backgroundColor: fitStyle.bg, color: fitStyle.text }}>
                      {result.fit_tier}
                    </span>
                  )}
                  <div className="fit-reason">{result.fit_reason}</div>
                </td>

                <td className="table-cell">
                  <DecisionMakerCell dm={result.decision_maker} alternates={result.email_alternates} />
                </td>

                <td className="table-cell cell-outreach">
                  {result.ai_outreach ? (
                    <>
                      <CopyButton text={result.ai_outreach} title="Copy email" />
                      {result.ai_outreach}
                    </>
                  ) : (
                    <span className="outreach-skipped">
                      {result.fit_tier === 'Low Fit'
                        ? 'Skipped: low fit for your product, so no draft written.'
                        : 'No draft available.'}
                    </span>
                  )}
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
