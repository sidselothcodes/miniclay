import React, { useState } from 'react';

const Favicon: React.FC<{ domain: string }> = ({ domain }) => {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return <span className="domain-icon favicon-fallback">🌐</span>;
  }
  return (
    <img
      className="favicon"
      src={`https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=64`}
      alt=""
      width={20}
      height={20}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
};

export default Favicon;
