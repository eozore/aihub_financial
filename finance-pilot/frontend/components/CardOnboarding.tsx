'use client';

import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { createCard } from '../services/api';
import { CreditCard, Loader, X, Check } from 'lucide-react';
import clsx from 'clsx';

interface CardOnboardingProps {
  unregisteredCards: string[];
  holderName: string;
  onComplete: () => void;
  onSkip: () => void;
}

interface CardEntry {
  last4: string;
  card_type: 'individual' | 'shared';
  saving: boolean;
  saved: boolean;
  error: string | null;
}

export default function CardOnboarding({
  unregisteredCards,
  holderName,
  onComplete,
  onSkip,
}: CardOnboardingProps) {
  const [cards, setCards] = useState<CardEntry[]>(
    unregisteredCards.map((last4) => ({
      last4,
      card_type: 'individual',
      saving: false,
      saved: false,
      error: null,
    }))
  );
  const [savingAll, setSavingAll] = useState(false);

  const allSaved = cards.every((c) => c.saved);

  const updateCardType = (index: number, card_type: 'individual' | 'shared') => {
    setCards((prev) =>
      prev.map((c, i) => (i === index ? { ...c, card_type } : c))
    );
  };

  const handleSaveAll = async () => {
    setSavingAll(true);
    const unsaved = cards.filter((c) => !c.saved);

    for (let i = 0; i < cards.length; i++) {
      if (cards[i].saved) continue;

      setCards((prev) =>
        prev.map((c, idx) => (idx === i ? { ...c, saving: true, error: null } : c))
      );

      try {
        await createCard({
          owner: holderName,
          last4: cards[i].last4,
          card_type: cards[i].card_type,
          bank: 'nubank',
        });

        setCards((prev) =>
          prev.map((c, idx) =>
            idx === i ? { ...c, saving: false, saved: true } : c
          )
        );
      } catch (error: unknown) {
        const axiosError = error as { response?: { data?: { detail?: string } } };
        const errorMsg =
          axiosError.response?.data?.detail || 'Erro ao salvar cartão';

        setCards((prev) =>
          prev.map((c, idx) =>
            idx === i ? { ...c, saving: false, error: errorMsg } : c
          )
        );
      }
    }

    setSavingAll(false);

    // Check if all saved after the loop
    setCards((prev) => {
      const nowAllSaved = prev.every((c) => c.saved);
      if (nowAllSaved) {
        // Delay to show success state briefly
        setTimeout(() => onComplete(), 600);
      }
      return prev;
    });
  };

  return (
    <Dialog.Root open onOpenChange={(open) => { if (!open) onSkip(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40 z-50 animate-fade-in" />
        <Dialog.Content
          className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-[calc(100%-2rem)] max-w-lg max-h-[85vh] overflow-y-auto bg-white rounded-2xl shadow-lg p-6 animate-fade-in"
          aria-describedby="card-onboarding-description"
        >
          <div className="flex items-center justify-between mb-4">
            <Dialog.Title className="text-lg font-bold text-[var(--color-text-primary)] flex items-center gap-2">
              <CreditCard className="w-5 h-5 text-[var(--color-brand-primary)]" />
              Cartões Detectados
            </Dialog.Title>
            <Dialog.Close asChild>
              <button
                className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors"
                aria-label="Fechar"
              >
                <X className="w-5 h-5 text-[var(--color-text-secondary)]" />
              </button>
            </Dialog.Close>
          </div>

          <p
            id="card-onboarding-description"
            className="text-sm text-[var(--color-text-secondary)] mb-6"
          >
            Encontramos cartões na fatura que ainda não estão cadastrados.
            Classifique cada um como <strong>individual</strong> ou{' '}
            <strong>compartilhado</strong> para que as transações sejam
            categorizadas corretamente.
          </p>

          {/* Card List */}
          <div className="space-y-3 mb-6">
            {cards.map((card, index) => (
              <div
                key={card.last4}
                className={clsx(
                  'p-4 rounded-xl border transition-all',
                  card.saved
                    ? 'border-green-200 bg-green-50'
                    : card.error
                    ? 'border-red-200 bg-red-50'
                    : 'border-[var(--color-border)] bg-white'
                )}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div
                      className={clsx(
                        'w-10 h-10 rounded-lg flex items-center justify-center',
                        card.saved
                          ? 'bg-green-100'
                          : 'bg-[var(--color-bg-accent)]'
                      )}
                    >
                      {card.saved ? (
                        <Check className="w-5 h-5 text-green-600" />
                      ) : card.saving ? (
                        <Loader className="w-5 h-5 text-[var(--color-brand-primary)] animate-spin" />
                      ) : (
                        <CreditCard className="w-5 h-5 text-[var(--color-text-muted)]" />
                      )}
                    </div>
                    <div>
                      <p className="font-mono text-sm font-semibold text-[var(--color-text-primary)]">
                        •••• {card.last4}
                      </p>
                      {card.saved && (
                        <p className="text-xs text-green-600 font-medium">
                          Cadastrado
                        </p>
                      )}
                      {card.error && (
                        <p className="text-xs text-red-600">{card.error}</p>
                      )}
                    </div>
                  </div>

                  {!card.saved && (
                    <div className="flex gap-1">
                      <button
                        type="button"
                        onClick={() => updateCardType(index, 'individual')}
                        disabled={card.saving}
                        className={clsx(
                          'px-3 py-1.5 text-xs font-medium rounded-lg transition-all',
                          card.card_type === 'individual'
                            ? 'bg-[var(--color-brand-primary)] text-white'
                            : 'bg-gray-100 text-[var(--color-text-secondary)] hover:bg-gray-200'
                        )}
                      >
                        Individual
                      </button>
                      <button
                        type="button"
                        onClick={() => updateCardType(index, 'shared')}
                        disabled={card.saving}
                        className={clsx(
                          'px-3 py-1.5 text-xs font-medium rounded-lg transition-all',
                          card.card_type === 'shared'
                            ? 'bg-[var(--color-brand-primary)] text-white'
                            : 'bg-gray-100 text-[var(--color-text-secondary)] hover:bg-gray-200'
                        )}
                      >
                        Compartilhado
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Actions */}
          <div className="flex flex-col sm:flex-row gap-2">
            <button
              onClick={onSkip}
              className="btn btn-ghost flex-1 h-10 border border-[var(--color-border)] text-sm"
            >
              Pular por agora
            </button>
            <button
              onClick={handleSaveAll}
              disabled={savingAll || allSaved}
              className={clsx(
                'btn btn-primary flex-1 h-10 text-sm',
                (savingAll || allSaved) && 'opacity-50 cursor-not-allowed'
              )}
            >
              {savingAll ? (
                <>
                  <Loader className="w-4 h-4 animate-spin" />
                  Salvando...
                </>
              ) : allSaved ? (
                <>
                  <Check className="w-4 h-4" />
                  Todos cadastrados
                </>
              ) : (
                <>
                  <CreditCard className="w-4 h-4" />
                  Cadastrar Cartões
                </>
              )}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
