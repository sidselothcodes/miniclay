import React, { useState } from 'react';
import { copyText } from '../api';

interface CopyButtonProps {
  text: string;
  className?: string;
  title?: string;
  children?: React.ReactNode;
}

const CopyButton: React.FC<CopyButtonProps> = ({ text, className = 'copy-btn', title, children }) => {
  const [copied, setCopied] = useState(false);

  const handleClick = async () => {
    if (await copyText(text)) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    }
  };

  return (
    <button type="button" className={className} onClick={handleClick} title={title || 'Copy'}>
      {copied ? 'Copied ✓' : children || 'Copy'}
    </button>
  );
};

export default CopyButton;
