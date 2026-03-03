'use client';
import { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useRouter } from 'next/navigation';
import AppShell from "@/components/AppShell";
import DashboardCharts from "@/components/DashboardCharts";
import { Loader, TrendingUp, ArrowRight, Calendar, Filter, Wallet, RefreshCw, Scale, X } from 'lucide-react';
import { getDashboardSummary, getTrendData, TransactionFilters, syncToDatabase, getOwners } from '../services/api';
import clsx from 'clsx';

export default function Home() {
  const { user, loading } = useAuth();
  const router = useRouter();

  const [data, setData] = useState<any>(null);
  const [trendData, setTrendData] = useState<any>(null);
  const [loadingData, setLoadingData] = useState(false);
  const [owners, setOwners] = useState<string[]>([]);

  // Date range state - default to current month
  const currentMonth = new Date().toISOString().slice(0, 7);
  const [startMonth, setStartMonth] = useState(currentMonth);
  const [endMonth, setEndMonth] = useState(currentMonth);

  // Filter state
  const [ownerFilter, setOwnerFilter] = useState<string>('');
  const [typeFilter, setTypeFilter] = useState<string>('');

  // Sync state
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [showBalanceModal, setShowBalanceModal] = useState(false);

  useEffect(() => {
    if (!loading && !user) {
      router.push('/login');
    }
  }, [user, loading, router]);

  useEffect(() => {
    getOwners().then(setOwners).catch(() => setOwners(['Victor', 'Larissa']));
  }, []);

  useEffect(() => {
    if (user) fetchDashboard();
  }, [user, startMonth, endMonth, ownerFilter, typeFilter]);

  const fetchDashboard = async () => {
    setLoadingData(true);
    try {
      const filters: TransactionFilters = {};
      if (ownerFilter) filters.owner = ownerFilter;
      if (typeFilter) filters.txType = typeFilter;

      const [dashResult, trendResult] = await Promise.all([
        getDashboardSummary(startMonth, endMonth, filters),
        getTrendData(startMonth, endMonth, filters)
      ]);
      setData(dashResult);
      setTrendData(trendResult);
    } catch (error) {
      console.error("Error fetching dashboard:", error);
    } finally {
      setLoadingData(false);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    setSyncMessage(null);
    try {
      const result = await syncToDatabase();
      setSyncMessage(`✓ ${result.synced_count} transações sincronizadas`);
      // Refresh dashboard after sync
      await fetchDashboard();
      // Clear message after 3 seconds
      setTimeout(() => setSyncMessage(null), 3000);
    } catch (error) {
      console.error("Sync error:", error);
      setSyncMessage('✗ Erro ao sincronizar');
      setTimeout(() => setSyncMessage(null), 3000);
    } finally {
      setSyncing(false);
    }
  };

  if (loading || !user) return null;

  const personData = (owners.length > 0 ? owners : ['Victor', 'Larissa']).map((name) => {
    const person = data?.spend_by_person?.find((p: any) => p.name === name);
    return {
      name,
      value: person?.value || 0,
      valueLast: person?.value_last_year || 0,
    };
  });

  const getTrend = (curr: number, prev: number, isDark = false) => {
    if (!prev) return <span className={`text-xs ${isDark ? 'text-white/60' : 'text-gray-400'}`}>Sem dados ant.</span>;
    const pct = ((curr - prev) / prev) * 100;
    const isUp = pct > 0;
    // Gasto maior: Vermelho (se isDark, vermelho claro). Gasto menor: Verde.
    const color = isDark
      ? (isUp ? "text-red-200 bg-red-500/20" : "text-green-200 bg-green-500/20")
      : (isUp ? "text-red-700 bg-red-50" : "text-green-700 bg-green-50");

    return (
      <span className={`text-[10px] font-semibold flex items-center gap-1 px-1.5 py-0.5 rounded-md ${color}`}>
        {isUp ? "▲" : "▼"} {Math.abs(pct).toFixed(0)}%
      </span>
    );
  };

  return (
    <AppShell>
      {/* Header */}
      <div className="flex flex-col gap-4 mb-8">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="page-header mb-0">
            <h1 className="page-title">Dashboard</h1>
            <p className="page-subtitle">Visão geral das suas finanças</p>
          </div>

          {/* Date Range Selector */}
          <div className="w-full sm:w-auto flex flex-wrap items-center gap-2 bg-white p-3 rounded-xl border border-[var(--border-color)] shadow-sm">
            <Calendar className="w-4 h-4 text-[var(--text-muted)]" />
            <div className="grid grid-cols-1 sm:grid-cols-[auto_auto_auto] items-end gap-2 w-full sm:w-auto">
              <div className="min-w-0">
                <label className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] block">Início</label>
                <input
                  type="month"
                  value={startMonth}
                  onChange={(e) => setStartMonth(e.target.value)}
                  className="input py-1.5 px-2 text-sm w-full sm:w-36"
                />
              </div>
              <span className="text-[var(--text-muted)] hidden sm:inline">→</span>
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
            </div>
          </div>
        </div>

        {/* Filters Row */}
        {/* Filters & Actions Bar */}
        <div className="bg-white p-4 rounded-xl border border-[var(--color-border)] shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2 text-[var(--color-text-secondary)]">
              <Filter className="w-4 h-4" />
              <span className="text-sm font-medium">Filtrar por:</span>
            </div>

            {/* Owner Filter */}
            <div className="relative">
              <select
                value={ownerFilter}
                onChange={(e) => setOwnerFilter(e.target.value)}
                className="appearance-none bg-[var(--color-bg-primary)] border-none text-[var(--color-text-primary)] text-sm font-medium py-2 pl-3 pr-8 rounded-lg cursor-pointer hover:bg-[var(--color-bg-accent)] transition-colors focus:ring-2 focus:ring-[var(--color-brand-primary)]"
              >
                <option value="">Todas Pessoas</option>
                {owners.map((o) => (
                  <option key={o} value={o}>{o}</option>
                ))}
              </select>
              <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-[var(--color-text-secondary)]">
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" /></svg>
              </div>
            </div>

            {/* Type Filter */}
            <div className="relative">
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                className="appearance-none bg-[var(--color-bg-primary)] border-none text-[var(--color-text-primary)] text-sm font-medium py-2 pl-3 pr-8 rounded-lg cursor-pointer hover:bg-[var(--color-bg-accent)] transition-colors focus:ring-2 focus:ring-[var(--color-brand-primary)]"
              >
                <option value="">Todos Tipos</option>
                <option value="Shared">Compartilhado</option>
                <option value="Individual">Individual</option>
              </select>
              <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-[var(--color-text-secondary)]">
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" /></svg>
              </div>
            </div>

            {(ownerFilter || typeFilter) && (
              <button
                onClick={() => { setOwnerFilter(''); setTypeFilter(''); }}
                className="text-xs font-semibold text-[var(--color-brand-primary)] hover:underline ml-2"
              >
                Limpar
              </button>
            )}
          </div>

          <div className="w-full md:w-auto flex flex-col sm:flex-row sm:items-center gap-2">
            {syncMessage && (
              <span className={clsx(
                "text-xs font-medium px-3 py-1.5 rounded-lg",
                syncMessage.startsWith('✓') ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
              )}>
                {syncMessage}
              </span>
            )}
            <button
              onClick={handleSync}
              disabled={syncing}
              className="btn btn-ghost border border-[var(--color-border)] flex items-center gap-2 w-full sm:w-auto"
              title="Sincronizar alterações das Transações para o Dashboard"
            >
              <RefreshCw className={clsx("w-4 h-4", syncing && "animate-spin")} />
              {syncing ? 'Sincronizando...' : 'Sincronizar'}
            </button>
            <button
              onClick={() => setShowBalanceModal(true)}
              className="btn btn-ghost border border-[var(--color-border)] w-full sm:w-auto"
            >
              <Scale className="w-4 h-4" />
              Calcular equilíbrio
            </button>
            <button
              onClick={() => router.push('/upload')}
              className="btn btn-primary w-full sm:w-auto"
            >
              <ArrowRight className="w-4 h-4" />
              Importar Novos Arquivos
            </button>
          </div>
        </div>
      </div>

      {loadingData || !data ? (
        <div className="flex items-center justify-center h-64">
          <Loader className="w-8 h-8 text-[var(--brand-primary)] animate-spin" />
        </div>
      ) : (
        <div className="space-y-6 animate-fade-in">
          {/* KPI Cards */}
          {/* KPI Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {/* Total Spend */}
            <div className="card stat-card relative overflow-hidden">
              <div className="absolute top-0 right-0 p-4 opacity-5">
                <Wallet className="w-24 h-24 transform translate-x-4 -translate-y-4 text-[var(--color-brand-primary)]" />
              </div>
              <div className="flex items-center justify-between mb-2 relative z-10">
                <span className="stat-label">Gasto Total</span>
                <TrendingUp className="w-5 h-5 text-[var(--color-brand-primary)]" />
              </div>
              <p className="stat-value text-[var(--color-brand-primary)] relative z-10 mb-2">
                R$ {data.total_spend?.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
              </p>
              <div className="relative z-10 flex items-center gap-2">
                {getTrend(data.total_spend, data.total_spend_last_year, false)}
                <span className="text-[10px] text-[var(--color-text-muted)]">vs ano anterior</span>
              </div>
            </div>

            {/* Per-person cards */}
            {personData.map((person, idx) => {
              const colors = ['blue', 'pink', 'emerald', 'amber', 'purple'];
              const color = colors[idx % colors.length];
              const initial = person.name.charAt(0).toUpperCase();
              return (
                <div key={person.name} className="card stat-card">
                  <div className="flex items-center justify-between mb-3">
                    <span className="stat-label">{person.name}</span>
                    <div className={`w-8 h-8 bg-${color}-100 rounded-full flex items-center justify-center`}>
                      <span className={`text-${color}-600 text-xs font-bold`}>{initial}</span>
                    </div>
                  </div>
                  <p className={`stat-value text-${color}-600 mb-2`}>
                    R$ {person.value?.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                  </p>
                  <div className="flex items-center gap-2">
                    {getTrend(person.value, person.valueLast)}
                    <span className="text-[10px] text-[var(--color-text-muted)]">vs ano anterior</span>
                  </div>
                </div>
              );
            })}

          </div>

          {/* Charts */}
          <DashboardCharts data={{
            totalSpend: data.total_spend,
            spendByPerson: data.spend_by_person,
            spendByCategory: data.spend_by_category,
            spendTrend: trendData?.data || []
          }} granularity={trendData?.granularity || 'monthly'} />

          {/* Quick Actions */}
          <div className="card p-6">
            <h3 className="font-semibold text-[var(--text-primary)] mb-4">Ações Rápidas</h3>
            <div className="flex flex-col sm:flex-row sm:flex-wrap gap-3">
              <a href="/upload" className="btn btn-primary w-full sm:w-auto">
                Importar Extrato
                <ArrowRight className="w-4 h-4" />
              </a>
              <a href="/transactions" className="btn btn-ghost border border-[var(--border-color)] w-full sm:w-auto">
                Ver Transações
              </a>
            </div>
          </div>
        </div>
      )}

      {showBalanceModal && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
            <div className="mb-4 flex items-start justify-between">
              <div>
                <h3 className="text-xl font-semibold text-[var(--color-text-primary)]">Equilíbrio do período</h3>
                <p className="text-sm text-[var(--color-text-secondary)]">
                  {startMonth} até {endMonth}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowBalanceModal(false)}
                className="rounded-lg p-2 hover:bg-gray-100"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-accent)] p-4">
              <p className="text-xs uppercase tracking-wider text-[var(--color-text-muted)]">Resultado</p>
              <p className="mt-2 text-3xl font-bold text-[var(--color-text-primary)]">
                R$ {Number(data?.settlement?.amount || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
              </p>
              <p className="mt-2 text-sm font-medium text-[var(--color-text-secondary)]">
                {data?.settlement?.direction || 'Sem pendências'}
              </p>
            </div>

            <div className="mt-5 flex justify-end">
              <button type="button" className="btn btn-primary w-full sm:w-auto" onClick={() => setShowBalanceModal(false)}>
                Fechar
              </button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
