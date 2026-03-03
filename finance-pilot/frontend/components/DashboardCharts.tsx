'use client';

import { Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, Area, AreaChart } from 'recharts';

interface DashboardData {
    totalSpend: number;
    spendByPerson: { name: string; value: number }[];
    spendByCategory: { name: string; value: number }[];
    spendTrend: { period: string; total: number }[];
}

// Monochromatic palette (same hue, different tones)
const PRIMARY_CHART_COLOR = '#4338ca';
const COLORS = ['#312e81', '#3730a3', '#4338ca', '#4f46e5', '#6366f1', '#818cf8'];
const PERSON_COLORS: Record<string, string> = {
    'Victor': '#3730a3',
    'Larissa': '#818cf8'
};

interface DashboardChartsProps {
    data: DashboardData;
    granularity?: 'daily' | 'monthly';
}

const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
        return (
            <div className="bg-white border border-[var(--border-color)] rounded-lg p-3 shadow-lg text-sm">
                <p className="font-medium text-[var(--text-primary)]">{payload[0].name || label}</p>
                <p className="text-[var(--brand-primary)] font-semibold">
                    R$ {payload[0].value?.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                </p>
            </div>
        );
    }
    return null;
};

const PersonTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
        const name = payload[0].name;
        const value = Number(payload[0].value || 0);
        const row = payload[0].payload || {};
        const total = Object.entries(row)
            .filter(([key]) => key !== 'label')
            .reduce((sum, [, v]) => sum + Number(v || 0), 0);
        const percent = total ? value / total : 0;

        return (
            <div className="bg-white border border-[var(--border-color)] rounded-lg p-3 shadow-lg text-sm">
                <p className="font-medium text-[var(--text-primary)]">{name}</p>
                <p className="text-[var(--brand-primary)] font-semibold">
                    R$ {value.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}{' '}
                    <span className="text-[var(--text-secondary)] font-medium">({(percent * 100).toFixed(1)}%)</span>
                </p>
            </div>
        );
    }
    return null;
};

const TrendTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
        const formattedLabel = label?.includes('-')
            ? new Date(label + (label.length === 7 ? '-01' : '')).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' })
            : label;
        return (
            <div className="bg-white border border-[var(--border-color)] rounded-lg p-3 shadow-lg text-sm">
                <p className="font-medium text-[var(--text-secondary)] text-xs">{formattedLabel}</p>
                <p className="text-[var(--brand-primary)] font-semibold">
                    R$ {payload[0].value?.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                </p>
            </div>
        );
    }
    return null;
};

