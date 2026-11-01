import React from 'react';

interface InputSectionProps {
  value: string;
  onChange: (value: string) => void;
  sellerContext: string;
  onSellerContextChange: (value: string) => void;
  onEnrich: () => void;
  isLoading: boolean;
  domainCount: number;
  maxDomains: number;
}

const InputSection: React.FC<InputSectionProps> = ({
  value,
  onChange,
  sellerContext,
  onSellerContextChange,
  onEnrich,
  isLoading,
  domainCount,
  maxDomains,
}) => {
  const overLimit = domainCount > maxDomains;

  return (
    <div className="input-card">
      <label className="input-label" htmlFor="seller-context">
        Your Product / Value Prop (Outreach Context)
      </label>
      <input
        id="seller-context"
        type="text"
        className="context-input"
        value={sellerContext}
        onChange={(e) => onSellerContextChange(e.target.value)}
        placeholder="What are you selling? One sentence, e.g. what it catches or fixes."
        maxLength={600}
        disabled={isLoading}
      />

      <label className="input-label" htmlFor="domains">
        Company Domains
      </label>
      <textarea
        id="domains"
        className="domain-input"
        rows={6}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={'Enter company domains, one per line...\n\nExamples:\nstripe.com\nnotion.so\nvercel.com'}
        disabled={isLoading}
      />
      <div className="input-footer">
        <span className={`input-hint${overLimit ? ' input-hint-warn' : ''}`}>
          {overLimit
            ? `${domainCount} domains entered. Only the first ${maxDomains} will be enriched.`
            : `Enter up to ${maxDomains} domains (${domainCount}/${maxDomains}). We'll enrich each from 5 live sources.`}
        </span>
        <button className="enrich-button" onClick={onEnrich} disabled={isLoading || !value.trim()}>
          {isLoading ? (
            <>
              <span className="spinner" />
              Enriching...
            </>
          ) : (
            'Enrich →'
          )}
        </button>
      </div>
    </div>
  );
};

export default InputSection;
