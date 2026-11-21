import React from 'react';
import { formatNumber, formatPercent } from '../../utils/formatters';

const hasNumber = (value) =>
  value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));

export default function ProductionByProductAndShift({
  byProduct = [],
  byShift = [],
  productDataAvailable = true,
  shiftDataAvailable = true,
  selectedProduct = null,
  onSelectProduct = null,
  selectedShift = null,
  onSelectShift = null,
}) {
  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Product SKU &amp; Operating Shift Breakdown</h3>
          <p className="section-desc">
            Production throughput and quality distribution categorized by finished product model and shift.
          </p>
        </div>
        <div className="section-tag-group">
          <span className="section-tag info">
            {productDataAvailable ? `${byProduct.length} SKUs` : 'SKU data unavailable'}
          </span>
          <span className="section-tag process">
            {shiftDataAvailable ? `${byShift.length} shifts` : 'Shift data unavailable'}
          </span>
        </div>
      </div>

      <div className="product-shift-grid">
        {/* Left: Product SKU Breakdown Card */}
        <div className="chart-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Output Volume by Product SKU</h4>
              <span className="chart-card-subtitle">Actual, good, and rejection rate per product model</span>
            </div>
          </div>

          <div className="table-responsive">
            <table className="production-line-table">
              <thead>
                <tr>
                  <th>Product SKU</th>
                  <th>Family</th>
                  <th className="text-right">Actual Output</th>
                  <th className="text-right">Good Units</th>
                  <th className="text-right">Reject Rate</th>
                </tr>
              </thead>
              <tbody>
                {!productDataAvailable || byProduct.length === 0 ? (
                  <tr>
                    <td colSpan="5" className="text-center text-muted" style={{ padding: '2rem' }}>
                      {!productDataAvailable ? 'Product data unavailable' : 'No product records returned'}
                    </td>
                  </tr>
                ) : (
                  byProduct.map((p) => {
                    const isSelected = selectedProduct === p.product_id;
                    return (
                      <tr
                        key={p.product_id}
                        onClick={() => onSelectProduct && onSelectProduct(isSelected ? null : p.product_id)}
                        style={{
                          cursor: onSelectProduct ? 'pointer' : 'default',
                          backgroundColor: isSelected ? 'var(--bg-active, rgba(111, 61, 186, 0.12))' : undefined,
                        }}
                        title={onSelectProduct ? `Click to ${isSelected ? 'clear filter' : `filter by ${p.product_id}`}` : undefined}
                      >
                        <td>
                          <div style={{ display: 'flex', flexDirection: 'column' }}>
                            <span className="font-semibold" style={{ color: isSelected ? 'var(--brand-purple)' : undefined }}>
                              {p.product_name || p.product_id}
                            </span>
                            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{p.product_id}</span>
                          </div>
                        </td>
                        <td>
                          <span className="area-category-badge process">{p.product_family}</span>
                        </td>
                        <td className="text-right font-mono font-semibold">
                          {formatNumber(p.actual_qty)}
                        </td>
                        <td className="text-right font-mono text-success">
                          {formatNumber(p.good_qty)}
                        </td>
                        <td className="text-right font-mono">
                          {formatPercent(p.reject_rate)}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right: Operating Shift Distribution Card */}
        <div className="chart-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Output Volume by Shift</h4>
              <span className="chart-card-subtitle">Throughput, yield, and downtime per manufacturing shift</span>
            </div>
          </div>

          <div className="table-responsive">
            <table className="production-line-table">
              <thead>
                <tr>
                  <th>Shift</th>
                  <th className="text-right">Actual Output</th>
                  <th className="text-right">Good Units</th>
                  <th className="text-right">Quality Yield</th>
                  <th className="text-right">Reported Downtime</th>
                </tr>
              </thead>
              <tbody>
                {!shiftDataAvailable || byShift.length === 0 ? (
                  <tr>
                    <td colSpan="5" className="text-center text-muted" style={{ padding: '2rem' }}>
                      {!shiftDataAvailable ? 'Shift data unavailable' : 'No shift records returned'}
                    </td>
                  </tr>
                ) : (
                  byShift.map((s) => {
                    const isSelected = selectedShift === s.shift_id;
                    return (
                      <tr
                        key={s.shift_id}
                        onClick={() => onSelectShift && onSelectShift(isSelected ? null : s.shift_id)}
                        style={{
                          cursor: onSelectShift ? 'pointer' : 'default',
                          backgroundColor: isSelected ? 'var(--bg-active, rgba(111, 61, 186, 0.12))' : undefined,
                        }}
                        title={onSelectShift ? `Click to ${isSelected ? 'clear filter' : `filter by Shift ${s.shift_id}`}` : undefined}
                      >
                        <td>
                          <span className="font-semibold" style={{ color: isSelected ? 'var(--brand-purple)' : undefined }}>
                            Shift {s.shift_id}
                          </span>
                        </td>
                        <td className="text-right font-mono font-semibold">
                          {formatNumber(s.actual_qty)}
                        </td>
                        <td className="text-right font-mono text-success">
                          {formatNumber(s.good_qty)}
                        </td>
                        <td className="text-right font-mono">
                          {formatPercent(s.good_rate)}
                        </td>
                        <td className="text-right font-mono">
                          {hasNumber(s.downtime_min) ? `${formatNumber(s.downtime_min)} min` : '—'}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
