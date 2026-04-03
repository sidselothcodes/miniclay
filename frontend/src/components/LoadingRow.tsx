import React from 'react';

interface LoadingRowProps {
  domain: string;
}

const LoadingRow: React.FC<LoadingRowProps> = ({ domain }) => {
  return (
    <tr className="table-row">
      <td className="table-cell cell-domain">
        <span className="domain-icon">🌐</span>
        {domain}
      </td>
      <td className="table-cell"><div className="skeleton" style={{ width: '80%' }} /></td>
      <td className="table-cell"><div className="skeleton" style={{ width: '90%' }} /></td>
      <td className="table-cell"><div className="skeleton" style={{ width: '60%' }} /></td>
      <td className="table-cell"><div className="skeleton" style={{ width: '50%' }} /></td>
      <td className="table-cell"><div className="skeleton" style={{ width: '95%' }} /></td>
      <td className="table-cell"><div className="skeleton" style={{ width: '70%' }} /></td>
    </tr>
  );
};

export default LoadingRow;
