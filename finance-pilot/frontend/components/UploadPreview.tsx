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

  const needsReviewCount = data.transactions.filter((t) => t.needs_review).length;
  const unregisteredCardCount = unregisteredCards.length;
  const totalAmount = data.transactions.reduce((sum, t) => sum + t.amount, 0);

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
          <p className="text-sm font-bold text-[var(--color-text-primary)]">
            R$ {totalAmount.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
          </p>
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
      {(unregisteredCardCount > 0 || needsReviewCount > 0) && (
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
        </div>
      )}

      {/* Transactions Table */}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--color-border)] bg-[var(--color-bg-accent)]">
                <th className="text-left px-4 py-3 font-semibold text-[var(--color-text-secondary)] text-xs uppercase tracking-wide">
                  Data
                </th>
                <th className="text-left px-4 py-3 font-semibold text-[var(--color-text-secondary)] text-xs uppercase tracking-wide">
                  Descrição
                </th>
                <th className="text-left px-4 py-3 font-semibold text-[var(--color-text-secondary)] text-xs uppercase tracking-wide hidden sm:table-cell">
                  Cartão
                </th>
                <th className="text-right px-4 py-3 font-semibold text-[var(--color-text-secondary)] text-xs uppercase tracking-wide">
                  Valor
                </th>
                <th className="text-left px-4 py-3 font-semibold text-[var(--color-text-secondary)] text-xs uppercase tracking-wide hidden md:table-cell">
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
                    <td className="px-4 py-3 text-[var(--color-text-primary)]">
                      <div className="flex items-center gap-2">
                        <span className="truncate max-w-[200px] sm:max-w-none">
                          {tx.description}
                        </span>
                        {tx.is_refund && (
                          <span className="shrink-0 text-[10px] font-semibold bg-green-100 text-green-700 px-1.5 py-0.5 rounded">
                            ESTORNO
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-[var(--color-text-secondary)] hidden sm:table-cell">
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
                    <td className="px-4 py-3 hidden md:table-cell">
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
