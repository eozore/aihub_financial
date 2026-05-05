'use client';

import { FormEvent, useEffect, useState } from 'react';
import { Loader, Save, User } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { getMe, updateMyProfile } from '@/services/api';

function formatCpf(value: string): string {
  // Strip non-digits and apply mask: 000.000.000-00
  const digits = value.replace(/\D/g, '').slice(0, 11);
  if (digits.length <= 3) return digits;
  if (digits.length <= 6) return `${digits.slice(0, 3)}.${digits.slice(3)}`;
  if (digits.length <= 9) return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6)}`;
  return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6, 9)}-${digits.slice(9)}`;
}

export default function ProfilePage() {
  const { user } = useAuth();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [displayName, setDisplayName] = useState('');
  const [shortName, setShortName] = useState('');
  const [photoUrl, setPhotoUrl] = useState('');
  const [birthDate, setBirthDate] = useState('');
  const [cpf, setCpf] = useState('');
  const [address, setAddress] = useState('');

  useEffect(() => {
    if (!user) return;
    let mounted = true;
    const load = async () => {
      setLoading(true);
      try {
        const me = await getMe();
        if (!mounted) return;
        setDisplayName(me.display_name || '');
        setShortName(me.short_name || '');
        setPhotoUrl(me.photo_url || '');
      } catch (err: any) {
        if (mounted) setError(err?.response?.data?.detail || 'Erro ao carregar perfil.');
      } finally {
        if (mounted) setLoading(false);
      }
    };
    load();
    return () => { mounted = false; };
  }, [user]);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!displayName.trim()) {
      setError('Nome de exibição é obrigatório.');
      return;
    }

    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      await updateMyProfile({
        display_name: displayName.trim(),
        short_name: shortName.trim() || undefined,
        photo_url: photoUrl.trim() || undefined,
        birth_date: birthDate || undefined,
        cpf: cpf.replace(/\D/g, '') || undefined,
        address: address.trim() || undefined,
      });
      setMessage('Perfil atualizado com sucesso.');
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Erro ao salvar perfil.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Meu Perfil</h1>
        <p className="page-subtitle">Gerencie suas informações pessoais</p>
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <Loader className="w-8 h-8 animate-spin text-[var(--color-brand-primary)]" />
        </div>
      ) : (
        <div className="max-w-xl animate-fade-in">
          {error && (
            <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}
          {message && (
            <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
              {message}
            </div>
          )}

          <div className="card p-6 space-y-6">
            {/* Avatar preview */}
            <div className="flex items-center gap-4">
              <div className="w-16 h-16 rounded-full bg-[var(--color-bg-accent)] border border-[var(--color-border)] flex items-center justify-center overflow-hidden flex-shrink-0">
                {photoUrl ? (
                  <img
                    src={photoUrl}
                    alt="Foto de perfil"
                    className="w-full h-full object-cover"
                    onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                  />
                ) : (
                  <User className="w-8 h-8 text-[var(--color-text-muted)]" />
                )}
              </div>
              <div>
                <p className="text-sm font-medium text-[var(--color-text-primary)]">
                  {displayName || 'Sem nome'}
                </p>
                <p className="text-xs text-[var(--color-text-muted)]">{user?.email}</p>
              </div>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Email — read-only */}
              <div>
                <label className="label">E-mail</label>
                <input
                  type="email"
                  value={user?.email || ''}
                  readOnly
                  className="input bg-[var(--color-bg-accent)] cursor-not-allowed text-[var(--color-text-muted)]"
                />
              </div>

              {/* Display name — required */}
              <div>
                <label className="label">
                  Nome de exibição <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  className="input"
                  placeholder="Ex.: Victor Zoré"
                  required
                />
                <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                  Aparece nas transações e no painel compartilhado.
                </p>
              </div>

              {/* Short name — optional */}
              <div>
                <label className="label">Nome curto</label>
                <input
                  type="text"
                  value={shortName}
                  onChange={(e) => setShortName(e.target.value)}
                  className="input"
                  placeholder="Ex.: Victor"
                />
                <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                  Usado em espaços reduzidos (gráficos, filtros).
                </p>
              </div>

              {/* Photo URL — optional */}
              <div>
                <label className="label">URL da foto de perfil</label>
                <input
                  type="url"
                  value={photoUrl}
                  onChange={(e) => setPhotoUrl(e.target.value)}
                  className="input"
                  placeholder="https://exemplo.com/foto.jpg"
                />
              </div>

              {/* Birth date — optional */}
              <div>
                <label className="label">Data de nascimento</label>
                <input
                  type="date"
                  value={birthDate}
                  onChange={(e) => setBirthDate(e.target.value)}
                  className="input"
                />
              </div>

              {/* CPF — optional, with mask */}
              <div>
                <label className="label">CPF</label>
                <input
                  type="text"
                  value={cpf}
                  onChange={(e) => setCpf(formatCpf(e.target.value))}
                  className="input"
                  placeholder="000.000.000-00"
                  maxLength={14}
                  inputMode="numeric"
                />
              </div>

              {/* Address — optional */}
              <div>
                <label className="label">Endereço</label>
                <textarea
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  className="input min-h-[80px] resize-y"
                  placeholder="Rua, número, bairro, cidade..."
                  rows={3}
                />
              </div>

              <div className="pt-2">
                <button
                  type="submit"
                  className="btn btn-primary w-full sm:w-auto"
                  disabled={saving}
                >
                  {saving ? (
                    <>
                      <Loader className="w-4 h-4 animate-spin" />
                      Salvando...
                    </>
                  ) : (
                    <>
                      <Save className="w-4 h-4" />
                      Salvar perfil
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
