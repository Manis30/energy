import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { formatNumber, formatCurrency } from '../../utils/formatters';

/**
 * Robust CSV and TSV parser supporting quotes and escaped delimiters.
 */
export function parseDelimitedText(text) {
  if (!text || !text.trim()) return [];

  const lines = text.trim().split(/\r?\n/);
  if (lines.length === 0) return [];

  const firstLine = lines[0];
  const tabCount = (firstLine.match(/\t/g) || []).length;
  const commaCount = (firstLine.match(/,/g) || []).length;
  const delimiter = tabCount >= commaCount && tabCount > 0 ? '\t' : ',';

  const rows = [];
  for (const line of lines) {
    if (!line.trim()) continue;

    const values = [];
    let current = '';
    let inQuotes = false;

    for (let i = 0; i < line.length; i++) {
      const char = line[i];
      if (char === '"' || char === "'") {
        if (inQuotes && line[i + 1] === char) {
          current += char;
          i++; // skip escaped quote
        } else {
          inQuotes = !inQuotes;
        }
      } else if (char === delimiter && !inQuotes) {
        values.push(current.trim());
        current = '';
      } else {
        current += char;
      }
    }
    values.push(current.trim());
    rows.push(values);
  }

  return rows;
}

const PLANT_OPTIONS = [
  { id: 'IN-TN-01', name: 'IN-TN-01 (Tamil Nadu Electronics Assembly)' },
  { id: 'IN-KA-01', name: 'IN-KA-01 (Karnataka Plant)' },
];

/**
 * Plant specific master options helper
 */
function getPlantMasterData(pId, masterData) {
  if (pId === 'IN-KA-01') {
    return {
      meters: masterData?.meters || ['MTR-MAIN', 'MTR-LINE1', 'MTR-LINE2', 'MTR-HVAC', 'MTR-UTILITY'],
      lines: masterData?.lines || ['LINE-01', 'LINE-02', 'PACK-01'],
      products: masterData?.products || ['SPH-A15-128', 'SPH-A15-256', 'SPH-PRO-256'],
      meterAreas: masterData?.meter_areas || {
        'MTR-MAIN': 'SUBSTATION',
        'MTR-LINE1': 'ASSEMBLY',
        'MTR-LINE2': 'ASSEMBLY',
        'MTR-HVAC': 'HVAC',
        'MTR-UTILITY': 'UTILITY',
      },
    };
  }
  return {
    meters: masterData?.meters || ['MTR-SMT', 'MTR-FAL', 'MTR-HVAC', 'MTR-COMPRESSOR', 'MTR-CHILLER'],
    lines: masterData?.lines || ['SMT-L1', 'FAL-L1'],
    products: masterData?.products || ['SPH-A15-128', 'SPH-A15-256', 'SPH-PRO-256'],
    meterAreas: masterData?.meter_areas || {
      'MTR-SMT': 'SMT',
      'MTR-FAL': 'FAL',
      'MTR-HVAC': 'HVAC',
      'MTR-COMPRESSOR': 'COMPRESSOR',
      'MTR-CHILLER': 'CHILLER',
    },
  };
}

/**
 * DailyDataEntryForm Component
 *
 * Stage 1 Compact Summary & "Add readings" Modal:
 * - Default view: Compact summary card with selected plant/date, database-confirmed counts,
 *   primary "Add readings" button, and secondary "View saved entries" action.
 * - "Add readings" modal:
 *   - Row 1: Plant dropdown and Reporting date picker (prefilled from page, editable).
 *   - Row 2: Energy / Production selector with "Paste readings" (default) and "Enter manually".
 *   - Below input: Expected columns, compact preview, total row count, inline errors.
 *   - Sticky footer: Cancel (leaves page alone) and Save readings (submits only active type).
 *   - Confirmed save switches page to saved plant/date and reloads counts & status.
 *   - Drafts kept separate by plant, date, and type.
 */
