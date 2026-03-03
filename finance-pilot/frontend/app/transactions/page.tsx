'use client';

import { useEffect, useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '../../context/AuthContext';
import { getTransactions, updateTransaction, createTransaction, deleteTransaction, TransactionFilters } from '../../services/api';
import { Loader, Edit2, X, Check, Calendar, Filter, Plus, Trash2, ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react';
import AppShell from '../../components/AppShell';
import clsx from 'clsx';

const CATEGORIES = [
    'Alimentação', 'Bar/Restaurante', 'Transporte', 'Combustivel', 'Moradia',
    'Aluguel', 'Condominio', 'Lazer', 'Saúde/Estética', 'Mercado', 'Delivery',
    'Streaming', 'Projeto Pessoal', 'Uber/Onibus', 'Presentes', 'Faxina',
    'Curso', 'Luz/Internet', 'Manutenção/Revisão', 'Vestuário', 'Voos',
    'Airbnb/Hotel', 'Pedagio', 'ItensdeCasa', 'Luana', 'Outro'
];
const TYPES = ['Shared', 'Individual'];
const OWNERS = ['Victor', 'Larissa'];

type SortField = 'date' | 'merchant_clean' | 'owner' | 'amount' | 'category' | 'type';
type SortDirection = 'asc' | 'desc';

interface EditFormData {
    date: string;
    amount: string;
    merchant_clean: string;
    category: string;
    owner: string;
    type: string;
}

const emptyForm: EditFormData = {
    date: new Date().toISOString().slice(0, 10),
    amount: '',
    merchant_clean: '',
    category: 'Outro',
    owner: 'Victor',
    type: 'Shared'
};

export default function TransactionsPage() {
    const { user, loading } = useAuth();
    const router = useRouter();
    const [transactions, setTransactions] = useState<any[]>([]);
    const [loadingData, setLoadingData] = useState(false);

    // Date range state
    const currentMonth = new Date().toISOString().slice(0, 7);
    const [startMonth, setStartMonth] = useState(currentMonth);
    const [endMonth, setEndMonth] = useState(currentMonth);

    // Filter state
    const [ownerFilter, setOwnerFilter] = useState<string>('');
    const [typeFilter, setTypeFilter] = useState<string>('');

    // Sort state
    const [sortField, setSortField] = useState<SortField>('date');
    const [sortDirection, setSortDirection] = useState<SortDirection>('desc');

    // Edit state
    const [editingId, setEditingId] = useState<string | null>(null);
    const [editForm, setEditForm] = useState<EditFormData>(emptyForm);

    // Create modal state
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [createForm, setCreateForm] = useState<EditFormData>(emptyForm);

    // Sorted transactions
    const sortedTransactions = useMemo(() => {
        const sorted = [...transactions].sort((a, b) => {
            let aVal = a[sortField];
            let bVal = b[sortField];

            // Handle numeric sorting for amount
            if (sortField === 'amount') {
                aVal = parseFloat(aVal) || 0;
                bVal = parseFloat(bVal) || 0;
            } else {
                // String comparison
                aVal = (aVal || '').toString().toLowerCase();
                bVal = (bVal || '').toString().toLowerCase();
            }

            if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1;
            if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1;
            return 0;
        });
        return sorted;
    }, [transactions, sortField, sortDirection]);

    const handleSort = (field: SortField) => {
        if (sortField === field) {
            setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
        } else {
            setSortField(field);
            setSortDirection('desc');
        }
    };

    const SortIcon = ({ field }: { field: SortField }) => {
        if (sortField !== field) {
            return <ArrowUpDown className="w-3 h-3 ml-1 opacity-40" />;
        }
        return sortDirection === 'asc'
            ? <ArrowUp className="w-3 h-3 ml-1 text-[var(--brand-primary)]" />
            : <ArrowDown className="w-3 h-3 ml-1 text-[var(--brand-primary)]" />;
    };

    useEffect(() => {
        if (!loading && !user) router.push('/login');
    }, [user, loading, router]);

    useEffect(() => {
        if (user) fetchTransactions();
    }, [user, startMonth, endMonth, ownerFilter, typeFilter]);

    const fetchTransactions = async () => {
        setLoadingData(true);
        try {
            const filters: TransactionFilters = {};
            if (ownerFilter) filters.owner = ownerFilter;
            if (typeFilter) filters.txType = typeFilter;

            const data = await getTransactions(startMonth, endMonth, filters);
            setTransactions(data);
        } catch (error) {
            console.error(error);
        } finally {
            setLoadingData(false);
        }
    };

    const handleEditClick = (tx: any) => {
        setEditingId(tx.id);
        setEditForm({
            date: tx.date,
            amount: tx.amount?.toString() || '',
            merchant_clean: tx.merchant_clean || '',
            category: tx.category || 'Outro',
            owner: tx.owner || 'Victor',
            type: tx.type || 'Shared'
        });
    };

    const handleSave = async (id: string) => {
        try {
            await updateTransaction(id, {
                date: editForm.date,
                amount: parseFloat(editForm.amount),
                merchant_clean: editForm.merchant_clean,
                category: editForm.category,
                owner: editForm.owner,
                type: editForm.type
            });
            setEditingId(null);
            fetchTransactions();
        } catch (error) {
            console.error("Failed to update", error);
        }
    };

    const handleDelete = async (id: string) => {
        if (!confirm('Tem certeza que deseja excluir esta transação?')) return;
        try {
            await deleteTransaction(id);
            fetchTransactions();
        } catch (error) {
            console.error("Failed to delete", error);
        }
    };

    const handleCreate = async () => {
        try {
            await createTransaction({
                date: createForm.date,
                amount: parseFloat(createForm.amount),
                merchant_clean: createForm.merchant_clean,
                category: createForm.category,
                owner: createForm.owner,
                type: createForm.type
            });
            setShowCreateModal(false);
            setCreateForm(emptyForm);
            fetchTransactions();
        } catch (error) {
            console.error("Failed to create", error);
        }
    };

    const handleCancel = () => {
        setEditingId(null);
    };

    if (loading || !user) return null;

    return (
        <AppShell>
            {/* Header */}
            <div className="flex flex-col gap-4 mb-8">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                    <div className="page-header mb-0">
                        <h1 className="page-title">Transações</h1>
                        <p className="page-subtitle">Revise e categorize seus gastos</p>
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
                                <option value="Victor">Victor</option>
                                <option value="Larissa">Larissa</option>
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

                    {/* Add Transaction Button */}
                    <button
                        onClick={() => setShowCreateModal(true)}
                        className="btn btn-primary w-full md:w-auto"
                    >
                        <Plus className="w-4 h-4" />
                        Nova Transação
                    </button>
                </div>
            </div>

            {loadingData ? (
                <div className="flex justify-center py-20">
                    <Loader className="w-8 h-8 text-[var(--brand-primary)] animate-spin" />
                </div>
            ) : transactions.length === 0 ? (
                <div className="card p-12 text-center">
                    <div className="w-16 h-16 bg-[var(--bg-accent)] rounded-full flex items-center justify-center mx-auto mb-4">
                        <span className="text-3xl">📭</span>
                    </div>
                    <h3 className="font-semibold text-[var(--text-primary)] mb-2">Nenhuma transação</h3>
                    <p className="text-sm text-[var(--text-secondary)]">
                        Não há transações para o período selecionado.
                    </p>
                </div>
            ) : (
                <>
                    {/* Desktop Table */}
                    <div className="hidden md:block card overflow-hidden animate-fade-in">
                        <table className="w-full">
                            <thead>
                                <tr className="border-b border-[var(--border-color)] bg-[var(--bg-primary)]">
                                    <th
                                        onClick={() => handleSort('date')}
                                        className="text-left py-3 px-4 text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider cursor-pointer hover:text-[var(--text-primary)] transition-colors select-none"
                                    >
                                        <span className="inline-flex items-center">Data<SortIcon field="date" /></span>
                                    </th>
                                    <th
                                        onClick={() => handleSort('merchant_clean')}
                                        className="text-left py-3 px-4 text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider cursor-pointer hover:text-[var(--text-primary)] transition-colors select-none"
                                    >
                                        <span className="inline-flex items-center">Descrição<SortIcon field="merchant_clean" /></span>
                                    </th>
                                    <th
                                        onClick={() => handleSort('owner')}
                                        className="text-left py-3 px-4 text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider cursor-pointer hover:text-[var(--text-primary)] transition-colors select-none"
                                    >
                                        <span className="inline-flex items-center">Quem<SortIcon field="owner" /></span>
                                    </th>
                                    <th
                                        onClick={() => handleSort('amount')}
                                        className="text-right py-3 px-4 text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider cursor-pointer hover:text-[var(--text-primary)] transition-colors select-none"
                                    >
                                        <span className="inline-flex items-center justify-end">Valor<SortIcon field="amount" /></span>
                                    </th>
                                    <th
                                        onClick={() => handleSort('category')}
                                        className="text-left py-3 px-4 text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider cursor-pointer hover:text-[var(--text-primary)] transition-colors select-none"
                                    >
                                        <span className="inline-flex items-center">Categoria<SortIcon field="category" /></span>
                                    </th>
                                    <th
                                        onClick={() => handleSort('type')}
                                        className="text-left py-3 px-4 text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider cursor-pointer hover:text-[var(--text-primary)] transition-colors select-none"
                                    >
                                        <span className="inline-flex items-center">Tipo<SortIcon field="type" /></span>
                                    </th>
                                    <th className="text-center py-3 px-4 text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider">Ações</th>
                                </tr>
                            </thead>
                            <tbody>
                                {sortedTransactions.map((tx, index) => (
                                    <tr
                                        key={tx.id}
                                        className={clsx(
                                            "border-b border-[var(--border-color)] hover:bg-[var(--bg-primary)] transition-colors",
                                            index % 2 === 0 ? "bg-white" : "bg-[var(--bg-primary)]/50"
                                        )}
                                    >
                                        <td className="py-3 px-4 text-sm font-mono">
                                            {editingId === tx.id ? (
                                                <input
                                                    type="date"
                                                    value={editForm.date}
                                                    onChange={(e) => setEditForm({ ...editForm, date: e.target.value })}
                                                    className="input py-1 px-2 text-sm w-32"
                                                />
                                            ) : (
                                                <span className="text-[var(--text-secondary)]">{tx.date}</span>
                                            )}
                                        </td>
                                        <td className="py-3 px-4">
                                            {editingId === tx.id ? (
                                                <input
                                                    type="text"
                                                    value={editForm.merchant_clean}
                                                    onChange={(e) => setEditForm({ ...editForm, merchant_clean: e.target.value })}
                                                    className="input py-1 px-2 text-sm w-full max-w-[200px]"
                                                />
                                            ) : (
                                                <p className="text-sm font-medium text-[var(--text-primary)] truncate max-w-[200px]">
                                                    {tx.merchant_clean}
                                                </p>
                                            )}
                                        </td>
                                        <td className="py-3 px-4">
                                            {editingId === tx.id ? (
                                                <select
                                                    value={editForm.owner}
                                                    onChange={(e) => setEditForm({ ...editForm, owner: e.target.value })}
                                                    className="input py-1 px-2 text-sm w-24"
                                                >
                                                    {OWNERS.map(o => (
                                                        <option key={o} value={o}>{o}</option>
                                                    ))}
                                                </select>
                                            ) : (
                                                <span className={clsx(
                                                    "inline-flex items-center px-2 py-1 rounded-full text-xs font-medium",
                                                    tx.owner === 'Victor'
                                                        ? "bg-blue-100 text-blue-700"
                                                        : "bg-pink-100 text-pink-700"
                                                )}>
                                                    {tx.owner}
                                                </span>
                                            )}
                                        </td>
                                        <td className="py-3 px-4 text-right">
                                            {editingId === tx.id ? (
                                                <input
                                                    type="number"
                                                    value={editForm.amount}
                                                    onChange={(e) => setEditForm({ ...editForm, amount: e.target.value })}
                                                    className="input py-1 px-2 text-sm w-24 text-right"
                                                    step="0.01"
                                                />
                                            ) : (
                                                <span className="text-sm font-semibold text-[var(--text-primary)]">
                                                    R$ {tx.amount?.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                                </span>
                                            )}
                                        </td>
                                        <td className="py-3 px-4">
                                            {editingId === tx.id ? (
                                                <select
                                                    value={editForm.category}
                                                    onChange={(e) => setEditForm({ ...editForm, category: e.target.value })}
                                                    className="input py-1 px-2 text-sm w-32"
                                                >
                                                    {CATEGORIES.map(cat => (
                                                        <option key={cat} value={cat}>{cat}</option>
                                                    ))}
                                                </select>
                                            ) : (
                                                <span className="text-sm text-[var(--text-primary)]">{tx.category}</span>
                                            )}
                                        </td>
                                        <td className="py-3 px-4">
                                            {editingId === tx.id ? (
                                                <select
                                                    value={editForm.type}
                                                    onChange={(e) => setEditForm({ ...editForm, type: e.target.value })}
                                                    className="input py-1 px-2 text-sm w-28"
                                                >
                                                    {TYPES.map(type => (
                                                        <option key={type} value={type}>{type}</option>
                                                    ))}
                                                </select>
                                            ) : (
                                                <span className={clsx(
                                                    "inline-flex items-center px-2 py-1 rounded-full text-xs font-medium",
                                                    tx.type === 'Shared'
                                                        ? "bg-indigo-100 text-indigo-700"
                                                        : "bg-gray-100 text-gray-600"
                                                )}>
                                                    {tx.type === 'Shared' ? 'Compartilhado' : 'Individual'}
                                                </span>
                                            )}
                                        </td>
                                        <td className="py-3 px-4 text-center">
                                            {editingId === tx.id ? (
                                                <div className="flex items-center justify-center gap-1">
                                                    <button
                                                        onClick={() => handleSave(tx.id)}
                                                        className="p-1.5 hover:bg-green-100 rounded-lg text-green-600 transition-colors"
                                                        title="Salvar"
                                                    >
                                                        <Check className="w-4 h-4" />
                                                    </button>
                                                    <button
                                                        onClick={handleCancel}
                                                        className="p-1.5 hover:bg-red-100 rounded-lg text-red-500 transition-colors"
                                                        title="Cancelar"
                                                    >
                                                        <X className="w-4 h-4" />
                                                    </button>
                                                </div>
                                            ) : (
                                                <div className="flex items-center justify-center gap-1">
                                                    <button
                                                        onClick={() => handleEditClick(tx)}
                                                        className="p-1.5 hover:bg-[var(--bg-accent)] rounded-lg text-[var(--text-secondary)] transition-colors"
                                                        title="Editar"
                                                    >
                                                        <Edit2 className="w-4 h-4" />
                                                    </button>
                                                    <button
                                                        onClick={() => handleDelete(tx.id)}
                                                        className="p-1.5 hover:bg-red-100 rounded-lg text-red-400 transition-colors"
                                                        title="Excluir"
                                                    >
                                                        <Trash2 className="w-4 h-4" />
                                                    </button>
                                                </div>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>

                    {/* Mobile Cards */}
                    <div className="md:hidden space-y-3 animate-fade-in">
                        {transactions.map((tx) => (
                            <div key={tx.id} className="card p-4">
                                <div className="flex items-start justify-between mb-3">
                                    <div className="flex-1 min-w-0">
                                        <p className="font-medium text-[var(--text-primary)] truncate">
                                            {tx.merchant_clean}
                                        </p>
                                        <p className="text-xs text-[var(--text-secondary)] font-mono mt-0.5">
                                            {tx.date}
                                        </p>
                                    </div>
                                    <span className="text-lg font-bold text-[var(--text-primary)] ml-4">
                                        R$ {tx.amount?.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                    </span>
                                </div>

                                <div className="flex items-center gap-2 flex-wrap">
                                    <span className={clsx(
                                        "px-2 py-1 rounded-full text-xs font-medium",
                                        tx.owner === 'Victor' ? "bg-blue-100 text-blue-700" : "bg-pink-100 text-pink-700"
                                    )}>
                                        {tx.owner}
                                    </span>
                                    <span className="px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
                                        {tx.category}
                                    </span>
                                    <span className={clsx(
                                        "px-2 py-1 rounded-full text-xs font-medium",
                                        tx.type === 'Shared' ? "bg-indigo-100 text-indigo-700" : "bg-gray-100 text-gray-600"
                                    )}>
                                        {tx.type === 'Shared' ? 'Compartilhado' : 'Individual'}
                                    </span>

                                    <div className="ml-auto flex gap-1">
                                        <button
                                            onClick={() => handleEditClick(tx)}
                                            className="p-1.5 hover:bg-[var(--bg-accent)] rounded-lg text-[var(--text-secondary)]"
                                        >
                                            <Edit2 className="w-4 h-4" />
                                        </button>
                                        <button
                                            onClick={() => handleDelete(tx.id)}
                                            className="p-1.5 hover:bg-red-100 rounded-lg text-red-400"
                                        >
                                            <Trash2 className="w-4 h-4" />
                                        </button>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </>
            )}

            {/* Create Transaction Modal */}
            {showCreateModal && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
                    <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6 animate-fade-in">
                        <h2 className="text-lg font-semibold text-[var(--text-primary)] mb-4">Nova Transação</h2>

                        <div className="space-y-4">
                            <div>
                                <label className="label">Data</label>
                                <input
                                    type="date"
                                    value={createForm.date}
                                    onChange={(e) => setCreateForm({ ...createForm, date: e.target.value })}
                                    className="input w-full"
                                />
                            </div>
                            <div>
                                <label className="label">Descrição</label>
                                <input
                                    type="text"
                                    value={createForm.merchant_clean}
                                    onChange={(e) => setCreateForm({ ...createForm, merchant_clean: e.target.value })}
                                    className="input w-full"
                                    placeholder="Ex: Restaurante, Mercado..."
                                />
                            </div>
                            <div>
                                <label className="label">Valor (R$)</label>
                                <input
                                    type="number"
                                    value={createForm.amount}
                                    onChange={(e) => setCreateForm({ ...createForm, amount: e.target.value })}
                                    className="input w-full"
                                    placeholder="0.00"
                                    step="0.01"
                                />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="label">Quem pagou</label>
                                    <select
                                        value={createForm.owner}
                                        onChange={(e) => setCreateForm({ ...createForm, owner: e.target.value })}
                                        className="input w-full"
                                    >
                                        {OWNERS.map(o => (
                                            <option key={o} value={o}>{o}</option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label className="label">Tipo</label>
                                    <select
                                        value={createForm.type}
                                        onChange={(e) => setCreateForm({ ...createForm, type: e.target.value })}
                                        className="input w-full"
                                    >
                                        <option value="Shared">Compartilhado</option>
                                        <option value="Individual">Individual</option>
                                    </select>
                                </div>
                            </div>
                            <div>
                                <label className="label">Categoria</label>
                                <select
                                    value={createForm.category}
                                    onChange={(e) => setCreateForm({ ...createForm, category: e.target.value })}
                                    className="input w-full"
                                >
                                    {CATEGORIES.map(cat => (
                                        <option key={cat} value={cat}>{cat}</option>
                                    ))}
                                </select>
                            </div>
                        </div>

                        <div className="flex gap-3 mt-6">
                            <button
                                onClick={() => setShowCreateModal(false)}
                                className="btn btn-ghost flex-1 border border-[var(--border-color)]"
                            >
                                Cancelar
                            </button>
                            <button
                                onClick={handleCreate}
                                className="btn btn-primary flex-1"
                                disabled={!createForm.merchant_clean || !createForm.amount}
                            >
                                Criar Transação
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </AppShell>
    );
}
