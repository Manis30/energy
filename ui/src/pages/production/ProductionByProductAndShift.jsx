import React from 'react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts';
import { formatNumber, formatPercent } from '../../utils/formatters';

function CustomProductTooltip({ active, payload }) {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="custom-chart-tooltip">
        <div className="tooltip-title">{data.product_name} ({data.product_id})</div>
        <div className="tooltip-row">
          <span className="tooltip-label">Family:</span>
          <span className="tooltip-val">{data.product_family}</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Actual Output:</span>
          <span className="tooltip-val font-bold">{formatNumber(data.actual_qty)} units</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Good Units:</span>
          <span className="tooltip-val text-success">{formatNumber(data.good_qty)} units</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Defects / Scrap:</span>
          <span className="tooltip-val text-danger">{formatNumber(data.reject_qty)} ({formatPercent(data.reject_rate)})</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Rework Units:</span>
          <span className="tooltip-val">{formatNumber(data.rework_qty)}</span>
        </div>
      </div>
    );
  }
  return null;
}

function CustomShiftTooltip({ active, payload }) {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="custom-chart-tooltip">
        <div className="tooltip-title">Shift {data.shift_id} Operations</div>
        <div className="tooltip-row">
          <span className="tooltip-label">Actual Output:</span>
          <span className="tooltip-val font-bold">{formatNumber(data.actual_qty)} units</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Good Units:</span>
          <span className="tooltip-val text-success">{formatNumber(data.good_qty)} units</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Defects / Scrap:</span>
          <span className="tooltip-val text-danger">{formatNumber(data.reject_qty)} ({formatPercent(data.reject_rate)})</span>
        </div>
        <div className="tooltip-row">
          <span className="tooltip-label">Downtime:</span>
          <span className="tooltip-val">{formatNumber(data.downtime_min)} min</span>
        </div>
      </div>
    );
  }
  return null;
}

export default function ProductionByProductAndShift({ byProduct = [], byShift = [] }) {
  const productData = (byProduct || []).map((p) => ({
    ...p,
    displayName: p.product_name || p.product_id,
  }));

  const shiftData = (byShift || []).map((s) => ({
    ...s,
    displayShift: `Shift ${s.shift_id}`,
  }));

  return (
    <div className="dashboard-section">
      <div className="section-header">
        <div>
          <h3 className="section-title">Production Distribution by Product SKU & Operating Shift</h3>
          <p className="section-desc">
            Product mix volume analysis across Aster smartphone variants and operating shift performance.
          </p>
        </div>
        <div className="section-tag-group">
          <span className="section-tag info">3 Product SKUs</span>
          <span className="section-tag process">3 Operating Shifts (A, B, C)</span>
        </div>
      </div>

      <div className="product-shift-grid">
        {/* Left: Product Output Comparison */}
        <div className="chart-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Output Volume by Product Model</h4>
              <span className="chart-card-subtitle">Actual vs Good units per product SKU</span>
            </div>
            <div className="chart-legend-custom">
              <span className="legend-item">
                <span className="legend-box" style={{ background: 'var(--brand-purple)' }}></span>
                Actual
              </span>
              <span className="legend-item">
                <span className="legend-box" style={{ background: 'var(--chart-cat-4)' }}></span>
                Good
              </span>
            </div>
          </div>

          <div className="chart-wrapper">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={productData} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" vertical={false} />
                <XAxis
                  dataKey="product_id"
                  stroke="var(--chart-axis)"
                  tick={{ fontSize: 11, fill: 'var(--chart-axis)' }}
                  tickLine={false}
                />
                <YAxis
                  stroke="var(--chart-axis)"
                  tick={{ fontSize: 11, fill: 'var(--chart-axis)' }}
                  tickLine={false}
                  tickFormatter={(val) => `${(val / 1000).toFixed(0)}k`}
                />
                <Tooltip content={<CustomProductTooltip />} />
                <Bar dataKey="actual_qty" fill="var(--brand-purple)" radius={[3, 3, 0, 0]} name="Actual" />
                <Bar dataKey="good_qty" fill="var(--chart-cat-4)" radius={[3, 3, 0, 0]} name="Good" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Product Mini List */}
          <div className="sku-summary-list">
            {productData.map((prod) => (
              <div key={prod.product_id} className="sku-summary-item">
                <div className="sku-item-left">
                  <span className="sku-name">{prod.product_name}</span>
                  <span className="sku-id">{prod.product_id} • {prod.product_family}</span>
                </div>
                <div className="sku-item-right">
                  <span className="sku-actual">{formatNumber(prod.actual_qty)} units</span>
                  <span className="sku-scrap">Scrap: {formatPercent(prod.reject_rate)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right: Shift Output Comparison */}
        <div className="chart-card">
          <div className="chart-card-header">
            <div>
              <h4 className="chart-card-title">Output Volume by Manufacturing Shift</h4>
              <span className="chart-card-subtitle">Actual vs Good units across operating shifts</span>
            </div>
            <div className="chart-legend-custom">
              <span className="legend-item">
                <span className="legend-box" style={{ background: 'var(--brand-blue)' }}></span>
                Actual
              </span>
              <span className="legend-item">
                <span className="legend-box" style={{ background: 'var(--chart-cat-4)' }}></span>
                Good
              </span>
            </div>
          </div>

          <div className="chart-wrapper">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={shiftData} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" vertical={false} />
                <XAxis
                  dataKey="displayShift"
                  stroke="var(--chart-axis)"
                  tick={{ fontSize: 11, fill: 'var(--chart-axis)' }}
                  tickLine={false}
                />
                <YAxis
                  stroke="var(--chart-axis)"
                  tick={{ fontSize: 11, fill: 'var(--chart-axis)' }}
                  tickLine={false}
                  tickFormatter={(val) => `${(val / 1000).toFixed(0)}k`}
                />
                <Tooltip content={<CustomShiftTooltip />} />
                <Bar dataKey="actual_qty" fill="var(--brand-blue)" radius={[3, 3, 0, 0]} name="Actual" />
                <Bar dataKey="good_qty" fill="var(--chart-cat-4)" radius={[3, 3, 0, 0]} name="Good" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Shift Mini List */}
          <div className="sku-summary-list">
            {shiftData.map((shift) => (
              <div key={shift.shift_id} className="sku-summary-item">
                <div className="sku-item-left">
                  <span className="sku-name">{shift.displayShift}</span>
                  <span className="sku-id">Downtime: {formatNumber(shift.downtime_min)} min</span>
                </div>
                <div className="sku-item-right">
                  <span className="sku-actual">{formatNumber(shift.actual_qty)} units</span>
                  <span className="sku-scrap">Yield: {formatPercent(shift.good_rate)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

