import React from 'react';

const Footer: React.FC = () => {
  return (
    <footer className="footer">
      <p className="footer-main">
        Built by <strong>Siddarth Seloth</strong> to explore Clay's enrichment pipeline concept.
      </p>
      <p className="footer-sub">I'd love to build the real thing.</p>
      <div className="footer-links">
        <a
          href="https://linkedin.com/in/siddarthseloth"
          target="_blank"
          rel="noopener noreferrer"
          className="footer-link"
        >
          LinkedIn
        </a>
        <span className="footer-divider">·</span>
        <a
          href="https://github.com/siddarthseloth"
          target="_blank"
          rel="noopener noreferrer"
          className="footer-link"
        >
          GitHub
        </a>
      </div>
    </footer>
  );
};

export default Footer;