export default function DashboardCharts({ data, granularity = 'monthly' }: DashboardChartsProps) {
    const spendByPersonData = data.spendByPerson || [];
    const spendByPersonTotal = spendByPersonData.reduce((sum, item) => sum + (item.value || 0), 0);
    const spendByPersonRow = spendByPersonData.reduce(
        (acc, item) => {
            acc[item.name] = item.value || 0;
            return acc;
        },
        { label: 'Total' } as Record<string, any>
    );
    const spendByPersonSubtitle =
        spendByPersonData.length === 2
            ? `Distribuição entre ${spendByPersonData[0].name} e ${spendByPersonData[1].name}`
            : 'Distribuição por pessoa no período';

    // Format period labels for the trend chart
    const formatPeriod = (period: string) => {
        if (!period) return '';
        if (period.length === 7) {
            // Monthly: YYYY-MM -> MMM/YY
            const [year, month] = period.split('-');
            const date = new Date(parseInt(year), parseInt(month) - 1);
            return date.toLocaleDateString('pt-BR', { month: 'short' }).replace('.', '');
        }
        // Daily: YYYY-MM-DD -> DD
        const parts = period.split('-');
        return parts[2] || period;
    };

    return (
        <div className="space-y-6">
            {/* Trend Chart - Full Width */}
            {data.spendTrend && data.spendTrend.length > 0 && (
                <div className="card p-6">
                    <h3 className="font-semibold text-[var(--text-primary)] mb-1">Evolução de Gastos</h3>
                    <p className="text-sm text-[var(--text-secondary)] mb-6">
                        {granularity === 'daily' ? 'Gastos diários' : 'Gastos mensais'} no período
                    </p>

                    <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={data.spendTrend} margin={{ left: 0, right: 10 }}>
                                <defs>
                                    <linearGradient id="colorTotal" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor={PRIMARY_CHART_COLOR} stopOpacity={0.3} />
                                        <stop offset="95%" stopColor={PRIMARY_CHART_COLOR} stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <XAxis
                                    dataKey="period"
                                    axisLine={false}
                                    tickLine={false}
                                    tick={{ fill: '#94a3b8', fontSize: 11 }}
                                    tickFormatter={formatPeriod}
                                    interval={granularity === 'daily' ? 'preserveStartEnd' : 0}
                                />
                                <YAxis
                                    axisLine={false}
                                    tickLine={false}
                                    tick={{ fill: '#94a3b8', fontSize: 11 }}
                                    tickFormatter={(value) => `R$ ${(value / 1000).toFixed(0)}k`}
                                    width={60}
                                />
                                <Tooltip content={<TrendTooltip />} />
                                <Area
                                    type="monotone"
                                    dataKey="total"
                                    stroke={PRIMARY_CHART_COLOR}
                                    strokeWidth={2}
                                    fill="url(#colorTotal)"
                                />
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Spending by Person - Divided Bar */}
                <div className="card p-6">
                    <h3 className="font-semibold text-[var(--text-primary)] mb-1">Gastos por Pessoa</h3>
                    <p className="text-sm text-[var(--text-secondary)] mb-6">{spendByPersonSubtitle}</p>

                    <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart
                                data={[spendByPersonRow]}
                                layout="vertical"
                                margin={{ left: 0, right: 20 }}
                            >
                                <XAxis type="number" hide domain={[0, spendByPersonTotal || 'dataMax']} />
                                <YAxis type="category" dataKey="label" hide />
                                <Tooltip content={<PersonTooltip />} />
                                <Legend
                                    verticalAlign="bottom"
                                    formatter={(value) => <span className="text-sm text-[var(--text-secondary)]">{value}</span>}
                                />

                                {(spendByPersonData || []).map((entry, index) => {
                                    const isOnly = spendByPersonData.length === 1;
                                    const isFirst = index === 0;
                                    const isLast = index === spendByPersonData.length - 1;
                                    const radius: [number, number, number, number] = isFirst
                                        ? (isOnly ? [6, 6, 6, 6] : [6, 0, 0, 6])
                                        : isLast
                                            ? [0, 6, 6, 0]
                                            : [0, 0, 0, 0];

                                    return (
                                        <Bar
                                            key={entry.name}
                                            dataKey={entry.name}
                                            stackId="total"
                                            barSize={28}
                                            radius={radius}
                                            fill={PERSON_COLORS[entry.name] || COLORS[index % COLORS.length]}
                                        />
                                    );
                                })}
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* Spending by Category - Bar Chart */}
                <div className="card p-6">
                    <h3 className="font-semibold text-[var(--text-primary)] mb-1">Gastos por Categoria</h3>
                    <p className="text-sm text-[var(--text-secondary)] mb-6">Top categorias do período</p>

                    <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart
                                data={(data.spendByCategory || []).slice(0, 6)}
                                layout="vertical"
                                margin={{ left: 0, right: 20 }}
                            >
                                <XAxis
                                    type="number"
                                    axisLine={false}
                                    tickLine={false}
                                    tick={{ fill: '#94a3b8', fontSize: 12 }}
                                    tickFormatter={(value) => `R$ ${(value / 1000).toFixed(0)}k`}
                                />
                                <YAxis
                                    type="category"
                                    dataKey="name"
                                    axisLine={false}
                                    tickLine={false}
                                    tick={{ fill: '#64748b', fontSize: 12 }}
                                    width={80}
                                />
                                <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(0,0,0,0.02)' }} />
                                <Bar
                                    dataKey="value"
                                    radius={[0, 6, 6, 0]}
                                    maxBarSize={24}
                                >
                                    {(data.spendByCategory || []).slice(0, 6).map((_, index) => (
                                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                    ))}
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            </div>
        </div>
    );
}
