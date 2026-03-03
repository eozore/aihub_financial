'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import AppShell from '@/components/AppShell';
import { useAuth } from '@/context/AuthContext';
import {
  getNetWorth,
  getNetWorthValidation,
  NetWorthSnapshot,
  NetWorthValidationRow,
  updateNetWorthRow,
  getOwners,
} from '@/services/api';
import { ArrowRight, Loader, Pencil, Save, UploadCloud, Wallet, X } from 'lucide-react';
import clsx from 'clsx';
import { Area, AreaChart, Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

const PRIMARY_CHART_COLOR = '#4338ca';

const formatCurrency = (value: number) =>
  `R$ ${Number(value || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`;

const toInputValue = (value?: number | null) =>
  value === null || value === undefined || Number.isNaN(value) ? '' : String(value);

const toOptionalNumber = (value: string): number | undefined => {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  const parsed = Number(trimmed.replace(',', '.'));
  if (Number.isNaN(parsed)) return undefined;
  return parsed;
};

const formatMonthLabel = (monthRef: string) => {
  if (!monthRef) return '';
  const [year, month] = monthRef.split('-');
  const date = new Date(parseInt(year, 10), parseInt(month, 10) - 1, 1);
  return date.toLocaleDateString('pt-BR', { month: 'short', year: '2-digit' }).replace('.', '');
};

const MoneyTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    const value = Number(payload[0].value || 0);
    return (
      <div className="bg-white border border-[var(--border-color)] rounded-lg p-3 shadow-lg text-sm">
        <p className="font-medium text-[var(--text-secondary)] text-xs">{formatMonthLabel(label)}</p>
        <p className="text-[var(--brand-primary)] font-semibold">{formatCurrency(value)}</p>
      </div>
    );
  }
  return null;
};

const CashflowTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    const value = Number(payload[0].value || 0);
    const color = value >= 0 ? 'text-emerald-700' : 'text-rose-700';
    return (
      <div className="bg-white border border-[var(--border-color)] rounded-lg p-3 shadow-lg text-sm">
        <p className="font-medium text-[var(--text-secondary)] text-xs">{formatMonthLabel(label)}</p>
        <p className={clsx('font-semibold', color)}>{formatCurrency(value)}</p>
      </div>
    );
  }
  return null;
};

