'use client';

import { FormEvent, useEffect, useState } from 'react';
import { CreditCard, Edit2, Loader, Plus, Save, Trash2, User, X } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { api, getMe, updateMyProfile } from '@/services/api';
import clsx from 'clsx';

// ─── CPF mask ───────────────────────────────────────────────
function formatCpf(value: string): string {
  const digits = value.replace(/\D/g, '').slice(0, 11);
  if (digits.length <= 3) return digits;
  if (digits.length <= 6) return `${digits.slice(0, 3)}.${digits.slice(3)}`;
  if (digits.length <= 9) return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6)}`;
  return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6, 9)}-${digits.slice(9)}`;
}

// ─── Card types ──────────────────────────────────────────────
interface Card {
  id: string;
  last4: string;
  label: string | null;
  card_type: 'individual' | 'shared';
  owner: string;
  bank: string;
}

interface CardForm {
  last4: string;
  label: string;
  card_type: 'individual' | 'shared';
  owner: string;
  bank: string;
}

const emptyCardForm: CardForm = {
  last4: '',
  label: '',
  card_type: 'individual',
  owner: '',
  bank: 'nubank',
};

// ─── TypeToggle helper ───────────────────────────────────────
function TypeToggle({
  value,
  onChange,
}: {
  value: 'individual' | 'shared';
  onChange: (v: 'individual' | 'shared') => void;
}) {
  return (
    <div className="flex gap-2">
      {(['individual', 'shared'] as const).map((t) => (
        <button
          key={t}
          type="button"
          onClick={() => onChange(t)}
          className={clsx(
            'flex-1 py-2 rounded-lg text-sm font-medium border transition-all',
            value === t
              ? 'bg-[var(--color-brand-primary)] text-white border-[var(--color-brand-primary)]'
              : 'bg-white text-[var(--color-text-secondary)] border-[var(--color-border)] hover:border-[var(--color-brand-primary)]'
          )}
        >
          {t === 'individual' ? 'Individual' : 'Compartilhado'}
        </button>
      ))}
    </div>
  );
}

