import React from 'react';
import Favicon from './Favicon';

interface LoadingRowProps {
  domain: string;
}

const LoadingRow: React.FC<LoadingRowProps> = ({ domain }) => {
  return (
    <tr className="table-row">
      <td className="table-cell">
        <div className="company-stack">
          <Favicon domain={domain} />
          <div className="company-text">
            <div className="skeleton" style={{ width: 70, marginBottom: 6 }} />
            <div className="company-domain">{domain}</div>
          </div>
        </div>
      </td>
      <td className="table-cell"><div className="skeleton" style={{ width: '90%' }} /></td>
      <td className="table-cell"><div className="skeleton" style={{ width: '60%' }} /></td>
      <td className="table-cell"><div className="skeleton" style={{ width: '95%' }} /></td>
      <td className="table-cell"><div className="skeleton" style={{ width: '70%' }} /></td>
      <td className="table-cell"><div className="skeleton" style={{ width: '95%' }} /></td>
      <td className="table-cell"><div className="skeleton" style={{ width: '70%' }} /></td>
    </tr>
  );
};

export default LoadingRow;