export default function PatrimonioPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  const now = new Date();
  const currentMonth = now.toISOString().slice(0, 7);
  const defaultStartDate = new Date(now.getFullYear(), now.getMonth() - 23, 1);
  const defaultStartMonth = defaultStartDate.toISOString().slice(0, 7);

  const [ownerFilter, setOwnerFilter] = useState('');
  const [owners, setOwners] = useState<string[]>([]);
  const [startMonth, setStartMonth] = useState(defaultStartMonth);
  const [endMonth, setEndMonth] = useState(currentMonth);
  const [loadingData, setLoadingData] = useState(false);

  useEffect(() => {
    getOwners().then((list) => {
      setOwners(list);
      if (list.length > 0 && !ownerFilter) setOwnerFilter(list[0]);
    }).catch(() => {
      setOwners(['Victor', 'Larissa']);
      if (!ownerFilter) setOwnerFilter('Victor');
    });
  }, []);
  const [savingRow, setSavingRow] = useState(false);
  const [snapshots, setSnapshots] = useState<NetWorthSnapshot[]>([]);
  const [validationRows, setValidationRows] = useState<NetWorthValidationRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editingMonth, setEditingMonth] = useState<string | null>(null);
  const [editIncome, setEditIncome] = useState('');
  const [editExpense, setEditExpense] = useState('');
  const [editNetWorth, setEditNetWorth] = useState('');
  const [editNotes, setEditNotes] = useState('');

  useEffect(() => {
    if (!loading && !user) {
      router.push('/login');
    }
  }, [loading, router, user]);

  const fetchData = async () => {
    setLoadingData(true);
    setError(null);
    try {
      const [netWorthResult, validationResult] = await Promise.all([
        getNetWorth(startMonth, endMonth, ownerFilter),
        getNetWorthValidation(ownerFilter, startMonth, endMonth),
      ]);
      setSnapshots(netWorthResult.data || []);
      setValidationRows(validationResult.data || []);
    } catch (fetchError: any) {
      setError(fetchError?.response?.data?.detail || 'Erro ao carregar patrimônio.');
      setSnapshots([]);
      setValidationRows([]);
    } finally {
      setLoadingData(false);
    }
  };

  useEffect(() => {
    if (!user) return;
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, ownerFilter, startMonth, endMonth]);

  const sorted = useMemo(() => {
    const copy = [...(snapshots || [])];
    copy.sort((a, b) => (a.month_ref || '').localeCompare(b.month_ref || ''));
    return copy;
  }, [snapshots]);

  const validationByMonth = useMemo(() => {
    const map = new Map<string, NetWorthValidationRow>();
    for (const row of validationRows || []) {
      map.set(row.month_ref, row);
    }
    return map;
  }, [validationRows]);

  const chartData = useMemo(
    () =>
      sorted
        .filter((row) => typeof row.net_worth_total === 'number' && !Number.isNaN(Number(row.net_worth_total)))
        .map((row) => ({
          month_ref: row.month_ref,
          net_worth_total: Number(row.net_worth_total || 0),
          net_cashflow: Number(row.income_total || 0) - Number(row.expense_total || 0),
        })),
    [sorted]
  );

  const cashflowData = useMemo(
    () =>
      sorted
        .filter((row) => typeof row.income_total === 'number' && typeof row.expense_total === 'number')
        .map((row) => ({
          month_ref: row.month_ref,
          net_cashflow: Number(row.income_total || 0) - Number(row.expense_total || 0),
        })),
    [sorted]
  );

  const latest = chartData[chartData.length - 1];
  const previous = chartData.length >= 2 ? chartData[chartData.length - 2] : undefined;
  const currentNetWorth = latest?.net_worth_total || 0;
  const momDelta = previous ? currentNetWorth - (previous.net_worth_total || 0) : 0;
  const momPct = previous?.net_worth_total ? momDelta / previous.net_worth_total : null;
  const periodDelta = chartData.length ? currentNetWorth - (chartData[0].net_worth_total || 0) : 0;

  const startEditing = (row: NetWorthSnapshot) => {
    setEditingMonth(row.month_ref);
    setEditIncome(toInputValue(row.income_total));
    setEditExpense(toInputValue(row.expense_total));
    setEditNetWorth(toInputValue(row.net_worth_total));
    setEditNotes(row.notes || '');
  };

  const applySuggestion = (monthRef: string) => {
    const suggested = validationByMonth.get(monthRef);
    if (!suggested) return;
    setEditIncome(toInputValue(suggested.suggested_income_total));
    setEditExpense(toInputValue(suggested.suggested_expense_total));
  };

  const saveEditing = async () => {
    if (!editingMonth) return;
    setSavingRow(true);
    setError(null);
    try {
      await updateNetWorthRow(editingMonth, ownerFilter, {
        income_total: toOptionalNumber(editIncome),
        expense_total: toOptionalNumber(editExpense),
        net_worth_total: toOptionalNumber(editNetWorth),
        notes: editNotes || undefined,
      });
      setEditingMonth(null);
      await fetchData();
    } catch (saveError: any) {
      setError(saveError?.response?.data?.detail || 'Erro ao salvar edição manual.');
    } finally {
      setSavingRow(false);
    }
  };

  if (loading || !user) return null;

  return (
    <AppShell>
      <div className="flex flex-col gap-4 mb-8">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="page-header mb-0">
            <h1 className="page-title">Patrimônio</h1>
            <p className="page-subtitle">Evolução do patrimônio e validação mensal ({ownerFilter})</p>
          </div>

          <div className="w-full sm:w-auto flex flex-col sm:flex-row items-stretch sm:items-end gap-2 bg-white p-3 rounded-xl border border-[var(--border-color)] shadow-sm">
            <div className="min-w-0">
              <label className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] block">Pessoa</label>
              <select
                value={ownerFilter}
                onChange={(e) => setOwnerFilter(e.target.value)}
                className="input py-1.5 px-2 text-sm w-full sm:w-36"
              >
                {owners.map((owner) => (
                  <option key={owner} value={owner}>
                    {owner}
                  </option>
                ))}
              </select>
            </div>
            <div className="min-w-0">
              <label className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] block">Início</label>
              <input
                type="month"
                value={startMonth}
                onChange={(e) => setStartMonth(e.target.value)}
                className="input py-1.5 px-2 text-sm w-full sm:w-36"
              />
            </div>
            <div className="min-w-0">
              <label className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] block">Fim</label>
              <input
                type="month"
                value={endMonth}
                min={startMonth}
                onChange={(e) => setEndMonth(e.target.value)}
                className="input py-1.5 px-2 text-sm w-full sm:w-36"
              />
            </div>
            <button
              onClick={() => router.push('/upload')}
              className="btn btn-primary w-full sm:w-auto"
              title="Importar controle mensal ou conta corrente"
            >
              <UploadCloud className="w-4 h-4" />
              Importar
            </button>
          </div>
        </div>

        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}
      </div>

      {loadingData ? (
        <div className="flex items-center justify-center h-64">
          <Loader className="w-8 h-8 text-[var(--brand-primary)] animate-spin" />
        </div>
      ) : chartData.length === 0 ? (
        <div className="card p-8 text-center">
          <div className="mx-auto mb-4 w-14 h-14 rounded-2xl bg-[var(--bg-accent)] flex items-center justify-center">
            <Wallet className="w-7 h-7 text-[var(--brand-primary)]" />
          </div>
          <h3 className="text-lg font-semibold text-[var(--text-primary)]">Sem dados de patrimônio</h3>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            Importe seu controle mensal (CSV) para ver a evolução do patrimônio.
          </p>
          <div className="mt-6 flex justify-center">
            <button onClick={() => router.push('/upload')} className="btn btn-primary">
              Ir para importação
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-6 animate-fade-in">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <div className="card stat-card relative overflow-hidden">
              <div className="absolute top-0 right-0 p-4 opacity-5">
                <Wallet className="w-24 h-24 transform translate-x-4 -translate-y-4 text-[var(--color-brand-primary)]" />
              </div>
              <div className="flex items-center justify-between mb-2 relative z-10">
                <span className="stat-label">Patrimônio Atual</span>
              </div>
              <p className="stat-value text-[var(--color-brand-primary)] relative z-10 mb-2">
                {formatCurrency(currentNetWorth)}
              </p>
              <p className="text-[10px] text-[var(--color-text-muted)] relative z-10">
                Último registro: {formatMonthLabel(latest?.month_ref || '')}
              </p>
            </div>

            <div className="card stat-card">
              <div className="flex items-center justify-between mb-2">
                <span className="stat-label">Variação (mês)</span>
              </div>
              <p className={clsx('stat-value mb-2', momDelta >= 0 ? 'text-emerald-600' : 'text-rose-600')}>
                {formatCurrency(momDelta)}
              </p>
              <p className="text-[10px] text-[var(--color-text-muted)]">
                {momPct === null ? 'Sem comparação' : `${(momPct * 100).toFixed(1)}% vs mês anterior`}
              </p>
            </div>

            <div className="card stat-card">
              <div className="flex items-center justify-between mb-2">
                <span className="stat-label">Variação (período)</span>
              </div>
              <p className={clsx('stat-value mb-2', periodDelta >= 0 ? 'text-emerald-600' : 'text-rose-600')}>
                {formatCurrency(periodDelta)}
              </p>
              <p className="text-[10px] text-[var(--color-text-muted)]">
                {formatMonthLabel(chartData[0]?.month_ref || '')} → {formatMonthLabel(latest?.month_ref || '')}
              </p>
            </div>
          </div>

          <div className="card p-6">
            <h3 className="font-semibold text-[var(--text-primary)] mb-1">Evolução do Patrimônio</h3>
            <p className="text-sm text-[var(--text-secondary)] mb-6">Série mensal da pessoa selecionada</p>

            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ left: 0, right: 10 }}>
                  <defs>
                    <linearGradient id="colorNetWorth" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={PRIMARY_CHART_COLOR} stopOpacity={0.25} />
                      <stop offset="95%" stopColor={PRIMARY_CHART_COLOR} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis
                    dataKey="month_ref"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#94a3b8', fontSize: 11 }}
                    tickFormatter={formatMonthLabel}
                    interval="preserveStartEnd"
                  />
                  <YAxis
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#94a3b8', fontSize: 11 }}
                    tickFormatter={(value) => `R$ ${(Number(value) / 1000).toFixed(0)}k`}
                    width={60}
                  />
                  <Tooltip content={<MoneyTooltip />} />
                  <Area
                    type="monotone"
                    dataKey="net_worth_total"
                    stroke={PRIMARY_CHART_COLOR}
                    strokeWidth={2}
                    fill="url(#colorNetWorth)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="card p-6">
            <h3 className="font-semibold text-[var(--text-primary)] mb-1">Sobra do Mês</h3>
            <p className="text-sm text-[var(--text-secondary)] mb-6">Entrada total - saída total (manual)</p>

            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={cashflowData} margin={{ left: 0, right: 10 }}>
                  <XAxis
                    dataKey="month_ref"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#94a3b8', fontSize: 11 }}
                    tickFormatter={formatMonthLabel}
                    interval="preserveStartEnd"
                  />
                  <YAxis
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#94a3b8', fontSize: 11 }}
                    tickFormatter={(value) => `R$ ${(Number(value) / 1000).toFixed(0)}k`}
                    width={60}
                  />
                  <Tooltip content={<CashflowTooltip />} />
                  <Bar dataKey="net_cashflow" fill={PRIMARY_CHART_COLOR} radius={[6, 6, 0, 0]} maxBarSize={28} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="card p-6">
            <div className="flex items-center justify-between mb-4 gap-3">
              <div>
                <h3 className="font-semibold text-[var(--text-primary)]">Validação e Edição Mensal</h3>
                <p className="text-sm text-[var(--text-secondary)]">
                  Sugestões automáticas de entrada/saída com base em fatura + conta corrente.
                </p>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="text-left text-[var(--text-secondary)] border-b border-[var(--border-color)]">
                    <th className="py-2 pr-4">Mês</th>
                    <th className="py-2 pr-4">Patrimônio</th>
                    <th className="py-2 pr-4">Entrada (manual)</th>
                    <th className="py-2 pr-4">Saída (manual)</th>
                    <th className="py-2 pr-4">Entrada (sugerida)</th>
                    <th className="py-2 pr-4">Saída (sugerida)</th>
                    <th className="py-2 pr-0">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((row) => {
                    const validation = validationByMonth.get(row.month_ref);
                    const isEditing = editingMonth === row.month_ref;
                    return (
                      <tr key={row.month_ref} className="border-b border-[var(--border-color)] align-top">
                        <td className="py-3 pr-4 font-medium">{formatMonthLabel(row.month_ref)}</td>
                        <td className="py-3 pr-4">{formatCurrency(Number(row.net_worth_total || 0))}</td>
                        <td className="py-3 pr-4">{formatCurrency(Number(row.income_total || 0))}</td>
                        <td className="py-3 pr-4">{formatCurrency(Number(row.expense_total || 0))}</td>
                        <td className="py-3 pr-4 text-emerald-700">
                          {validation ? formatCurrency(validation.suggested_income_total) : '-'}
                        </td>
                        <td className="py-3 pr-4 text-rose-700">
                          {validation ? formatCurrency(validation.suggested_expense_total) : '-'}
                        </td>
                        <td className="py-3 pr-0">
                          <button
                            type="button"
                            className="btn btn-ghost border border-[var(--border-color)]"
                            onClick={() => startEditing(row)}
                          >
                            <Pencil className="w-4 h-4" />
                            Editar
                          </button>
                          {validation?.is_partial && (
                            <p className="mt-1 text-[11px] text-amber-600">Dados parciais no mês</p>
                          )}
                          {isEditing && (
                            <div className="mt-3 rounded-xl border border-[var(--border-color)] p-3 space-y-2 bg-[var(--color-bg-accent)]">
                              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                                <input
                                  className="input"
                                  placeholder="Entrada"
                                  value={editIncome}
                                  onChange={(e) => setEditIncome(e.target.value)}
                                />
                                <input
                                  className="input"
                                  placeholder="Saída"
                                  value={editExpense}
                                  onChange={(e) => setEditExpense(e.target.value)}
                                />
                                <input
                                  className="input"
                                  placeholder="Patrimônio"
                                  value={editNetWorth}
                                  onChange={(e) => setEditNetWorth(e.target.value)}
                                />
                              </div>
                              <input
                                className="input"
                                placeholder="Observações"
                                value={editNotes}
                                onChange={(e) => setEditNotes(e.target.value)}
                              />
                              <div className="flex flex-wrap gap-2">
                                <button
                                  type="button"
                                  className="btn btn-ghost border border-[var(--border-color)]"
                                  onClick={() => applySuggestion(row.month_ref)}
                                >
                                  Aplicar sugestão
                                </button>
                                <button type="button" className="btn btn-primary" onClick={saveEditing} disabled={savingRow}>
                                  <Save className="w-4 h-4" />
                                  {savingRow ? 'Salvando...' : 'Salvar'}
                                </button>
                                <button
                                  type="button"
                                  className="btn btn-ghost border border-[var(--border-color)]"
                                  onClick={() => setEditingMonth(null)}
                                >
                                  <X className="w-4 h-4" />
                                  Cancelar
                                </button>
                              </div>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}