// ─── Main page ───────────────────────────────────────────────
export default function ProfilePage() {
  const { user } = useAuth();

  // Profile state
  const [loadingProfile, setLoadingProfile] = useState(true);
  const [savingProfile, setSavingProfile] = useState(false);
  const [profileMessage, setProfileMessage] = useState<string | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState('');
  const [shortName, setShortName] = useState('');
  const [photoUrl, setPhotoUrl] = useState('');
  const [birthDate, setBirthDate] = useState('');
  const [cpf, setCpf] = useState('');
  const [address, setAddress] = useState('');

  // Cards state
  const [cards, setCards] = useState<Card[]>([]);
  const [loadingCards, setLoadingCards] = useState(true);
  const [savingCard, setSavingCard] = useState(false);
  const [cardError, setCardError] = useState<string | null>(null);
  const [cardMessage, setCardMessage] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState<CardForm>(emptyCardForm);
  const [editingCardId, setEditingCardId] = useState<string | null>(null);
  const [editCardForm, setEditCardForm] = useState<CardForm>(emptyCardForm);

  // Load profile
  useEffect(() => {
    if (!user) return;
    let mounted = true;
    (async () => {
      setLoadingProfile(true);
      try {
        const me = await getMe();
        if (!mounted) return;
        setDisplayName(me.display_name || '');
        setShortName(me.short_name || '');
        setPhotoUrl(me.photo_url || '');
      } catch (e: any) {
        if (mounted) setProfileError(e?.response?.data?.detail || 'Erro ao carregar perfil.');
      } finally {
        if (mounted) setLoadingProfile(false);
      }
    })();
    return () => { mounted = false; };
  }, [user]);

  // Load cards
  const loadCards = async () => {
    setLoadingCards(true);
    try {
      const res = await api.get('/cards');
      setCards(res.data || []);
    } catch (e: any) {
      setCardError(e?.response?.data?.detail || 'Erro ao carregar cartões.');
    } finally {
      setLoadingCards(false);
    }
  };

  useEffect(() => {
    if (user) loadCards();
  }, [user]);

  // Save profile
  const handleSaveProfile = async (e: FormEvent) => {
    e.preventDefault();
    if (!displayName.trim()) { setProfileError('Nome de exibição é obrigatório.'); return; }
    setSavingProfile(true);
    setProfileError(null);
    setProfileMessage(null);
    try {
      await updateMyProfile({
        display_name: displayName.trim(),
        short_name: shortName.trim() || undefined,
        photo_url: photoUrl.trim() || undefined,
        birth_date: birthDate || undefined,
        cpf: cpf.replace(/\D/g, '') || undefined,
        address: address.trim() || undefined,
      });
      setProfileMessage('Perfil atualizado com sucesso.');
    } catch (e: any) {
      setProfileError(e?.response?.data?.detail || 'Erro ao salvar perfil.');
    } finally {
      setSavingProfile(false);
    }
  };

  // Create card
  const handleCreateCard = async () => {
    if (!/^\d{4}$/.test(createForm.last4)) {
      setCardError('Os 4 dígitos finais devem ser exatamente 4 números.');
      return;
    }
    setSavingCard(true);
    setCardError(null);
    setCardMessage(null);
    try {
      await api.post('/cards', {
        last4: createForm.last4,
        label: createForm.label || null,
        card_type: createForm.card_type,
        owner: createForm.owner || displayName || 'default',
        bank: createForm.bank || 'nubank',
      });
      setCardMessage('Cartão cadastrado.');
      setShowCreate(false);
      setCreateForm(emptyCardForm);
      await loadCards();
    } catch (e: any) {
      setCardError(e?.response?.data?.detail || 'Erro ao cadastrar cartão.');
    } finally {
      setSavingCard(false);
    }
  };

  // Edit card
  const startEditCard = (card: Card) => {
    setEditingCardId(card.id);
    setEditCardForm({ last4: card.last4, label: card.label || '', card_type: card.card_type, owner: card.owner, bank: card.bank });
    setCardError(null);
    setCardMessage(null);
  };

  const handleSaveCard = async () => {
    if (!editingCardId) return;
    setSavingCard(true);
    setCardError(null);
    setCardMessage(null);
    try {
      await api.put(`/cards/${editingCardId}`, {
        label: editCardForm.label || null,
        card_type: editCardForm.card_type,
        owner: editCardForm.owner || displayName || 'default',
        bank: editCardForm.bank || 'nubank',
      });
      setCardMessage('Cartão atualizado.');
      setEditingCardId(null);
      await loadCards();
    } catch (e: any) {
      setCardError(e?.response?.data?.detail || 'Erro ao atualizar cartão.');
    } finally {
      setSavingCard(false);
    }
  };

  // Delete card
  const handleDeleteCard = async (card: Card) => {
    if (!confirm(`Excluir cartão final ${card.last4}${card.label ? ` (${card.label})` : ''}?`)) return;
    setSavingCard(true);
    setCardError(null);
    setCardMessage(null);
    try {
      await api.delete(`/cards/${card.id}`);
      setCardMessage('Cartão removido.');
      await loadCards();
    } catch (e: any) {
      setCardError(e?.response?.data?.detail || 'Erro ao remover cartão.');
    } finally {
      setSavingCard(false);
    }
  };

  const isLoading = loadingProfile || loadingCards;

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Meu Perfil</h1>
        <p className="page-subtitle">Informações pessoais e configuração de cartões</p>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16">
          <Loader className="w-8 h-8 animate-spin text-[var(--color-brand-primary)]" />
        </div>
      ) : (
        <div className="max-w-5xl space-y-6 animate-fade-in">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">

          {/* ── PROFILE SECTION ── */}
          <div className="card p-6 space-y-5">
            <h2 className="text-base font-semibold text-[var(--color-text-primary)]">Dados pessoais</h2>

            {profileError && (
              <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{profileError}</div>
            )}
            {profileMessage && (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{profileMessage}</div>
            )}

            {/* Avatar */}
            <div className="flex items-center gap-4">
              <div className="w-14 h-14 rounded-full bg-[var(--color-bg-accent)] border border-[var(--color-border)] flex items-center justify-center overflow-hidden flex-shrink-0">
                {photoUrl ? (
                  <img src={photoUrl} alt="Foto" className="w-full h-full object-cover"
                    onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }} />
                ) : (
                  <User className="w-7 h-7 text-[var(--color-text-muted)]" />
                )}
              </div>
              <div>
                <p className="text-sm font-medium text-[var(--color-text-primary)]">{displayName || 'Sem nome'}</p>
                <p className="text-xs text-[var(--color-text-muted)]">{user?.email}</p>
              </div>
            </div>

            <form onSubmit={handleSaveProfile} className="space-y-4">
              <div>
                <label className="label">E-mail</label>
                <input type="email" value={user?.email || ''} readOnly
                  className="input bg-[var(--color-bg-accent)] cursor-not-allowed text-[var(--color-text-muted)]" />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="label">Nome de exibição <span className="text-red-500">*</span></label>
                  <input type="text" value={displayName} onChange={(e) => setDisplayName(e.target.value)}
                    className="input" placeholder="Ex.: Victor Z" required />
                  <p className="mt-1 text-xs text-[var(--color-text-muted)]">Aparece nas transações e no dashboard.</p>
                </div>
                <div>
                  <label className="label">Nome curto</label>
                  <input type="text" value={shortName} onChange={(e) => setShortName(e.target.value)}
                    className="input" placeholder="Ex.: Victor" />
                  <p className="mt-1 text-xs text-[var(--color-text-muted)]">Usado em gráficos e filtros.</p>
                </div>
              </div>
              <div>
                <label className="label">URL da foto de perfil</label>
                <input type="url" value={photoUrl} onChange={(e) => setPhotoUrl(e.target.value)}
                  className="input" placeholder="https://exemplo.com/foto.jpg" />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="label">Data de nascimento</label>
                  <input type="date" value={birthDate} onChange={(e) => setBirthDate(e.target.value)} className="input" />
                </div>
                <div>
                  <label className="label">CPF</label>
                  <input type="text" value={cpf} onChange={(e) => setCpf(formatCpf(e.target.value))}
                    className="input" placeholder="000.000.000-00" maxLength={14} inputMode="numeric" />
                </div>
              </div>
              <div>
                <label className="label">Endereço</label>
                <textarea value={address} onChange={(e) => setAddress(e.target.value)}
                  className="input min-h-[72px] resize-y" placeholder="Rua, número, bairro, cidade..." rows={2} />
              </div>
              <button type="submit" className="btn btn-primary w-full sm:w-auto" disabled={savingProfile}>
                {savingProfile ? <><Loader className="w-4 h-4 animate-spin" />Salvando...</> : <><Save className="w-4 h-4" />Salvar perfil</>}
              </button>
            </form>
          </div>

          {/* ── CARDS SECTION ── */}
          <div className="card p-6 space-y-4">            <div>
              <h2 className="text-base font-semibold text-[var(--color-text-primary)]">Meus cartões</h2>
              <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
                Configure os cartões que aparecem nas faturas. O tipo determina se a despesa é individual ou dividida.
              </p>
            </div>

            {cardError && (
              <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{cardError}</div>
            )}
            {cardMessage && (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{cardMessage}</div>
            )}

            {/* Card list */}
            <div className="space-y-2">
              {cards.length === 0 && !showCreate && (
                <p className="text-sm text-[var(--color-text-secondary)] py-2">Nenhum cartão cadastrado ainda.</p>
              )}

              {cards.map((card) => (
                <div key={card.id} className="rounded-xl border border-[var(--color-border)] p-4">
                  {editingCardId === card.id ? (
                    <div className="space-y-3">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-mono text-sm font-semibold">•••• {card.last4}</span>
                        <span className="text-xs text-[var(--color-text-muted)]">(não editável)</span>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div>
                          <label className="label">Nome do cartão</label>
                          <input type="text" value={editCardForm.label}
                            onChange={(e) => setEditCardForm({ ...editCardForm, label: e.target.value })}
                            className="input" placeholder="Ex.: Cartão principal" />
                        </div>
                        <div>
                          <label className="label">Responsável</label>
                          <input type="text" value={editCardForm.owner}
                            onChange={(e) => setEditCardForm({ ...editCardForm, owner: e.target.value })}
                            className="input" placeholder={displayName || 'Nome do dono'} />
                        </div>
                      </div>
                      <div>
                        <label className="label">Tipo</label>
                        <TypeToggle value={editCardForm.card_type}
                          onChange={(v) => setEditCardForm({ ...editCardForm, card_type: v })} />
                      </div>
                      <div className="flex gap-2 pt-1">
                        <button onClick={handleSaveCard} disabled={savingCard} className="btn btn-primary">
                          {savingCard ? <Loader className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                          Salvar
                        </button>
                        <button onClick={() => setEditingCardId(null)}
                          className="btn btn-ghost border border-[var(--color-border)]">
                          <X className="w-4 h-4" />Cancelar
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-lg bg-[var(--color-bg-accent)] flex items-center justify-center flex-shrink-0">
                          <CreditCard className="w-4 h-4 text-[var(--color-brand-primary)]" />
                        </div>
                        <div>
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-mono text-sm font-semibold text-[var(--color-text-primary)]">
                              •••• {card.last4}
                            </span>
                            {card.label && (
                              <span className="text-sm text-[var(--color-text-secondary)]">— {card.label}</span>
                            )}
                          </div>
                          <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                            <span className="text-xs text-[var(--color-text-muted)]">{card.owner}</span>
                            <span className="text-[var(--color-text-muted)]">·</span>
                            <span className={clsx(
                              'text-xs font-medium px-1.5 py-0.5 rounded',
                              card.card_type === 'shared' ? 'bg-purple-100 text-purple-700' : 'bg-blue-100 text-blue-700'
                            )}>
                              {card.card_type === 'shared' ? 'Compartilhado' : 'Individual'}
                            </span>
                          </div>
                        </div>
                      </div>
                      <div className="flex gap-1 flex-shrink-0">
                        <button onClick={() => startEditCard(card)}
                          className="p-2 hover:bg-[var(--color-bg-accent)] rounded-lg transition-colors" title="Editar">
                          <Edit2 className="w-4 h-4 text-[var(--color-text-secondary)]" />
                        </button>
                        <button onClick={() => handleDeleteCard(card)}
                          className="p-2 hover:bg-red-50 rounded-lg transition-colors" title="Excluir">
                          <Trash2 className="w-4 h-4 text-red-500" />
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Create form */}
            {showCreate ? (
              <div className="rounded-xl border-2 border-dashed border-[var(--color-brand-primary)] p-4 space-y-3">
                <p className="text-sm font-semibold text-[var(--color-text-primary)]">Novo cartão</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="label">4 dígitos finais <span className="text-red-500">*</span></label>
                    <input type="text" value={createForm.last4}
                      onChange={(e) => setCreateForm({ ...createForm, last4: e.target.value.replace(/\D/g, '').slice(0, 4) })}
                      className="input font-mono" placeholder="1234" maxLength={4} inputMode="numeric" />
                    <p className="mt-1 text-xs text-[var(--color-text-muted)]">Aparece na fatura como "•••• 1234"</p>
                  </div>
                  <div>
                    <label className="label">Nome do cartão</label>
                    <input type="text" value={createForm.label}
                      onChange={(e) => setCreateForm({ ...createForm, label: e.target.value })}
                      className="input" placeholder="Ex.: Cartão principal" />
                  </div>
                  <div>
                    <label className="label">Responsável</label>
                    <input type="text" value={createForm.owner}
                      onChange={(e) => setCreateForm({ ...createForm, owner: e.target.value })}
                      className="input" placeholder={displayName || 'Nome do dono'} />
                  </div>
                  <div>
                    <label className="label">Banco</label>
                    <select value={createForm.bank}
                      onChange={(e) => setCreateForm({ ...createForm, bank: e.target.value })} className="input">
                      <option value="nubank">Nubank</option>
                      <option value="itau">Itaú</option>
                      <option value="bradesco">Bradesco</option>
                      <option value="santander">Santander</option>
                      <option value="inter">Inter</option>
                      <option value="c6">C6 Bank</option>
                      <option value="outro">Outro</option>
                    </select>
                  </div>
                </div>
                <div>
                  <label className="label">Tipo</label>
                  <TypeToggle value={createForm.card_type}
                    onChange={(v) => setCreateForm({ ...createForm, card_type: v })} />
                  <p className="mt-1.5 text-xs text-[var(--color-text-muted)]">
                    <strong>Individual:</strong> conta só para o responsável. <strong>Compartilhado:</strong> entra na divisão do casal/família.
                  </p>
                </div>
                <div className="flex gap-2 pt-1">
                  <button onClick={handleCreateCard} disabled={savingCard} className="btn btn-primary">
                    {savingCard ? <Loader className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                    Cadastrar
                  </button>
                  <button onClick={() => { setShowCreate(false); setCreateForm(emptyCardForm); setCardError(null); }}
                    className="btn btn-ghost border border-[var(--color-border)]">
                    <X className="w-4 h-4" />Cancelar
                  </button>
                </div>
              </div>
            ) : (
              <button onClick={() => { setShowCreate(true); setCardError(null); setCardMessage(null); }}
                className="btn btn-primary w-full sm:w-auto">
                <Plus className="w-4 h-4" />
                Adicionar cartão
              </button>
            )}
          </div>

          </div>{/* end grid */}
        </div>
      )}
    </>
  );
}
