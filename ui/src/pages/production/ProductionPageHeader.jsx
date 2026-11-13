import React from 'react';
import AnalyticsPageHeader from '../../components/common/AnalyticsPageHeader';

export default function ProductionPageHeader({
  dateRange,
  lastRefreshed,
  onRefresh,
  refreshing,
  selectedPlant,
  onSelectPlant,
}) {
  return (
    <AnalyticsPageHeader
      badge="Manufacturing Data"
      title="Production Analytics"
      subtitle="Manufacturing throughput, first-pass quality yield, line-level output, and operational stoppage tracking."
      selectedPlant={selectedPlant}
      onSelectPlant={onSelectPlant}
      dateRange={dateRange}
      onRefresh={onRefresh}
      refreshing={refreshing}
      lastRefreshed={lastRefreshed}
    />
  );
}
