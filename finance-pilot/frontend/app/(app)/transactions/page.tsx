'use client';

import { useEffect, useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '../../../context/AuthContext';
import { getTransactions, updateTransaction, createTransaction, deleteTransaction, TransactionFilters, getOwners } from '../../../services/api';
import { Loader, Edit2, X, Check, Calendar, Filter, Plus, Trash2, ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react';
import clsx from 'clsx';

const CATEGORIES = [
    'Alimentação', 'Bar/Restaurante', 'Transporte', 'Combustivel', 'Moradia',
    'Aluguel', 'Condominio', 'Lazer', 'Saúde/Estética', 'Mercado', 'Delivery',
    'Streaming', 'Projeto Pessoal', 'Uber/Onibus', 'Presentes', 'Faxina',
    'Curso', 'Luz/Internet', 'Manutenção/Revisão', 'Vestuário', 'Voos',
    'Airbnb/Hotel', 'Pedagio', 'ItensdeCasa', 'Luana', 'Outro'
];
const TYPES = ['Shared', 'Individual'];

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
    owner: '',
    type: 'Shared'
};

interface Transaction {
    id: string;
    date: string;
    amount: number;
    merchant_clean: string;
    category: string;
    subcategory?: string;
    owner: string;
    type: string;
    month_ref?: string;
}

interface PendingUpdate {
    id: string;
    data: {
        date: string;
        amount: number;
        merchant_clean: string;
        category: string;
        owner: string;
        type: string;
    };
}

export default function TransactionsPage() {
    const { user, loading } = useAuth();
    const router = useRouter();
    const [transactions, setTransactions] = useState<Transaction[]>([]);
    const [loadingData, setLoadingData] = useState(false);
    const [owners, setOwners] = useState<string[]>([]);

    useEffect(() => {
        getOwners().then(setOwners).catch(() => {});
    }, []);

    // Date range state
    const prevMonth = (() => {
        const d = new Date();
        d.setMonth(d.getMonth() - 1);
        return d.toISOString().slice(0, 7);
    })();
    const [startMonth, setStartMonth] = useState(prevMonth);
    const [endMonth, setEndMonth] = useState(prevMonth);

    // Filter state
    const [ownerFilter, setOwnerFilter] = useState<string>('');
    const [typeFilter, setTypeFilter] = useState<string>('');

    // Sort state
    const [sortField, setSortField] = useState<SortField>('date');
    const [sortDirection, setSortDirection] = useState<SortDirection>('desc');

    // Edit state
    const [editingId, setEditingId] = useState<string | null>(null);
    const [editForm, setEditForm] = useState<EditFormData>(emptyForm);
    const [isBatchEditMode, setIsBatchEditMode] = useState(false);
    const [draftsById, setDraftsById] = useState<Record<string, EditFormData>>({});
    const [savingBatch, setSavingBatch] = useState(false);
    const [batchMessage, setBatchMessage] = useState<string>('');

    // Create modal state
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [createForm, setCreateForm] = useState<EditFormData>(emptyForm);

    // Pagination state
    const PAGE_SIZE = 200;
    const [totalCount, setTotalCount] = useState(0);
    const [currentPage, setCurrentPage] = useState(0);

    // Sorted transactions
    const sortedTransactions = useMemo(() => {
        const sorted = [...transactions].sort((a, b) => {
            let aVal = a[sortField];
            let bVal = b[sortField];

            // Handle numeric sorting for amount
            if (sortField === 'amount') {
                aVal = Number(aVal) || 0;
                bVal = Number(bVal) || 0;
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
        if (user) fetchTransactions();
    }, [user, startMonth, endMonth, ownerFilter, typeFilter, currentPage]);

    const fetchTransactions = async () => {
        setLoadingData(true);
        try {
            const filters: TransactionFilters = {};
            if (ownerFilter) filters.owner = ownerFilter;
            if (typeFilter) filters.txType = typeFilter;

            const result = await getTransactions(startMonth, endMonth, filters, PAGE_SIZE, currentPage * PAGE_SIZE);
            setTransactions(result.data ?? result);
            setTotalCount(result.total ?? (result.data ?? result).length);
        } catch (error) {
            console.error(error);
        } finally {
            setLoadingData(false);
        }
    };

    const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));

    const toEditForm = (tx: Transaction): EditFormData => ({
        date: tx.date,
        amount: tx.amount?.toString() || '',
        merchant_clean: tx.merchant_clean || '',
        category: tx.category || 'Outro',
        owner: tx.owner || owners[0] || '',
        type: tx.type || 'Shared'
    });

    const handleEditClick = (tx: Transaction) => {
        setEditingId(tx.id);
        setEditForm(toEditForm(tx));
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

    const startBatchEdit = () => {
        const nextDrafts: Record<string, EditFormData> = {};
        for (const tx of transactions) {
            nextDrafts[tx.id] = toEditForm(tx);
        }
        setDraftsById(nextDrafts);
        setIsBatchEditMode(true);
        setEditingId(null);
        setBatchMessage('');
    };

    const cancelBatchEdit = () => {
        setIsBatchEditMode(false);
        setDraftsById({});
        setBatchMessage('');
    };

    const updateDraftField = (id: string, field: keyof EditFormData, value: string) => {
        setDraftsById(prev => ({
            ...prev,
            [id]: {
                ...(prev[id] || emptyForm),
                [field]: value
            }
        }));
    };

    const buildPendingUpdates = (): PendingUpdate[] => {
        const updates: PendingUpdate[] = [];

        for (const tx of transactions) {
            const draft = draftsById[tx.id];
            if (!draft) continue;

            const parsedAmount = Number(draft.amount);
            const normalizedMerchant = draft.merchant_clean.trim();
            if (!Number.isFinite(parsedAmount) || !normalizedMerchant) continue;

            const changed =
                tx.date !== draft.date ||
                tx.amount !== parsedAmount ||
                tx.merchant_clean !== normalizedMerchant ||
                tx.category !== draft.category ||
                tx.owner !== draft.owner ||
                tx.type !== draft.type;

            if (!changed) continue;

            updates.push({
                id: tx.id,
                data: {
                    date: draft.date,
                    amount: parsedAmount,
                    merchant_clean: normalizedMerchant,
                    category: draft.category,
                    owner: draft.owner,
                    type: draft.type
                }
            });
        }

        return updates;
    };

    const pendingChanges = useMemo(() => buildPendingUpdates().length, [draftsById, transactions]);

    const saveBatchEdits = async () => {
        const updates = buildPendingUpdates();
        if (updates.length === 0) {
            setBatchMessage('Nenhuma alteração para salvar.');
            return;
        }

        setSavingBatch(true);
        setBatchMessage('');
        try {
            const results = await Promise.allSettled(
                updates.map((item) => updateTransaction(item.id, item.data))
            );
            const failed = results.filter(result => result.status === 'rejected').length;

            if (failed > 0) {
                setBatchMessage(`${failed} transação(ões) falharam ao salvar. Ajuste e tente novamente.`);
                return;
            }

            setBatchMessage(`${updates.length} transação(ões) salvas com sucesso.`);
            setIsBatchEditMode(false);
            setDraftsById({});
            await fetchTransactions();
        } catch (error) {
            console.error('Failed to save batch updates', error);
            setBatchMessage('Falha ao salvar alterações em lote.');
        } finally {
            setSavingBatch(false);
        }
    };

    return (
        <>
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
                                    disabled={isBatchEditMode}
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
                                    disabled={isBatchEditMode}
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
                                disabled={isBatchEditMode}
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
                                disabled={isBatchEditMode}
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

                    <div className="flex flex-col sm:flex-row gap-2 w-full md:w-auto">
                        {isBatchEditMode ? (
                            <>
                                <button
                                    onClick={saveBatchEdits}
                                    disabled={savingBatch}
                                    className="btn btn-primary w-full md:w-auto"
                                >
                                    {savingBatch ? (
                                        <>
                                            <Loader className="w-4 h-4 animate-spin" />
                                            Salvando...
                                        </>
                                    ) : (
                                        <>
                                            <Check className="w-4 h-4" />
                                            Salvar Tudo ({pendingChanges})
                                        </>
                                    )}
                                </button>
                                <button
                                    onClick={cancelBatchEdit}
                                    disabled={savingBatch}
                                    className="btn btn-ghost w-full md:w-auto border border-[var(--border-color)]"
                                >
                                    <X className="w-4 h-4" />
                                    Cancelar
                                </button>
                            </>
                        ) : (
                            <>
                                <button
                                    onClick={startBatchEdit}
                                    className="btn btn-ghost w-full md:w-auto border border-[var(--border-color)]"
                                >
                                    <Edit2 className="w-4 h-4" />
                                    Modo Editar
                                </button>
                                <button
                                    onClick={() => {
                                        setCreateForm({ ...emptyForm, owner: owners[0] || '' });
                                        setShowCreateModal(true);
                                    }}
                                    className="btn btn-primary w-full md:w-auto"
                                >
                                    <Plus className="w-4 h-4" />
                                    Nova Transação
                                </button>
                            </>
                        )}
                    </div>
                </div>

                {batchMessage && (
                    <div className="bg-[var(--bg-primary)] border border-[var(--border-color)] rounded-xl px-4 py-3 text-sm text-[var(--text-secondary)]">
                        {batchMessage}
                    </div>
                )}
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
                                {sortedTransactions.map((tx, index) => {
                                    const isSingleRowEditing = editingId === tx.id;
                                    const isRowEditing = isBatchEditMode || isSingleRowEditing;
                                    const rowForm = isBatchEditMode
                                        ? (draftsById[tx.id] || toEditForm(tx))
                                        : editForm;

                                    return (
                                        <tr
                                            key={tx.id}
                                            className={clsx(
                                                "border-b border-[var(--border-color)] hover:bg-[var(--bg-primary)] transition-colors",
                                                index % 2 === 0 ? "bg-white" : "bg-[var(--bg-primary)]/50"
                                            )}
                                        >
                                            <td className="py-3 px-4 text-sm font-mono">
                                                {isRowEditing ? (
                                                    <input
                                                        type="date"
                                                        value={rowForm.date}
                                                        onChange={(e) => (
                                                            isBatchEditMode
                                                                ? updateDraftField(tx.id, 'date', e.target.value)
                                                                : setEditForm({ ...editForm, date: e.target.value })
                                                        )}
                                                        className="input py-1 px-2 text-sm w-32"
                                                    />
                                                ) : (
                                                    <span className="text-[var(--text-secondary)]">{tx.date}</span>
                                                )}
                                            </td>
                                            <td className="py-3 px-4">
                                                {isRowEditing ? (
                                                    <input
                                                        type="text"
                                                        value={rowForm.merchant_clean}
                                                        onChange={(e) => (
                                                            isBatchEditMode
                                                                ? updateDraftField(tx.id, 'merchant_clean', e.target.value)
                                                                : setEditForm({ ...editForm, merchant_clean: e.target.value })
                                                        )}
                                                        className="input py-1 px-2 text-sm w-full max-w-[200px]"
                                                    />
                                                ) : (
                                                    <p className="text-sm font-medium text-[var(--text-primary)] truncate max-w-[200px]">
                                                        {tx.merchant_clean}
                                                    </p>
                                                )}
                                            </td>
                                            <td className="py-3 px-4">
                                                {isRowEditing ? (
                                                    <select
                                                        value={rowForm.owner}
                                                        onChange={(e) => (
                                                            isBatchEditMode
                                                                ? updateDraftField(tx.id, 'owner', e.target.value)
                                                                : setEditForm({ ...editForm, owner: e.target.value })
                                                        )}
                                                        className="input py-1 px-2 text-sm w-24"
                                                    >
                                                        {owners.map(o => (
                                                            <option key={o} value={o}>{o}</option>
                                                        ))}
                                                    </select>
                                                ) : (
                                                    <span className={clsx(
                                                        "inline-flex items-center px-2 py-1 rounded-full text-xs font-medium",
                                                        owners.indexOf(tx.owner) === 0
                                                            ? "bg-blue-100 text-blue-700"
                                                            : "bg-pink-100 text-pink-700"
                                                    )}>
                                                        {tx.owner}
                                                    </span>
                                                )}
                                            </td>
                                            <td className="py-3 px-4 text-right">
                                                {isRowEditing ? (
                                                    <input
                                                        type="number"
                                                        value={rowForm.amount}
                                                        onChange={(e) => (
                                                            isBatchEditMode
                                                                ? updateDraftField(tx.id, 'amount', e.target.value)
                                                                : setEditForm({ ...editForm, amount: e.target.value })
                                                        )}
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
                                                {isRowEditing ? (
                                                    <select
                                                        value={rowForm.category}
                                                        onChange={(e) => (
                                                            isBatchEditMode
                                                                ? updateDraftField(tx.id, 'category', e.target.value)
                                                                : setEditForm({ ...editForm, category: e.target.value })
                                                        )}
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
                                                {isRowEditing ? (
                                                    <select
                                                        value={rowForm.type}
                                                        onChange={(e) => (
                                                            isBatchEditMode
                                                                ? updateDraftField(tx.id, 'type', e.target.value)
                                                                : setEditForm({ ...editForm, type: e.target.value })
                                                        )}
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
                                                {isBatchEditMode ? (
                                                    <span className="text-xs text-[var(--text-secondary)]">Em lote</span>
                                                ) : isSingleRowEditing ? (
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
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>

                    {/* Mobile Cards */}
                    <div className="md:hidden space-y-3 animate-fade-in">
                        {sortedTransactions.map((tx) => {
                            const isSingleRowEditing = editingId === tx.id;
                            const isRowEditing = isBatchEditMode || isSingleRowEditing;
                            const rowForm = isBatchEditMode
                                ? (draftsById[tx.id] || toEditForm(tx))
                                : editForm;

                            return (
                                <div key={tx.id} className="card p-4">
                                    {isRowEditing ? (
                                        <div className="space-y-3">
                                            <input
                                                type="text"
                                                value={rowForm.merchant_clean}
                                                onChange={(e) => (
                                                    isBatchEditMode
                                                        ? updateDraftField(tx.id, 'merchant_clean', e.target.value)
                                                        : setEditForm({ ...editForm, merchant_clean: e.target.value })
                                                )}
                                                className="input w-full"
                                            />
                                            <div className="grid grid-cols-2 gap-2">
                                                <input
                                                    type="date"
                                                    value={rowForm.date}
                                                    onChange={(e) => (
                                                        isBatchEditMode
                                                            ? updateDraftField(tx.id, 'date', e.target.value)
                                                            : setEditForm({ ...editForm, date: e.target.value })
                                                    )}
                                                    className="input w-full"
                                                />
                                                <input
                                                    type="number"
                                                    value={rowForm.amount}
                                                    onChange={(e) => (
                                                        isBatchEditMode
                                                            ? updateDraftField(tx.id, 'amount', e.target.value)
                                                            : setEditForm({ ...editForm, amount: e.target.value })
                                                    )}
                                                    className="input w-full"
                                                    step="0.01"
                                                />
                                            </div>
                                            <div className="grid grid-cols-2 gap-2">
                                                <select
                                                    value={rowForm.owner}
                                                    onChange={(e) => (
                                                        isBatchEditMode
                                                            ? updateDraftField(tx.id, 'owner', e.target.value)
                                                            : setEditForm({ ...editForm, owner: e.target.value })
                                                    )}
                                                    className="input w-full"
                                                >
                                                    {owners.map(o => (
                                                        <option key={o} value={o}>{o}</option>
                                                    ))}
                                                </select>
                                                <select
                                                    value={rowForm.type}
                                                    onChange={(e) => (
                                                        isBatchEditMode
                                                            ? updateDraftField(tx.id, 'type', e.target.value)
                                                            : setEditForm({ ...editForm, type: e.target.value })
                                                    )}
                                                    className="input w-full"
                                                >
                                                    {TYPES.map(type => (
                                                        <option key={type} value={type}>{type}</option>
                                                    ))}
                                                </select>
                                            </div>
                                            <select
                                                value={rowForm.category}
                                                onChange={(e) => (
                                                    isBatchEditMode
                                                        ? updateDraftField(tx.id, 'category', e.target.value)
                                                        : setEditForm({ ...editForm, category: e.target.value })
                                                )}
                                                className="input w-full"
                                            >
                                                {CATEGORIES.map(cat => (
                                                    <option key={cat} value={cat}>{cat}</option>
                                                ))}
                                            </select>
                                            {!isBatchEditMode && (
                                                <div className="flex justify-end gap-2">
                                                    <button
                                                        onClick={() => handleSave(tx.id)}
                                                        className="btn btn-primary"
                                                    >
                                                        Salvar
                                                    </button>
                                                    <button
                                                        onClick={handleCancel}
                                                        className="btn btn-ghost border border-[var(--border-color)]"
                                                    >
                                                        Cancelar
                                                    </button>
                                                </div>
                                            )}
                                        </div>
                                    ) : (
                                        <>
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
                                                    owners.indexOf(tx.owner) === 0 ? "bg-blue-100 text-blue-700" : "bg-pink-100 text-pink-700"
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
                                        </>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </>
            )}

            {/* Pagination Controls */}
            {totalPages > 1 && (
                <div className="flex items-center justify-between mt-4 px-2">
                    <p className="text-sm text-[var(--text-secondary)]">
                        {totalCount} transações · Página {currentPage + 1} de {totalPages}
                    </p>
                    <div className="flex gap-2">
                        <button
                            onClick={() => setCurrentPage(p => Math.max(0, p - 1))}
                            disabled={currentPage === 0 || isBatchEditMode}
                            className="btn btn-ghost text-sm px-3 py-1.5 border border-[var(--border-color)] disabled:opacity-40"
                        >
                            Anterior
                        </button>
                        <button
                            onClick={() => setCurrentPage(p => Math.min(totalPages - 1, p + 1))}
                            disabled={currentPage >= totalPages - 1 || isBatchEditMode}
                            className="btn btn-ghost text-sm px-3 py-1.5 border border-[var(--border-color)] disabled:opacity-40"
                        >
                            Próxima
                        </button>
                    </div>
                </div>
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
                                        {owners.map(o => (
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
        </>
    );
}
