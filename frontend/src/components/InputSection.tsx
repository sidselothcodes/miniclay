import React from 'react';

interface InputSectionProps {
  value: string;
  onChange: (value: string) => void;
  onEnrich: () => void;
  isLoading: boolean;
}

const InputSection: React.FC<InputSectionProps> = ({ value, onChange, onEnrich, isLoading }) => {
  return (
    <div className="input-card">
      <textarea
        className="domain-input"
        rows={6}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={"Enter company domains, one per line...\n\nExamples:\nstripe.com\nnotion.so\nvercel.com"}
        disabled={isLoading}
      />
      <div className="input-footer">
        <span className="input-hint">Enter up to 5 domains. We'll enrich each with AI.</span>
        <button
          className="enrich-button"
          onClick={onEnrich}
          disabled={isLoading || !value.trim()}
        >
          {isLoading ? (
            <>
              <span className="spinner" />
              Enriching...
            </>
          ) : (
            'Enrich \u2192'
          )}
        </button>
      </div>
    </div>
  );
};

export default InputSection;