export default function DailyDataEntryForm({
  reportingDate,
  plantId,
  masterData,
  energyRows = [],
  setEnergyRows,
  productionRows = [],
  setProductionRows,
  savedCounts,
  onValidate,
  onSave,
  validating,
  saving,
  validationResult,
  onReload,
  loadingSaved,
  onSwitchPlantAndDate,
}) {
  // Modal states
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [viewSavedModalOpen, setViewSavedModalOpen] = useState(false);

  // Modal active scope (can differ from underlying page before save)
  const [modalPlant, setModalPlant] = useState(plantId);
  const [modalDate, setModalDate] = useState(reportingDate);
  const [modalType, setModalType] = useState('energy'); // 'energy' | 'production'
  const [modalMode, setModalMode] = useState('paste'); // 'paste' | 'manual'

  // Input states inside modal
  const [pasteRawText, setPasteRawText] = useState('');
  const [pastePreviewRows, setPastePreviewRows] = useState([]);
  const [modalError, setModalError] = useState(null);
  const [saveSuccessMsg, setSaveSuccessMsg] = useState(null);

  // Inline validation errors for manual mode
  const [energyErrors, setEnergyErrors] = useState({});
  const [prodErrors, setProdErrors] = useState({});

  // Editing state for saved records: { tab: 'energy'|'production', index: number } | null
  const [editingRecord, setEditingRecord] = useState(null);

  // Derived plant master data
  const { meters, lines, products, meterAreas } = useMemo(
    () => getPlantMasterData(modalPlant, masterData),
    [modalPlant, masterData]
  );

  // Draft generators
  const createBlankEnergyDraft = useCallback(
    (date, mList = meters, mAreas = meterAreas) => ({
      timestamp: `${date} 00:00`,
      meter_id: mList[0] || 'MTR-SMT',
      area: mAreas[mList[0] || 'MTR-SMT'] || 'SMT',
      energy_source: 'ELECTRICITY',
      consumption_kwh: '',
      demand_kw: '',
      power_factor: '',
      tariff_inr_per_kwh: '8.25',
      cost_inr: '',
      co2e_kg: '',
      reading_quality: 'VALID',
    }),
    [meters, meterAreas]
  );

  const createBlankProdDraft = useCallback(
    (date, lList = lines, pList = products) => ({
      event_ts: `${date} 00:00`,
      line_id: lList[0] || 'SMT-L1',
      shift_id: 'A',
      product_id: pList[0] || 'SPH-A15-256',
      production_order_id: `PO-${date.replace(/-/g, '')}-01`,
      target_qty: '',
      actual_qty: '',
      good_qty: '',
      reject_qty: '',
      rework_qty: '0',
      downtime_min: '0',
      downtime_reason: 'NONE',
      operator_team: 'TEAM-01',
      source_system: 'MANUAL_ENTRY',
      data_quality: 'VALID',
    }),
    [lines, products]
  );

  const [energyDraft, setEnergyDraft] = useState(() => createBlankEnergyDraft(reportingDate));
  const [prodDraft, setProdDraft] = useState(() => createBlankProdDraft(reportingDate));

  // Drafts storage keyed by `${plant}:${date}:${type}`
  const draftsStoreRef = useRef({});
  const currentDraftKeyRef = useRef(`${modalPlant}:${modalDate}:${modalType}`);

  // Helper to persist current active draft into draftsStoreRef
  const persistActiveDraft = useCallback(() => {
    const key = currentDraftKeyRef.current;
    if (!key) return;
    draftsStoreRef.current[key] = {
      pasteRawText,
      pastePreviewRows,
      energyDraft,
      prodDraft,
      modalMode,
      editingRecord,
    };
  }, [pasteRawText, pastePreviewRows, energyDraft, prodDraft, modalMode, editingRecord]);

  // Helper to restore draft for a target key
  const restoreDraftForScope = useCallback(
    (targetPlant, targetDate, targetType) => {
      const key = `${targetPlant}:${targetDate}:${targetType}`;
      currentDraftKeyRef.current = key;
      const stored = draftsStoreRef.current[key];
      const plantMaster = getPlantMasterData(targetPlant, masterData);

      if (stored) {
        setPasteRawText(stored.pasteRawText || '');
        setPastePreviewRows(stored.pastePreviewRows || []);
        setEnergyDraft(stored.energyDraft || createBlankEnergyDraft(targetDate, plantMaster.meters, plantMaster.meterAreas));
        setProdDraft(stored.prodDraft || createBlankProdDraft(targetDate, plantMaster.lines, plantMaster.products));
        setModalMode(stored.modalMode || 'paste');
        setEditingRecord(stored.editingRecord || null);
      } else {
        setPasteRawText('');
        setPastePreviewRows([]);
        setEnergyDraft(createBlankEnergyDraft(targetDate, plantMaster.meters, plantMaster.meterAreas));
        setProdDraft(createBlankProdDraft(targetDate, plantMaster.lines, plantMaster.products));
        setModalMode('paste');
        setEditingRecord(null);
      }
      setModalError(null);
      setEnergyErrors({});
      setProdErrors({});
    },
    [masterData, createBlankEnergyDraft, createBlankProdDraft]
  );

  // Sync modal scope when page plantId or reportingDate changes from outside
  useEffect(() => {
    if (!addModalOpen) {
      setModalPlant(plantId);
      setModalDate(reportingDate);
    }
  }, [plantId, reportingDate, addModalOpen]);

  // Open Add Readings modal
  const handleOpenAddReadings = (initialType = 'energy', initialMode = 'paste') => {
    setModalPlant(plantId);
    setModalDate(reportingDate);
    setModalType(initialType);
    setModalMode(initialMode);
    restoreDraftForScope(plantId, reportingDate, initialType);
    setAddModalOpen(true);
  };

  // Close Add Readings modal (Cancel leaves underlying page selection alone)
  const handleCancelModal = () => {
    persistActiveDraft();
    setAddModalOpen(false);
    setModalError(null);
  };

  // Switch plant inside modal
  const handleModalPlantChange = (newPlant) => {
    persistActiveDraft();
    setModalPlant(newPlant);
    restoreDraftForScope(newPlant, modalDate, modalType);
  };

  // Switch reporting date inside modal
  const handleModalDateChange = (newDate) => {
    persistActiveDraft();
    setModalDate(newDate);
    restoreDraftForScope(modalPlant, newDate, modalType);
  };

  // Switch type (Energy / Production) inside modal
  const handleModalTypeChange = (newType) => {
    persistActiveDraft();
    setModalType(newType);
    restoreDraftForScope(modalPlant, modalDate, newType);
  };

  // Switch mode (Paste / Manual) inside modal
  const handleModalModeChange = (newMode) => {
    setModalMode(newMode);
    setModalError(null);
  };

  // ---------------------------------------------------------------------------
  // ENERGY FIELD CHANGE HANDLERS
  // ---------------------------------------------------------------------------
  const handleEnergyChange = (field, value) => {
    setEnergyDraft((prev) => {
      const updated = { ...prev, [field]: value };
      if (field === 'meter_id') {
        updated.area = meterAreas[value] || 'SMT';
      }

      if (field === 'consumption_kwh') {
        const numKwh = parseFloat(value);
        if (!isNaN(numKwh) && numKwh >= 0) {
          const tariff = parseFloat(updated.tariff_inr_per_kwh || 8.25);
          updated.cost_inr = (numKwh * tariff).toFixed(2);
          updated.co2e_kg = (numKwh * 0.716).toFixed(4);
        } else {
          updated.cost_inr = '';
          updated.co2e_kg = '';
        }
      }

      if (field === 'tariff_inr_per_kwh') {
        const tariff = parseFloat(value);
        const numKwh = parseFloat(updated.consumption_kwh);
        if (!isNaN(tariff) && !isNaN(numKwh) && numKwh >= 0) {
          updated.cost_inr = (numKwh * tariff).toFixed(2);
        } else {
          updated.cost_inr = '';
        }
      }

      return updated;
    });

    if (energyErrors[field] || energyErrors._form) {
      setEnergyErrors((prev) => {
        const next = { ...prev };
        delete next[field];
        delete next._form;
        return next;
      });
    }
  };

  // ---------------------------------------------------------------------------
  // PRODUCTION FIELD CHANGE HANDLERS
  // ---------------------------------------------------------------------------
  const handleProdChange = (field, value) => {
    setProdDraft((prev) => {
      const updated = { ...prev, [field]: value };
      if (field === 'actual_qty' || field === 'good_qty') {
        const actual = parseInt(field === 'actual_qty' ? value : updated.actual_qty, 10);
        const good = parseInt(field === 'good_qty' ? value : updated.good_qty, 10);
        if (!isNaN(actual) && !isNaN(good) && actual >= good) {
          updated.reject_qty = String(actual - good);
        }
      }
      return updated;
    });

    if (prodErrors[field] || prodErrors._form) {
      setProdErrors((prev) => {
        const next = { ...prev };
        delete next[field];
        delete next._form;
        return next;
      });
    }
  };

  // ---------------------------------------------------------------------------
  // PARSE DELIMITED TEXT (PASTE READINGS)
  // ---------------------------------------------------------------------------
  const handleParsePasteText = (text) => {
    setPasteRawText(text);
    setModalError(null);
    if (!text || !text.trim()) {
      setPastePreviewRows([]);
      return;
    }

    try {
      const parsed = parseDelimitedText(text);
      if (parsed.length === 0) {
        setPastePreviewRows([]);
        return;
      }

      const firstRowNorm = parsed[0].map((c) =>
        String(c || '').toLowerCase().trim().replace(/[\s_\-\.\/\(\)]+/g, '')
      );

      const energyHeaderMatches = firstRowNorm.map((cell) => {
        if (/^(timestamp|time|hour|datetime|date|eventts|ts)$/.test(cell)) return 'timestamp';
        if (/^(meter|meterid|mtr)$/.test(cell)) return 'meter_id';
        if (/^(plant|plantid)$/.test(cell)) return 'plant_id';
        if (/^(consumption|consumptionkwh|kwh|energykwh|activepower|reading)$/.test(cell)) return 'consumption_kwh';
        if (/^(demand|demandkw|kw|peakdemand)$/.test(cell)) return 'demand_kw';
        if (/^(powerfactor|pf|powerfact)$/.test(cell)) return 'power_factor';
        if (/^(tariff|tariffinrperkwh|rate)$/.test(cell)) return 'tariff_inr_per_kwh';
        if (/^(cost|costinr)$/.test(cell)) return 'cost_inr';
        if (/^(co2|co2e|co2ekg|emissions)$/.test(cell)) return 'co2e_kg';
        if (/^(readingquality|quality)$/.test(cell)) return 'reading_quality';
        if (/^(area)$/.test(cell)) return 'area';
        if (/^(energysource|source)$/.test(cell)) return 'energy_source';
        return null;
      });

      const prodHeaderMatches = firstRowNorm.map((cell) => {
        if (/^(eventts|timestamp|time|hour|datetime|date|ts)$/.test(cell)) return 'event_ts';
        if (/^(line|lineid|productionline)$/.test(cell)) return 'line_id';
        if (/^(plant|plantid)$/.test(cell)) return 'plant_id';
        if (/^(shift|shiftid)$/.test(cell)) return 'shift_id';
        if (/^(product|productid|sku|productsku)$/.test(cell)) return 'product_id';
        if (/^(actual|actualqty|actualunits|produced|actualquantity|qty)$/.test(cell)) return 'actual_qty';
        if (/^(good|goodqty|goodunits|goodquantity|passed)$/.test(cell)) return 'good_qty';
        if (/^(reject|rejectqty|rejectunits|rejected|rejects|scrap)$/.test(cell)) return 'reject_qty';
        if (/^(target|targetqty|targetunits)$/.test(cell)) return 'target_qty';
        if (/^(downtime|downtimemin|downtimeminutes)$/.test(cell)) return 'downtime_min';
        if (/^(downtimereason|reason)$/.test(cell)) return 'downtime_reason';
        if (/^(rework|reworkqty)$/.test(cell)) return 'rework_qty';
        if (/^(team|operatorteam)$/.test(cell)) return 'operator_team';
        if (/^(po|ponumber|order|orderid|productionorderid)$/.test(cell)) return 'production_order_id';
        if (/^(sourcesystem|source)$/.test(cell)) return 'source_system';
        if (/^(dataquality|quality)$/.test(cell)) return 'data_quality';
        return null;
      });

      const isEnergy = modalType === 'energy';
      const headerMatches = isEnergy ? energyHeaderMatches : prodHeaderMatches;
      const matchedCount = headerMatches.filter(Boolean).length;
      const hasHeaders = matchedCount >= 2 || (parsed.length > 1 && matchedCount >= 1);

      const startIndex = hasHeaders ? 1 : 0;
      const parsedItems = [];

      for (let i = startIndex; i < parsed.length; i++) {
        const raw = parsed[i];
        if (!raw || raw.length === 0 || (raw.length === 1 && !raw[0])) continue;

        const rowErrors = [];

        if (isEnergy) {
          let tsVal = '',
            meterVal = '',
            kwhVal = '',
            demandVal = '',
            pfVal = '',
            rowPlant = '',
            tariffVal = '8.25';

          if (hasHeaders) {
            raw.forEach((val, colIdx) => {
              const field = headerMatches[colIdx];
              if (field === 'timestamp') tsVal = val;
              else if (field === 'meter_id') meterVal = val;
              else if (field === 'consumption_kwh') kwhVal = val;
              else if (field === 'demand_kw') demandVal = val;
              else if (field === 'power_factor') pfVal = val;
              else if (field === 'plant_id') rowPlant = val;
              else if (field === 'tariff_inr_per_kwh') tariffVal = val;
            });
          } else {
            // Positional fallback: 0: Timestamp, 1: Meter, 2: Consumption, 3: Demand, 4: PF, 5: Plant
            tsVal = raw[0] || '';
            meterVal = raw[1] || '';
            kwhVal = raw[2] !== undefined ? raw[2] : '';
            demandVal = raw[3] !== undefined ? raw[3] : '';
            pfVal = raw[4] !== undefined ? raw[4] : '';
            rowPlant = raw[5] || '';
          }

          let formattedTs = String(tsVal || '').trim();
          if (formattedTs && !formattedTs.includes('-') && (formattedTs.includes(':') || formattedTs.length <= 5)) {
            formattedTs = `${modalDate} ${formattedTs.padStart(5, '0')}`;
          } else if (!formattedTs) {
            formattedTs = `${modalDate} ${String(parsedItems.length % 24).padStart(2, '0')}:00`;
          } else if (formattedTs.includes('-')) {
            const datePart = formattedTs.split(/[ T]/)[0];
            if (datePart !== modalDate) {
              rowErrors.push(`Date mismatch: ${datePart} vs ${modalDate}`);
            }
          }

          if (rowPlant && rowPlant.trim() && rowPlant.trim() !== modalPlant) {
            rowErrors.push(`Plant mismatch: ${rowPlant.trim()} vs ${modalPlant}`);
          }

          const cleanMeter = (meterVal || '').trim() || meters[0] || 'MTR-SMT';
          if (!meterVal || !meterVal.trim()) {
            rowErrors.push('Missing meter');
          }

          const cleanKwh = kwhVal !== undefined && kwhVal !== null ? String(kwhVal).trim() : '';
          let parsedKwh = null;
          if (cleanKwh === '' || isNaN(Number(cleanKwh))) {
            rowErrors.push('Missing or invalid Consumption (kWh)');
          } else if (Number(cleanKwh) < 0) {
            rowErrors.push('Consumption must be >= 0');
          } else {
            parsedKwh = parseFloat(cleanKwh);
          }

          let cleanDemand = '';
          if (demandVal !== undefined && demandVal !== null && String(demandVal).trim() !== '') {
            const numDemand = Number(demandVal);
            if (isNaN(numDemand) || numDemand < 0) {
              rowErrors.push('Demand must be a non-negative number');
            } else {
              cleanDemand = String(demandVal).trim();
            }
          }

          let cleanPf = '';
          if (pfVal !== undefined && pfVal !== null && String(pfVal).trim() !== '') {
            const numPf = Number(pfVal);
            if (isNaN(numPf) || numPf < 0 || numPf > 1.0) {
              rowErrors.push('Power factor must be between 0.00 and 1.00');
            } else {
              cleanPf = String(pfVal).trim();
            }
          }

          const parsedTariff = parseFloat(tariffVal || 8.25);
          const costVal = parsedKwh !== null ? (parsedKwh * parsedTariff).toFixed(2) : '';
          const co2Val = parsedKwh !== null ? (parsedKwh * 0.716).toFixed(4) : '';

          parsedItems.push({
            timestamp: formattedTs,
            plant_id: modalPlant,
            meter_id: cleanMeter,
            area: meterAreas[cleanMeter] || 'SMT',
            energy_source: 'ELECTRICITY',
            consumption_kwh: cleanKwh,
            demand_kw: cleanDemand !== '' ? cleanDemand : null,
            power_factor: cleanPf !== '' ? cleanPf : null,
            tariff_inr_per_kwh: String(parsedTariff),
            cost_inr: costVal !== '' ? costVal : null,
            co2e_kg: co2Val !== '' ? co2Val : null,
            reading_quality: 'VALID',
            _error: rowErrors.length > 0 ? rowErrors.join('; ') : null,
          });
        } else {
          // Production
          let tsVal = '',
            lineVal = '',
            shiftVal = 'A',
            prodVal = '',
            actualVal = '',
            goodVal = '',
            rejectVal = '',
            downtimeVal = '0',
            reasonVal = 'NONE',
            rowPlant = '';

          if (hasHeaders) {
            raw.forEach((val, colIdx) => {
              const field = headerMatches[colIdx];
              if (field === 'event_ts') tsVal = val;
              else if (field === 'line_id') lineVal = val;
              else if (field === 'shift_id') shiftVal = val;
              else if (field === 'product_id') prodVal = val;
              else if (field === 'actual_qty') actualVal = val;
              else if (field === 'good_qty') goodVal = val;
              else if (field === 'reject_qty') rejectVal = val;
              else if (field === 'downtime_min') downtimeVal = val;
              else if (field === 'downtime_reason') reasonVal = val;
              else if (field === 'plant_id') rowPlant = val;
            });
          } else {
            tsVal = raw[0] || '';
            lineVal = raw[1] || '';
            shiftVal = raw[2] || 'A';
            prodVal = raw[3] || '';
            actualVal = raw[4] !== undefined ? raw[4] : '';
            goodVal = raw[5] !== undefined ? raw[5] : '';
            rejectVal = raw[6] !== undefined ? raw[6] : '';
            downtimeVal = raw[7] !== undefined ? raw[7] : '0';
            reasonVal = raw[8] || 'NONE';
            rowPlant = raw[9] || '';
          }

          let formattedTs = String(tsVal || '').trim();
          if (formattedTs && !formattedTs.includes('-') && (formattedTs.includes(':') || formattedTs.length <= 5)) {
            formattedTs = `${modalDate} ${formattedTs.padStart(5, '0')}`;
          } else if (!formattedTs) {
            formattedTs = `${modalDate} ${String(parsedItems.length % 24).padStart(2, '0')}:00`;
          } else if (formattedTs.includes('-')) {
            const datePart = formattedTs.split(/[ T]/)[0];
            if (datePart !== modalDate) {
              rowErrors.push(`Date mismatch: ${datePart} vs ${modalDate}`);
            }
          }

          if (rowPlant && rowPlant.trim() && rowPlant.trim() !== modalPlant) {
            rowErrors.push(`Plant mismatch: ${rowPlant.trim()} vs ${modalPlant}`);
          }

          const cleanLine = (lineVal || '').trim() || lines[0] || 'SMT-L1';
          if (!lineVal || !lineVal.trim()) {
            rowErrors.push('Missing production line');
          }

          const cleanProduct = (prodVal || '').trim() || products[0] || 'SPH-A15-256';
          const cleanActual = actualVal !== undefined && actualVal !== null ? String(actualVal).trim() : '';
          const cleanGood = goodVal !== undefined && goodVal !== null ? String(goodVal).trim() : '';

          let parsedActual = null;
          let parsedGood = null;

          if (cleanActual === '' || isNaN(parseInt(cleanActual, 10)) || parseInt(cleanActual, 10) < 0) {
            rowErrors.push('Missing or invalid actual units produced');
          } else {
            parsedActual = parseInt(cleanActual, 10);
          }

          if (cleanGood === '' || isNaN(parseInt(cleanGood, 10)) || parseInt(cleanGood, 10) < 0) {
            rowErrors.push('Missing or invalid good units');
          } else {
            parsedGood = parseInt(cleanGood, 10);
          }

          if (parsedActual !== null && parsedGood !== null && parsedGood > parsedActual) {
            rowErrors.push('Good units cannot exceed actual units');
          }

          let calculatedReject = '0';
          if (rejectVal !== undefined && rejectVal !== null && String(rejectVal).trim() !== '') {
            calculatedReject = String(rejectVal).trim();
          } else if (parsedActual !== null && parsedGood !== null) {
            calculatedReject = String(Math.max(0, parsedActual - parsedGood));
          }

          parsedItems.push({
            event_ts: formattedTs,
            plant_id: modalPlant,
            line_id: cleanLine,
            shift_id: (shiftVal || 'A').trim().toUpperCase(),
            product_id: cleanProduct,
            production_order_id: `PO-${modalDate.replace(/-/g, '')}-${String(i).padStart(2, '0')}`,
            target_qty: cleanActual !== '' ? cleanActual : null,
            actual_qty: cleanActual,
            good_qty: cleanGood,
            reject_qty: calculatedReject,
            rework_qty: '0',
            downtime_min: String(downtimeVal || '0').trim(),
            downtime_reason: String(reasonVal || 'NONE').trim().toUpperCase(),
            operator_team: 'TEAM-01',
            source_system: 'CLIPBOARD_PASTE',
            data_quality: 'VALID',
            _error: rowErrors.length > 0 ? rowErrors.join('; ') : null,
          });
        }
      }

      setPastePreviewRows(parsedItems);
    } catch (err) {
      setModalError(`Failed to parse text: ${err.message}`);
    }
  };

  // ---------------------------------------------------------------------------
  // SAVE READINGS ACTION (Submits only active type for the modal's plant/date)
  // ---------------------------------------------------------------------------
  const handleSaveReadings = async () => {
    setModalError(null);

    if (modalMode === 'paste') {
      if (pastePreviewRows.length === 0) {
        setModalError('Please paste readings into the text area before saving.');
        return;
      }
      const hasErrors = pastePreviewRows.some((r) => r._error);
      if (hasErrors) {
        setModalError('Please resolve rows with errors highlighted below before saving.');
        return;
      }

      const cleanRows = pastePreviewRows.map(({ _error, ...rest }) => rest);
      const payload =
        modalType === 'energy'
          ? {
              energy_rows: cleanRows,
              production_rows: [],
              reporting_date: modalDate,
              plant_id: modalPlant,
            }
          : {
              energy_rows: [],
              production_rows: cleanRows,
              reporting_date: modalDate,
              plant_id: modalPlant,
            };

      try {
        if (onSave) {
          const res = await onSave('PASTE', payload);
          if (res && res.success === true) {
            setAddModalOpen(false);
            setPasteRawText('');
            setPastePreviewRows([]);
            // Clear draft for this combination
            delete draftsStoreRef.current[`${modalPlant}:${modalDate}:${modalType}`];

            setSaveSuccessMsg(
              `Saved ${cleanRows.length} ${modalType === 'energy' ? 'Energy' : 'Production'} readings for ${modalPlant} (${modalDate}) to database.`
            );

            // Switch page to saved plant/date and reload
            if (onSwitchPlantAndDate) {
              onSwitchPlantAndDate(modalPlant, modalDate);
            }
            if (modalPlant === plantId && modalDate === reportingDate) {
              onReload?.();
            }
          } else {
            // Failure keeps modal open with input intact
            setModalError(res?.message || 'Failed to save readings to database.');
          }
        }
      } catch (err) {
        setModalError(`Save request failed: ${err.message}`);
      }
    } else {
      // Manual entry mode
      if (modalType === 'energy') {
        const errors = {};
        if (!energyDraft.timestamp || !energyDraft.timestamp.trim()) {
          errors.timestamp = 'Hour / Timestamp is required.';
        }
        if (!energyDraft.meter_id) {
          errors.meter_id = 'Please select a meter.';
        }
        if (
          energyDraft.consumption_kwh === '' ||
          energyDraft.consumption_kwh === null ||
          isNaN(Number(energyDraft.consumption_kwh))
        ) {
          errors.consumption_kwh = 'Valid consumption in kWh is required.';
        } else if (Number(energyDraft.consumption_kwh) < 0) {
          errors.consumption_kwh = 'Consumption must be non-negative.';
        }

        if (
          energyDraft.power_factor !== '' &&
          energyDraft.power_factor !== null &&
          (isNaN(Number(energyDraft.power_factor)) ||
            Number(energyDraft.power_factor) < 0 ||
            Number(energyDraft.power_factor) > 1.0)
        ) {
          errors.power_factor = 'Power factor must be between 0.00 and 1.00.';
        }

        if (
          energyDraft.demand_kw !== '' &&
          energyDraft.demand_kw !== null &&
          (isNaN(Number(energyDraft.demand_kw)) || Number(energyDraft.demand_kw) < 0)
        ) {
          errors.demand_kw = 'Demand must be a non-negative number.';
        }

        if (Object.keys(errors).length > 0) {
          setEnergyErrors(errors);
          setModalError('Please correct the highlighted field errors.');
          return;
        }
        setEnergyErrors({});

        const kwhVal = parseFloat(energyDraft.consumption_kwh);
        const tariffVal = energyDraft.tariff_inr_per_kwh ? parseFloat(energyDraft.tariff_inr_per_kwh) : null;
        let costVal = energyDraft.cost_inr;
        if (costVal === '' && !isNaN(kwhVal) && tariffVal !== null && !isNaN(tariffVal)) {
          costVal = (kwhVal * tariffVal).toFixed(2);
        }
        let co2Val = energyDraft.co2e_kg;
        if (co2Val === '' && !isNaN(kwhVal)) {
          co2Val = (kwhVal * 0.716).toFixed(4);
        }

        const recordToSave = {
          timestamp: energyDraft.timestamp.trim(),
          plant_id: modalPlant,
          meter_id: energyDraft.meter_id,
          area: energyDraft.area || meterAreas[energyDraft.meter_id] || 'SMT',
          energy_source: energyDraft.energy_source || 'ELECTRICITY',
          consumption_kwh: energyDraft.consumption_kwh,
          demand_kw:
            energyDraft.demand_kw !== '' && energyDraft.demand_kw !== null && energyDraft.demand_kw !== undefined
              ? energyDraft.demand_kw
              : null,
          power_factor:
            energyDraft.power_factor !== '' && energyDraft.power_factor !== null && energyDraft.power_factor !== undefined
              ? energyDraft.power_factor
              : null,
          tariff_inr_per_kwh: energyDraft.tariff_inr_per_kwh !== '' ? energyDraft.tariff_inr_per_kwh : null,
          cost_inr: costVal !== '' ? costVal : null,
          co2e_kg: co2Val !== '' ? co2Val : null,
          reading_quality: energyDraft.reading_quality || 'VALID',
        };

        try {
          if (onSave) {
            const res = await onSave('MANUAL', {
              energy_rows: [recordToSave],
              production_rows: [],
              reporting_date: modalDate,
              plant_id: modalPlant,
            });

            if (res && res.success === true) {
              setAddModalOpen(false);
              setEditingRecord(null);
              delete draftsStoreRef.current[`${modalPlant}:${modalDate}:energy`];
              setSaveSuccessMsg(`Energy reading saved for ${modalPlant} (${modalDate}) to database.`);

              if (onSwitchPlantAndDate) {
                onSwitchPlantAndDate(modalPlant, modalDate);
              }
              if (modalPlant === plantId && modalDate === reportingDate) {
                onReload?.();
              }
            } else {
              setModalError(res?.message || 'Failed to save energy record.');
            }
          }
        } catch (err) {
          setModalError(`Save request failed: ${err.message}`);
        }
      } else {
        // Production manual
        const errors = {};
        if (!prodDraft.event_ts || !prodDraft.event_ts.trim()) {
          errors.event_ts = 'Hour / Timestamp is required.';
        }
        if (!prodDraft.line_id) {
          errors.line_id = 'Please select a production line.';
        }
        if (!prodDraft.product_id) {
          errors.product_id = 'Please select a product SKU.';
        }
        if (
          prodDraft.actual_qty === '' ||
          isNaN(parseInt(prodDraft.actual_qty, 10)) ||
          parseInt(prodDraft.actual_qty, 10) < 0
        ) {
          errors.actual_qty = 'Valid actual units produced is required.';
        }
        if (
          prodDraft.good_qty === '' ||
          isNaN(parseInt(prodDraft.good_qty, 10)) ||
          parseInt(prodDraft.good_qty, 10) < 0
        ) {
          errors.good_qty = 'Valid good units is required.';
        } else if (parseInt(prodDraft.good_qty, 10) > parseInt(prodDraft.actual_qty || '0', 10)) {
          errors.good_qty = 'Good units cannot exceed actual units produced.';
        }

        if (Object.keys(errors).length > 0) {
          setProdErrors(errors);
          setModalError('Please correct the highlighted field errors.');
          return;
        }
        setProdErrors({});

        const actualUnits = parseInt(prodDraft.actual_qty, 10);
        const goodUnits = parseInt(prodDraft.good_qty, 10);
        const rejectUnits =
          prodDraft.reject_qty !== '' ? prodDraft.reject_qty : String(Math.max(0, actualUnits - goodUnits));

        const recordToSave = {
          event_ts: prodDraft.event_ts.trim(),
          plant_id: modalPlant,
          line_id: prodDraft.line_id,
          shift_id: prodDraft.shift_id || 'A',
          product_id: prodDraft.product_id,
          production_order_id: prodDraft.production_order_id || `PO-${modalDate.replace(/-/g, '')}-01`,
          target_qty: prodDraft.target_qty !== '' ? prodDraft.target_qty : null,
          actual_qty: prodDraft.actual_qty,
          good_qty: prodDraft.good_qty,
          reject_qty: rejectUnits,
          rework_qty: prodDraft.rework_qty !== '' ? prodDraft.rework_qty : '0',
          downtime_min: prodDraft.downtime_min !== '' ? prodDraft.downtime_min : '0',
          downtime_reason: prodDraft.downtime_reason || 'NONE',
          operator_team: prodDraft.operator_team || 'TEAM-01',
          source_system: 'MANUAL_ENTRY',
          data_quality: 'VALID',
        };

        try {
          if (onSave) {
            const res = await onSave('MANUAL', {
              energy_rows: [],
              production_rows: [recordToSave],
              reporting_date: modalDate,
              plant_id: modalPlant,
            });

            if (res && res.success === true) {
              setAddModalOpen(false);
              setEditingRecord(null);
              delete draftsStoreRef.current[`${modalPlant}:${modalDate}:production`];
              setSaveSuccessMsg(`Production reading saved for ${modalPlant} (${modalDate}) to database.`);

              if (onSwitchPlantAndDate) {
                onSwitchPlantAndDate(modalPlant, modalDate);
              }
              if (modalPlant === plantId && modalDate === reportingDate) {
                onReload?.();
              }
            } else {
              setModalError(res?.message || 'Failed to save production record.');
            }
          }
        } catch (err) {
          setModalError(`Save request failed: ${err.message}`);
        }
      }
    }
  };

  // Edit existing record from View Saved Entries modal
  const handleEditSavedRecord = (tab, index) => {
    setViewSavedModalOpen(false);
    setModalType(tab);
    setModalMode('manual');
    setEditingRecord({ tab, index });

    if (tab === 'energy') {
      const row = energyRows[index];
      if (row) {
        setEnergyDraft({
          timestamp: row.timestamp || `${reportingDate} 00:00`,
          meter_id: row.meter_id || meters[0] || 'MTR-SMT',
          area: row.area || meterAreas[row.meter_id] || 'SMT',
          energy_source: row.energy_source || 'ELECTRICITY',
          consumption_kwh: row.consumption_kwh !== undefined && row.consumption_kwh !== null ? String(row.consumption_kwh) : '',
          demand_kw: row.demand_kw !== undefined && row.demand_kw !== null ? String(row.demand_kw) : '',
          power_factor: row.power_factor !== undefined && row.power_factor !== null ? String(row.power_factor) : '',
          tariff_inr_per_kwh: row.tariff_inr_per_kwh !== undefined && row.tariff_inr_per_kwh !== null ? String(row.tariff_inr_per_kwh) : '8.25',
          cost_inr: row.cost_inr !== undefined && row.cost_inr !== null ? String(row.cost_inr) : '',
          co2e_kg: row.co2e_kg !== undefined && row.co2e_kg !== null ? String(row.co2e_kg) : '',
          reading_quality: row.reading_quality || 'VALID',
        });
      }
    } else {
      const row = productionRows[index];
      if (row) {
        setProdDraft({
          event_ts: row.event_ts || `${reportingDate} 00:00`,
          line_id: row.line_id || lines[0] || 'SMT-L1',
          shift_id: row.shift_id || 'A',
          product_id: row.product_id || products[0] || 'SPH-A15-256',
          production_order_id: row.production_order_id || `PO-${reportingDate.replace(/-/g, '')}-01`,
          target_qty: row.target_qty !== undefined && row.target_qty !== null ? String(row.target_qty) : '',
          actual_qty: row.actual_qty !== undefined && row.actual_qty !== null ? String(row.actual_qty) : '',
          good_qty: row.good_qty !== undefined && row.good_qty !== null ? String(row.good_qty) : '',
          reject_qty: row.reject_qty !== undefined && row.reject_qty !== null ? String(row.reject_qty) : '',
          rework_qty: row.rework_qty !== undefined && row.rework_qty !== null ? String(row.rework_qty) : '0',
          downtime_min: row.downtime_min !== undefined && row.downtime_min !== null ? String(row.downtime_min) : '0',
          downtime_reason: row.downtime_reason || 'NONE',
          operator_team: row.operator_team || 'TEAM-01',
          source_system: row.source_system || 'MANUAL_ENTRY',
          data_quality: row.data_quality || 'VALID',
        });
      }
    }
    setAddModalOpen(true);
  };

  const hasLoadedCounts = !loadingSaved && savedCounts !== null;
  const totalSavedEnergy = savedCounts?.energy ?? 0;
  const totalSavedProduction = savedCounts?.production ?? 0;

  return (
    <div className="daily-ops-data-entry-container">
      {/* 1. Single-line Data Entry Bar (No nested card, no repeated plant/date chips) */}
      <div className="daily-ops-stage1-bar">
        <div className="daily-ops-summary-counts">
          <span className={`daily-ops-summary-dot ${loadingSaved ? 'loading' : ''}`} aria-hidden="true" />
          <span className="daily-ops-summary-counts-text">
            {!hasLoadedCounts ? (
              'Loading entries…'
            ) : (
              <>
                Database-confirmed: <strong>{totalSavedEnergy}</strong> Energy entries · <strong>{totalSavedProduction}</strong> Production entries
              </>
            )}
          </span>
        </div>

        <div className="daily-ops-summary-actions">
          {/* Primary Action: Add readings */}
          <button
            type="button"
            className="daily-ops-btn daily-ops-btn-primary daily-ops-add-readings-btn"
            onClick={() => handleOpenAddReadings('energy', 'paste')}
            title="Open modal to paste or manually enter energy and production readings"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            <span>Add readings</span>
          </button>

          {/* Secondary Action: View Saved Entries */}
          <button
            type="button"
            className="daily-ops-btn daily-ops-btn-secondary"
            onClick={() => setViewSavedModalOpen(true)}
            title="Inspect saved database records and select any record to edit"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
            </svg>
            <span>View saved entries</span>
          </button>
        </div>
      </div>

      {/* Global Success Banner */}
      {saveSuccessMsg && (
        <div className="daily-ops-alert-banner info" style={{ marginTop: '0.75rem' }} role="status">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
            <polyline points="22 4 12 14.01 9 11.01" />
          </svg>
          <span>{saveSuccessMsg}</span>
        </div>
      )}

      {/* 2. "ADD READINGS" MODAL */}
      {addModalOpen && (
        <div
          className="daily-ops-modal-backdrop"
          onClick={handleCancelModal}
          role="dialog"
          aria-modal="true"
          aria-labelledby="add-readings-modal-title"
        >
          <div className="daily-ops-add-modal-card" onClick={(e) => e.stopPropagation()}>
            {/* Modal Header */}
            <div className="daily-ops-modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <div className="ps-ref-header-icon ps-icon-purple" style={{ width: '26px', height: '26px' }} aria-hidden="true">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                    <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
                  </svg>
                </div>
                <h3 id="add-readings-modal-title" className="daily-ops-modal-title">
                  {editingRecord ? `Edit ${modalType === 'energy' ? 'Energy' : 'Production'} Record #${editingRecord.index + 1}` : 'Add readings'}
                </h3>
              </div>
              <button
                type="button"
                className="daily-ops-modal-close"
                onClick={handleCancelModal}
                aria-label="Close modal"
              >
                ✕
              </button>
            </div>

            {/* Modal Body */}
            <div className="daily-ops-add-modal-body">
              {/* Row 1: Plant dropdown and Reporting date picker */}
              <div className="daily-ops-modal-row-1">
                <div className="daily-ops-field-group">
                  <label className="daily-ops-field-label" htmlFor="modal-plant-select">
                    Plant <span className="req">*</span>
                  </label>
                  <select
                    id="modal-plant-select"
                    className="daily-ops-field-select"
                    value={modalPlant}
                    onChange={(e) => handleModalPlantChange(e.target.value)}
                  >
                    {PLANT_OPTIONS.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="daily-ops-field-group">
                  <label className="daily-ops-field-label" htmlFor="modal-date-input">
                    Reporting date <span className="req">*</span>
                  </label>
                  <input
                    id="modal-date-input"
                    type="date"
                    className="daily-ops-field-input"
                    value={modalDate}
                    min="2026-01-01"
                    max="2030-12-31"
                    onChange={(e) => handleModalDateChange(e.target.value)}
                  />
                </div>
              </div>

              {/* Row 2: Energy / Production selector & Mode selector */}
              <div className="daily-ops-modal-row-2">
                {/* Type Selector (Energy vs Production) */}
                <div className="daily-ops-tab-nav" role="tablist">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={modalType === 'energy'}
                    className={`daily-ops-tab-btn ${modalType === 'energy' ? 'active' : ''}`}
                    onClick={() => handleModalTypeChange('energy')}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
                      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
                    </svg>
                    <span>Energy Telemetry</span>
                  </button>

                  <button
                    type="button"
                    role="tab"
                    aria-selected={modalType === 'production'}
                    className={`daily-ops-tab-btn ${modalType === 'production' ? 'active' : ''}`}
                    onClick={() => handleModalTypeChange('production')}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
                      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
                    </svg>
                    <span>Production Output</span>
                  </button>
                </div>

                {/* Entry Mode Selector (Default to Paste readings; Enter manually as secondary) */}
                <div className="daily-ops-tab-nav" style={{ background: 'var(--bg-hover, #f1f5f9)' }}>
                  <button
                    type="button"
                    className={`daily-ops-tab-btn ${modalMode === 'paste' ? 'active' : ''}`}
                    style={{ fontSize: '12px', padding: '0.25rem 0.65rem' }}
                    onClick={() => handleModalModeChange('paste')}
                  >
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                      <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
                      <rect x="8" y="2" width="8" height="4" rx="1" ry="1" />
                    </svg>
                    <span>Paste readings</span>
                  </button>

                  <button
                    type="button"
                    className={`daily-ops-tab-btn ${modalMode === 'manual' ? 'active' : ''}`}
                    style={{ fontSize: '12px', padding: '0.25rem 0.65rem' }}
                    onClick={() => handleModalModeChange('manual')}
                  >
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                    </svg>
                    <span>Enter manually</span>
                  </button>
                </div>
              </div>

              {/* Modal Error Banner */}
              {modalError && (
                <div className="daily-ops-alert-banner error" style={{ padding: '0.5rem 0.75rem' }} role="alert">
                  <strong>Save Error:</strong> {modalError}
                </div>
              )}

              {/* Input Area */}
              {modalMode === 'paste' ? (
                /* PASTE READINGS (DEFAULT MODE) */
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  <textarea
                    rows="7"
                    className="daily-ops-paste-textarea"
                    placeholder={
                      modalType === 'energy'
                        ? `Paste Excel or CSV cells for Energy...\nExample:\nTimestamp\tMeter\tConsumption_kWh\tDemand_kW\tPower_Factor\n${modalDate} 00:00\t${meters[0] || 'MTR-SMT'}\t125.40\t115.20\t0.95\n${modalDate} 01:00\t${meters[0] || 'MTR-SMT'}\t118.80\t\t`
                        : `Paste Excel or CSV cells for Production...\nExample:\nEvent_TS\tLine\tShift\tProduct\tActual_Qty\tGood_Qty\tReject_Qty\tDowntime\n${modalDate} 00:00\t${lines[0] || 'SMT-L1'}\tA\t${products[0] || 'SPH-A15-256'}\t300\t295\t5\t0\n${modalDate} 01:00\t${lines[0] || 'SMT-L1'}\tA\t${products[0] || 'SPH-A15-256'}\t310\t302\t8\t0`
                    }
                    value={pasteRawText}
                    onChange={(e) => handleParsePasteText(e.target.value)}
                  />
                </div>
              ) : (
                /* ENTER MANUALLY (SECONDARY MODE) */
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  {modalType === 'energy' ? (
                    /* Energy Manual Form */
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                      <div className="daily-ops-form-grid-2col">
                        <div className="daily-ops-field-group">
                          <label className="daily-ops-field-label">
                            Hour / Timestamp <span className="req">*</span>
                          </label>
                          <input
                            type="text"
                            className={`daily-ops-field-input ${energyErrors.timestamp ? 'has-error' : ''}`}
                            value={energyDraft.timestamp}
                            placeholder={`${modalDate} 00:00`}
                            onChange={(e) => handleEnergyChange('timestamp', e.target.value)}
                          />
                          {energyErrors.timestamp && (
                            <span className="daily-ops-inline-error">{energyErrors.timestamp}</span>
                          )}
                        </div>

                        <div className="daily-ops-field-group">
                          <label className="daily-ops-field-label">
                            Meter <span className="req">*</span>
                          </label>
                          <select
                            className={`daily-ops-field-select ${energyErrors.meter_id ? 'has-error' : ''}`}
                            value={energyDraft.meter_id}
                            onChange={(e) => handleEnergyChange('meter_id', e.target.value)}
                          >
                            {meters.map((m) => (
                              <option key={m} value={m}>
                                {m} ({meterAreas[m] || 'SMT'})
                              </option>
                            ))}
                          </select>
                          {energyErrors.meter_id && (
                            <span className="daily-ops-inline-error">{energyErrors.meter_id}</span>
                          )}
                        </div>
                      </div>

                      <div className="daily-ops-form-grid-3col">
                        <div className="daily-ops-field-group">
                          <label className="daily-ops-field-label">
                            Consumption (kWh) <span className="req">*</span>
                          </label>
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            className={`daily-ops-field-input ${energyErrors.consumption_kwh ? 'has-error' : ''}`}
                            placeholder="e.g. 125.40"
                            value={energyDraft.consumption_kwh}
                            onChange={(e) => handleEnergyChange('consumption_kwh', e.target.value)}
                          />
                          {energyErrors.consumption_kwh && (
                            <span className="daily-ops-inline-error">{energyErrors.consumption_kwh}</span>
                          )}
                        </div>

                        <div className="daily-ops-field-group">
                          <label className="daily-ops-field-label">Demand (kW)</label>
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            className={`daily-ops-field-input ${energyErrors.demand_kw ? 'has-error' : ''}`}
                            placeholder="e.g. 115.20 (Optional)"
                            value={energyDraft.demand_kw}
                            onChange={(e) => handleEnergyChange('demand_kw', e.target.value)}
                          />
                          {energyErrors.demand_kw && (
                            <span className="daily-ops-inline-error">{energyErrors.demand_kw}</span>
                          )}
                        </div>

                        <div className="daily-ops-field-group">
                          <label className="daily-ops-field-label">Power factor</label>
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            max="1.0"
                            className={`daily-ops-field-input ${energyErrors.power_factor ? 'has-error' : ''}`}
                            placeholder="e.g. 0.95 (Optional)"
                            value={energyDraft.power_factor}
                            onChange={(e) => handleEnergyChange('power_factor', e.target.value)}
                          />
                          {energyErrors.power_factor && (
                            <span className="daily-ops-inline-error">{energyErrors.power_factor}</span>
                          )}
                        </div>
                      </div>

                      <details className="daily-ops-form-details">
                        <summary>More details (Tariff, Estimated Cost, Emissions, Quality)</summary>
                        <div className="daily-ops-form-details-body">
                          <div className="daily-ops-form-grid-4col">
                            <div className="daily-ops-field-group">
                              <label className="daily-ops-field-label">Tariff (₹/kWh)</label>
                              <input
                                type="number"
                                step="0.01"
                                className="daily-ops-field-input"
                                value={energyDraft.tariff_inr_per_kwh}
                                onChange={(e) => handleEnergyChange('tariff_inr_per_kwh', e.target.value)}
                              />
                            </div>
                            <div className="daily-ops-field-group">
                              <label className="daily-ops-field-label">Cost (₹)</label>
                              <input
                                type="number"
                                step="0.01"
                                className="daily-ops-field-input"
                                value={energyDraft.cost_inr}
                                onChange={(e) => handleEnergyChange('cost_inr', e.target.value)}
                              />
                            </div>
                            <div className="daily-ops-field-group">
                              <label className="daily-ops-field-label">CO₂e (kg)</label>
                              <input
                                type="number"
                                step="0.0001"
                                className="daily-ops-field-input"
                                value={energyDraft.co2e_kg}
                                onChange={(e) => handleEnergyChange('co2e_kg', e.target.value)}
                              />
                            </div>
                            <div className="daily-ops-field-group">
                              <label className="daily-ops-field-label">Reading Quality</label>
                              <select
                                className="daily-ops-field-select"
                                value={energyDraft.reading_quality}
                                onChange={(e) => handleEnergyChange('reading_quality', e.target.value)}
                              >
                                <option value="VALID">VALID</option>
                                <option value="ESTIMATED">ESTIMATED</option>
                                <option value="SUSPECT">SUSPECT</option>
                              </select>
                            </div>
                          </div>
                        </div>
                      </details>
                    </div>
                  ) : (
                    /* Production Manual Form */
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                      <div className="daily-ops-form-grid-4col">
                        <div className="daily-ops-field-group">
                          <label className="daily-ops-field-label">
                            Hour / Timestamp <span className="req">*</span>
                          </label>
                          <input
                            type="text"
                            className={`daily-ops-field-input ${prodErrors.event_ts ? 'has-error' : ''}`}
                            value={prodDraft.event_ts}
                            placeholder={`${modalDate} 00:00`}
                            onChange={(e) => handleProdChange('event_ts', e.target.value)}
                          />
                          {prodErrors.event_ts && (
                            <span className="daily-ops-inline-error">{prodErrors.event_ts}</span>
                          )}
                        </div>

                        <div className="daily-ops-field-group">
                          <label className="daily-ops-field-label">
                            Production line <span className="req">*</span>
                          </label>
                          <select
                            className={`daily-ops-field-select ${prodErrors.line_id ? 'has-error' : ''}`}
                            value={prodDraft.line_id}
                            onChange={(e) => handleProdChange('line_id', e.target.value)}
                          >
                            {lines.map((l) => (
                              <option key={l} value={l}>
                                {l}
                              </option>
                            ))}
                          </select>
                          {prodErrors.line_id && (
                            <span className="daily-ops-inline-error">{prodErrors.line_id}</span>
                          )}
                        </div>

                        <div className="daily-ops-field-group">
                          <label className="daily-ops-field-label">
                            Shift <span className="req">*</span>
                          </label>
                          <select
                            className="daily-ops-field-select"
                            value={prodDraft.shift_id}
                            onChange={(e) => handleProdChange('shift_id', e.target.value)}
                          >
                            <option value="A">Shift A (Morning)</option>
                            <option value="B">Shift B (Evening)</option>
                            <option value="C">Shift C (Night)</option>
                          </select>
                        </div>

                        <div className="daily-ops-field-group">
                          <label className="daily-ops-field-label">
                            Product SKU <span className="req">*</span>
                          </label>
                          <select
                            className={`daily-ops-field-select ${prodErrors.product_id ? 'has-error' : ''}`}
                            value={prodDraft.product_id}
                            onChange={(e) => handleProdChange('product_id', e.target.value)}
                          >
                            {products.map((p) => (
                              <option key={p} value={p}>
                                {p}
                              </option>
                            ))}
                          </select>
                          {prodErrors.product_id && (
                            <span className="daily-ops-inline-error">{prodErrors.product_id}</span>
                          )}
                        </div>
                      </div>

                      <div className="daily-ops-form-grid-3col">
                        <div className="daily-ops-field-group">
                          <label className="daily-ops-field-label">
                            Actual units <span className="req">*</span>
                          </label>
                          <input
                            type="number"
                            min="0"
                            step="1"
                            className={`daily-ops-field-input ${prodErrors.actual_qty ? 'has-error' : ''}`}
                            placeholder="e.g. 300"
                            value={prodDraft.actual_qty}
                            onChange={(e) => handleProdChange('actual_qty', e.target.value)}
                          />
                          {prodErrors.actual_qty && (
                            <span className="daily-ops-inline-error">{prodErrors.actual_qty}</span>
                          )}
                        </div>

                        <div className="daily-ops-field-group">
                          <label className="daily-ops-field-label">
                            Good units <span className="req">*</span>
                          </label>
                          <input
                            type="number"
                            min="0"
                            step="1"
                            className={`daily-ops-field-input ${prodErrors.good_qty ? 'has-error' : ''}`}
                            placeholder="e.g. 295"
                            value={prodDraft.good_qty}
                            onChange={(e) => handleProdChange('good_qty', e.target.value)}
                          />
                          {prodErrors.good_qty && (
                            <span className="daily-ops-inline-error">{prodErrors.good_qty}</span>
                          )}
                        </div>

                        <div className="daily-ops-field-group">
                          <label className="daily-ops-field-label">Reject units</label>
                          <input
                            type="number"
                            min="0"
                            step="1"
                            className="daily-ops-field-input"
                            placeholder="e.g. 5"
                            value={prodDraft.reject_qty}
                            onChange={(e) => handleProdChange('reject_qty', e.target.value)}
                          />
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Expected Columns Box */}
              <div className="daily-ops-expected-cols-box">
                <div className="daily-ops-expected-cols-title">
                  Expected Columns for {modalType === 'energy' ? 'Energy Telemetry' : 'Production Output'}:
                </div>
                <div className="daily-ops-expected-cols-code">
                  {modalType === 'energy'
                    ? 'Timestamp (YYYY-MM-DD HH:MM), Meter ID, Consumption (kWh), Demand (kW - optional), Power factor (0.00-1.00 - optional)'
                    : 'Timestamp (YYYY-MM-DD HH:MM), Line ID, Shift (A/B/C), Product SKU, Actual units, Good units, Reject units, Downtime (min), Reason'}
                </div>
              </div>

              {/* Compact Preview Table & Errors */}
              {modalMode === 'paste' && pastePreviewRows.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px', fontWeight: 600 }}>
                    <span>Preview ({pastePreviewRows.length} rows parsed):</span>
                    {pastePreviewRows.some((r) => r._error) && (
                      <span style={{ color: '#ef4444', fontSize: '11px' }}>
                        ⚠️ Resolve errors highlighted in red before saving
                      </span>
                    )}
                  </div>
                  <div style={{ maxHeight: '180px', overflowY: 'auto', border: '1px solid var(--border-color, #e2e8f0)', borderRadius: '6px' }}>
                    <table className="daily-ops-editable-table" style={{ margin: 0 }}>
                      <thead>
                        <tr>
                          <th>#</th>
                          <th>Timestamp</th>
                          <th>{modalType === 'energy' ? 'Meter' : 'Line'}</th>
                          <th>{modalType === 'energy' ? 'Consumption (kWh)' : 'Actual / Good'}</th>
                          <th>{modalType === 'energy' ? 'PF' : 'Product'}</th>
                          <th>Status / Error</th>
                        </tr>
                      </thead>
                      <tbody>
                        {pastePreviewRows.slice(0, 15).map((r, i) => (
                          <tr key={i} style={{ backgroundColor: r._error ? '#fef2f2' : undefined }}>
                            <td className="row-num-cell">{i + 1}</td>
                            <td>{r.timestamp || r.event_ts}</td>
                            <td>{r.meter_id || r.line_id}</td>
                            <td>{modalType === 'energy' ? (r.consumption_kwh || '—') : `${r.actual_qty || '—'} / ${r.good_qty || '—'}`}</td>
                            <td>{modalType === 'energy' ? (r.power_factor || '—') : r.product_id}</td>
                            <td>
                              {r._error ? (
                                <span style={{ color: '#dc2626', fontSize: '11px', fontWeight: 600 }}>
                                  ⚠️ {r._error}
                                </span>
                              ) : (
                                <span style={{ color: '#16a34a', fontSize: '11px', fontWeight: 600 }}>
                                  ✓ Valid
                                </span>
                              )}
                            </td>
                          </tr>
                        ))}
                        {pastePreviewRows.length > 15 && (
                          <tr>
                            <td colSpan="6" style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '11px', padding: '5px' }}>
                              ...and {pastePreviewRows.length - 15} more rows
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>

            {/* Sticky Footer: Cancel and Save readings (Always visible if body scrolls) */}
            <div className="daily-ops-add-modal-footer">
              <div className="daily-ops-modal-row-count-badge">
                {modalMode === 'paste'
                  ? `${pastePreviewRows.length} ${modalType === 'energy' ? 'Energy' : 'Production'} rows ready to save`
                  : `1 ${modalType === 'energy' ? 'Energy' : 'Production'} record ready to save`}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <button
                  type="button"
                  className="daily-ops-btn daily-ops-btn-secondary"
                  onClick={handleCancelModal}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="daily-ops-btn daily-ops-btn-primary"
                  onClick={handleSaveReadings}
                  disabled={
                    saving ||
                    (modalMode === 'paste' && (pastePreviewRows.length === 0 || pastePreviewRows.some((r) => r._error)))
                  }
                >
                  {saving ? 'Saving readings…' : 'Save readings'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 3. "VIEW SAVED ENTRIES" MODAL / DRAWER */}
      {viewSavedModalOpen && (
        <div
          className="daily-ops-modal-backdrop"
          onClick={() => setViewSavedModalOpen(false)}
          role="dialog"
          aria-modal="true"
          aria-labelledby="view-saved-modal-title"
        >
          <div
            className="daily-ops-modal-card"
            style={{ maxWidth: '920px', width: '92%', maxHeight: '85vh' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="daily-ops-modal-header">
              <h3 id="view-saved-modal-title" className="daily-ops-modal-title">
                Saved Database Records — {plantId} ({reportingDate})
              </h3>
              <button
                type="button"
                className="daily-ops-modal-close"
                onClick={() => setViewSavedModalOpen(false)}
                aria-label="Close modal"
              >
                ✕
              </button>
            </div>

            <div className="daily-ops-modal-body" style={{ overflowY: 'auto' }}>
              {/* Type Switcher inside Saved Records Viewer */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                <div className="daily-ops-tab-nav" role="tablist">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={modalType === 'energy'}
                    className={`daily-ops-tab-btn ${modalType === 'energy' ? 'active' : ''}`}
                    onClick={() => setModalType('energy')}
                  >
                    <span>Energy Telemetry ({totalSavedEnergy})</span>
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={modalType === 'production'}
                    className={`daily-ops-tab-btn ${modalType === 'production' ? 'active' : ''}`}
                    onClick={() => setModalType('production')}
                  >
                    <span>Production Output ({totalSavedProduction})</span>
                  </button>
                </div>

                <button
                  type="button"
                  className="daily-ops-btn daily-ops-btn-primary"
                  onClick={() => {
                    setViewSavedModalOpen(false);
                    handleOpenAddReadings(modalType, 'paste');
                  }}
                >
                  + Add more readings
                </button>
              </div>

              {modalType === 'energy' ? (
                /* Energy Saved Table */
                energyRows.length === 0 ? (
                  <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                    No energy records saved in database for this plant and date.
                  </div>
                ) : (
                  <table className="daily-ops-editable-table">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Timestamp</th>
                        <th>Meter</th>
                        <th>Consumption (kWh)</th>
                        <th>Demand (kW)</th>
                        <th>Power Factor</th>
                        <th>Quality</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {energyRows.map((r, i) => (
                        <tr key={i}>
                          <td className="row-num-cell">{i + 1}</td>
                          <td>{r.timestamp}</td>
                          <td><strong>{r.meter_id}</strong></td>
                          <td>{formatNumber(r.consumption_kwh, 2)}</td>
                          <td>{r.demand_kw !== null && r.demand_kw !== undefined ? formatNumber(r.demand_kw, 2) : '—'}</td>
                          <td>{r.power_factor !== null && r.power_factor !== undefined ? formatNumber(r.power_factor, 2) : '—'}</td>
                          <td><span className="daily-ops-quality-pill valid">{r.reading_quality || 'VALID'}</span></td>
                          <td>
                            <button
                              type="button"
                              className="daily-ops-row-action-btn"
                              onClick={() => handleEditSavedRecord('energy', i)}
                              title="Edit this record in modal"
                            >
                              Edit
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )
              ) : (
                /* Production Saved Table */
                productionRows.length === 0 ? (
                  <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                    No production records saved in database for this plant and date.
                  </div>
                ) : (
                  <table className="daily-ops-editable-table">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Timestamp</th>
                        <th>Line</th>
                        <th>Shift</th>
                        <th>Product SKU</th>
                        <th>Actual</th>
                        <th>Good</th>
                        <th>Rejects</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {productionRows.map((r, i) => (
                        <tr key={i}>
                          <td className="row-num-cell">{i + 1}</td>
                          <td>{r.event_ts}</td>
                          <td><strong>{r.line_id}</strong></td>
                          <td>Shift {r.shift_id}</td>
                          <td>{r.product_id}</td>
                          <td>{formatNumber(r.actual_qty, 0)}</td>
                          <td>{formatNumber(r.good_qty, 0)}</td>
                          <td>{formatNumber(r.reject_qty, 0)}</td>
                          <td>
                            <button
                              type="button"
                              className="daily-ops-row-action-btn"
                              onClick={() => handleEditSavedRecord('production', i)}
                              title="Edit this record in modal"
                            >
                              Edit
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )
              )}
            </div>

            <div className="daily-ops-modal-footer">
              <button
                type="button"
                className="daily-ops-btn daily-ops-btn-secondary"
                onClick={() => setViewSavedModalOpen(false)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
