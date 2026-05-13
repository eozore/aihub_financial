'use client';

import { useState } from 'react';
import {
  UploadPreviewResponse,
  PreviewTransaction,
  confirmUpload,
  ConfirmedTransaction,
} from '../services/api';
import {
  ArrowLeft,
  Check,
  Loader,
  AlertTriangle,
  CreditCard,
  Calendar,
  DollarSign,
} from 'lucide-react';
import clsx from 'clsx';
import CardOnboarding from './CardOnboarding';

interface UploadPreviewProps {
  data: UploadPreviewResponse;
  onBack: () => void;
  onConfirmed: () => void;
}

export default function UploadPreview({ data, onBack, onConfirmed }: UploadPreviewProps) {
  const [status, setStatus] = useState<'idle' | 'confirming' | 'success' | 'error'>('idle');
  const [message, setMessage] = useState('');
  const [showCardOnboarding, setShowCardOnboarding] = useState(
    data.unregistered_cards.length > 0
  );
  const [unregisteredCards, setUnregisteredCards] = useState<string[]>(
    data.unregistered_cards
  );

  // User inputs for owner and month_ref
  const [selectedOwner, setSelectedOwner] = useState<string>('Victor Z');
  const [selectedMonthRef, setSelectedMonthRef] = useState<string>(
    data.period_end ? data.period_end.substring(0, 7) : new Date().toISOString().substring(0, 7)
  );

  const needsReviewCount = data.transactions.filter((t) => t.needs_review).length;
  const unregisteredCardCount = unregisteredCards.length;

  // Sum of extracted purchases (excluding refunds) — used for validation
  const extractedPurchasesTotal = data.transactions
    .filter((t) => !t.is_refund)
    .reduce((sum, t) => sum + t.amount, 0);

  // Total shown to user = purchases minus refunds
  const totalAmount = data.transactions.reduce(
    (sum, t) => sum + (t.is_refund ? -t.amount : t.amount),
    0
  );

  // Validation: compare extracted sum against the cover page total_amount
  // Allow up to 1% or R$5 tolerance (rounding differences)
  const coverTotal = data.total_amount;
  const amountDiff = Math.abs(extractedPurchasesTotal - coverTotal);
  const amountDiffPct = coverTotal > 0 ? (amountDiff / coverTotal) * 100 : 0;
  const hasAmountMismatch = coverTotal > 0 && amountDiff > 5 && amountDiffPct > 1;

  const handleConfirm = async () => {
    setStatus('confirming');
    setMessage('');

    try {
      const transactions: ConfirmedTransaction[] = data.transactions.map(
        (t: PreviewTransaction) => ({
          date: t.date,
          card_last4: t.card_last4,
          description: t.description,
          amount: t.amount,
          is_refund: t.is_refund,
          category: t.suggested_category,
          owner: data.holder_name,
        })
      );

      await confirmUpload({
        file_hash: data.file_hash,
        statement_type: data.statement_type,
        bank: data.bank,
        month_ref: selectedMonthRef,
        owner: selectedOwner,
        transactions,
      });

      setStatus('success');
      setMessage(
        `${data.transactions.length} transações importadas com sucesso!`
      );
    } catch (error: unknown) {
      setStatus('error');
      const axiosError = error as { response?: { data?: { detail?: string } } };
      setMessage(
        axiosError.response?.data?.detail || 'Erro ao confirmar importação.'
      );
    }
  };

  const handleCardOnboardingComplete = () => {
    setShowCardOnboarding(false);
    setUnregisteredCards([]);
  };

  const handleCardOnboardingSkip = () => {
    setShowCardOnboarding(false);
  };

  // Show success state
  if (status === 'success') {
    return (
      <div className="space-y-6">
        <div className="card p-8 text-center">
          <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <Check className="w-8 h-8 text-green-600" />
          </div>
          <h2 className="text-xl font-bold text-[var(--color-text-primary)] mb-2">
            Importação concluída
          </h2>
          <p className="text-[var(--color-text-secondary)] mb-6">{message}</p>
          <button onClick={onConfirmed} className="btn btn-primary">
            Voltar ao início
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Card Onboarding Modal */}
      {showCardOnboarding && (
        <CardOnboarding
          unregisteredCards={unregisteredCards}
          holderName={data.holder_name}
          onComplete={handleCardOnboardingComplete}
          onSkip={handleCardOnboardingSkip}
        />
      )}

      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          onClick={onBack}
          className="p-2 hover:bg-[var(--color-bg-accent)] rounded-lg transition-colors"
          aria-label="Voltar"
        >
          <ArrowLeft className="w-5 h-5 text-[var(--color-text-secondary)]" />
        </button>
        <div>
          <h2 className="text-lg font-bold text-[var(--color-text-primary)]">
            Preview da Importação
          </h2>
          <p className="text-sm text-[var(--color-text-secondary)]">
            Revise as transações antes de confirmar
          </p>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="card p-4">
          <div className="flex items-center gap-2 mb-1">
            <CreditCard className="w-4 h-4 text-[var(--color-text-muted)]" />
            <span className="text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wide">
              Banco
            </span>
          </div>
          <p className="text-sm font-bold text-[var(--color-text-primary)] capitalize">
            {data.bank}
          </p>
        </div>
        <div className="card p-4">
          <div className="flex items-center gap-2 mb-1">
            <Calendar className="w-4 h-4 text-[var(--color-text-muted)]" />
            <span className="text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wide">
              Período
            </span>
          </div>
          <p className="text-sm font-bold text-[var(--color-text-primary)]">
            {data.period_start} — {data.period_end}
          </p>
        </div>
        <div className="card p-4">
          <div className="flex items-center gap-2 mb-1">
            <DollarSign className="w-4 h-4 text-[var(--color-text-muted)]" />
            <span className="text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wide">
              Total
            </span>
          </div>
          <p className={clsx(
            "text-sm font-bold",
            hasAmountMismatch ? "text-red-600" : "text-[var(--color-text-primary)]"
          )}>
            R$ {totalAmount.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
          </p>
          {hasAmountMismatch && (
            <p className="text-xs text-red-500 mt-0.5">
              Capa: R$ {coverTotal.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
            </p>
          )}
        </div>
        <div className="card p-4">
          <div className="flex items-center gap-2 mb-1">
            <AlertTriangle className="w-4 h-4 text-[var(--color-text-muted)]" />
            <span className="text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wide">
              Transações
            </span>
          </div>
          <p className="text-sm font-bold text-[var(--color-text-primary)]">
            {data.transactions.length}
          </p>
        </div>
      </div>

      {/* Warnings */}
      {(unregisteredCardCount > 0 || needsReviewCount > 0 || hasAmountMismatch) && (
        <div className="space-y-2">
          {unregisteredCardCount > 0 && (
            <div className="flex items-center gap-2 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>
                <strong>{unregisteredCardCount}</strong> cartão(ões) não cadastrado(s) detectado(s).
              </span>
              <button
                onClick={() => setShowCardOnboarding(true)}
                className="ml-auto text-xs font-semibold text-amber-700 hover:text-amber-900 underline"
              >
                Cadastrar agora
              </button>
            </div>
          )}
          {needsReviewCount > 0 && (
            <div className="flex items-center gap-2 p-3 bg-orange-50 border border-orange-200 rounded-lg text-sm text-orange-800">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>
                <strong>{needsReviewCount}</strong> transação(ões) precisam de revisão (categoria não identificada).
              </span>
            </div>
          )}
          {hasAmountMismatch && (
            <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold">Divergência no valor total detectada</p>
                <p className="text-xs mt-0.5">
                  Soma das transações extraídas:{' '}
                  <strong>
                    R$ {extractedPurchasesTotal.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                  </strong>
                  {' '}— Valor na capa do PDF:{' '}
                  <strong>
                    R$ {coverTotal.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                  </strong>
                  {' '}(diferença de R$ {amountDiff.toLocaleString('pt-BR', { minimumFractionDigits: 2 })},{' '}
                  {amountDiffPct.toFixed(1)}%). Verifique se alguma transação foi perdida na extração.
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Transactions Table */}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm" style={{ minWidth: '700px' }}>
            <thead>
              <tr className="border-b border-[var(--color-border)] bg-[var(--color-bg-accent)]">
                <th className="text-left px-4 py-3 font-semibold text-[var(--color-text-secondary)] text-xs uppercase tracking-wide whitespace-nowrap">
                  Data
                </th>
                <th className="text-left px-4 py-3 font-semibold text-[var(--color-text-secondary)] text-xs uppercase tracking-wide">
                  Descrição
                </th>
                <th className="text-left px-4 py-3 font-semibold text-[var(--color-text-secondary)] text-xs uppercase tracking-wide whitespace-nowrap">
                  Cartão
                </th>
                <th className="text-right px-4 py-3 font-semibold text-[var(--color-text-secondary)] text-xs uppercase tracking-wide whitespace-nowrap">
                  Valor
                </th>
                <th className="text-left px-4 py-3 font-semibold text-[var(--color-text-secondary)] text-xs uppercase tracking-wide whitespace-nowrap">
                  Categoria
                </th>
              </tr>
            </thead>
            <tbody>
              {data.transactions.map((tx: PreviewTransaction, idx: number) => {
                const isUnregisteredCard =
                  tx.card_last4 != null &&
                  unregisteredCards.includes(tx.card_last4);
                const isNeedsReview = tx.needs_review;

                return (
                  <tr
                    key={idx}
                    className={clsx(
                      'border-b border-[var(--color-border)] last:border-b-0 transition-colors',
                      isUnregisteredCard && 'bg-amber-50',
                      isNeedsReview && !isUnregisteredCard && 'bg-orange-50'
                    )}
                  >
                    <td className="px-4 py-3 text-[var(--color-text-primary)] whitespace-nowrap">
                      {tx.date}
                    </td>
                    <td className="px-4 py-3 text-[var(--color-text-primary)] min-w-[200px]">
                      <div className="flex items-center gap-2">
                        <span>{tx.description}</span>
                        {tx.is_refund && (
                          <span className="shrink-0 text-[10px] font-semibold bg-green-100 text-green-700 px-1.5 py-0.5 rounded">
                            ESTORNO
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-[var(--color-text-secondary)] whitespace-nowrap">
                      {tx.card_last4 ? (
                        <span
                          className={clsx(
                            'inline-flex items-center gap-1 text-xs font-mono px-2 py-0.5 rounded',
                            isUnregisteredCard
                              ? 'bg-amber-100 text-amber-800'
                              : 'bg-gray-100 text-gray-700'
                          )}
                        >
                          •••• {tx.card_last4}
                        </span>
                      ) : (
                        <span className="text-[var(--color-text-muted)]">—</span>
                      )}
                    </td>
                    <td
                      className={clsx(
                        'px-4 py-3 text-right font-medium whitespace-nowrap',
                        tx.is_refund
                          ? 'text-green-600'
                          : 'text-[var(--color-text-primary)]'
                      )}
                    >
                      {tx.is_refund ? '+' : ''}R${' '}
                      {Math.abs(tx.amount).toLocaleString('pt-BR', {
                        minimumFractionDigits: 2,
                      })}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <span
                        className={clsx(
                          'inline-block text-xs font-medium px-2 py-0.5 rounded',
                          isNeedsReview
                            ? 'bg-orange-100 text-orange-700'
                            : 'bg-[var(--color-bg-accent)] text-[var(--color-text-secondary)]'
                        )}
                      >
                        {tx.suggested_category}
                        {isNeedsReview && ' ⚠'}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Error Message */}
      {status === 'error' && message && (
        <div className="p-4 rounded-lg text-sm flex items-center gap-2 bg-red-50 text-red-700 border border-red-200">
          <AlertTriangle className="w-5 h-5 shrink-0" />
          {message}
        </div>
      )}

      {/* Owner and Month Ref Inputs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 p-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)]">
        <div>
          <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">
            Owner (responsável)
          </label>
          <select
            value={selectedOwner}
            onChange={(e) => setSelectedOwner(e.target.value)}
            className="w-full px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg-primary)] text-sm"
          >
            <option value="Victor Z">Victor Z</option>
            <option value="Larissa C">Larissa C</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">
            Mês referência
          </label>
          <input
            type="month"
            value={selectedMonthRef}
            onChange={(e) => setSelectedMonthRef(e.target.value)}
            className="w-full px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg-primary)] text-sm"
          />
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex flex-col sm:flex-row gap-3">
        <button
          onClick={onBack}
          className="btn btn-ghost flex-1 h-12 border border-[var(--color-border)]"
        >
          Cancelar
        </button>
        <button
          onClick={handleConfirm}
          disabled={status === 'confirming'}
          className={clsx(
            'btn btn-primary flex-1 h-12',
            status === 'confirming' && 'opacity-50 cursor-not-allowed'
          )}
        >
          {status === 'confirming' ? (
            <>
              <Loader className="w-5 h-5 animate-spin" />
              Importando...
            </>
          ) : (
            <>
              <Check className="w-5 h-5" />
              Confirmar e Importar ({data.transactions.length} transações)
            </>
          )}
        </button>
      </div>
    </div>
  );
}
