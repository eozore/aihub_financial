'use client';

import { FormEvent, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Crown, Loader, MailPlus, Plus, RefreshCw, Save, Trash2, UserMinus, Users, WalletCards, X } from 'lucide-react';
import AppShell from '@/components/AppShell';
import { useAuth } from '@/context/AuthContext';
import {
  acceptInvite,
  createWorkspace,
  createWorkspaceInvite,
  deleteWorkspace,
  getInvites,
  getMe,
  getWorkspaceMembers,
  getWorkspaces,
  removeWorkspaceMember,
  updatePlan,
  updateWorkspace,
  WorkspaceSummary,
} from '@/services/api';

interface WorkspaceMember {
  user_id: string;
  email?: string;
  role: string;
}

interface InviteRecord {
  id: string;
  invitee_email: string;
  invite_mode: 'shared' | 'isolated';
  status: string;
  created_at?: string;
  workspace_id?: string;
  target_workspace_name?: string;
}

export default function WorkspacePage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  const [loadingPage, setLoadingPage] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [planType, setPlanType] = useState<'free' | 'paid'>('free');
  const [workspaceLimit, setWorkspaceLimit] = useState(1);
  const [memberLimit, setMemberLimit] = useState(1);

  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([]);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState('');
  const [workspaceName, setWorkspaceName] = useState('');
  const [newWorkspaceName, setNewWorkspaceName] = useState('');

  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [inviteEmail, setInviteEmail] = useState('');
  const [receivedInvites, setReceivedInvites] = useState<InviteRecord[]>([]);
  const [sentInvites, setSentInvites] = useState<InviteRecord[]>([]);

  const [showSubscribeModal, setShowSubscribeModal] = useState(false);
  const [confirmingSubscribe, setConfirmingSubscribe] = useState(false);

  const activeWorkspace = useMemo(
    () => workspaces.find((workspace) => workspace.id === activeWorkspaceId),
    [workspaces, activeWorkspaceId]
  );
  const isWorkspaceOwner = activeWorkspace?.role === 'owner';

  useEffect(() => {
    if (!loading && !user) {
      router.push('/login');
    }
  }, [loading, router, user]);

  const loadWorkspaceData = async () => {
    const [me, workspacePayload, invitePayload] = await Promise.all([getMe(), getWorkspaces(), getInvites()]);
    const nextWorkspaces: WorkspaceSummary[] = workspacePayload.workspaces || [];
    const nextActiveWorkspaceId =
      workspacePayload.active_workspace_id ||
      me.active_workspace_id ||
      nextWorkspaces[0]?.id ||
      '';

    setPlanType(me.plan_type);
    setWorkspaceLimit(me.limits.max_workspaces);
    setMemberLimit(me.limits.max_members_per_workspace);
    setWorkspaces(nextWorkspaces);
    setActiveWorkspaceId(nextActiveWorkspaceId);
    setWorkspaceName(nextWorkspaces.find((workspace) => workspace.id === nextActiveWorkspaceId)?.name || '');
    setReceivedInvites((invitePayload.received || []) as InviteRecord[]);
    setSentInvites((invitePayload.sent || []) as InviteRecord[]);

    if (nextActiveWorkspaceId) {
      const memberPayload = await getWorkspaceMembers(nextActiveWorkspaceId);
      setMembers((memberPayload.members || []) as WorkspaceMember[]);
    } else {
      setMembers([]);
    }
  };

  useEffect(() => {
    if (!user) return;

    let mounted = true;
    const load = async () => {
      setLoadingPage(true);
      setError(null);
      try {
        await loadWorkspaceData();
      } catch (loadError: any) {
        if (!mounted) return;
        setError(loadError?.response?.data?.detail || 'Erro ao carregar dados do painel.');
      } finally {
        if (mounted) {
          setLoadingPage(false);
        }
      }
    };

    load();
    return () => {
      mounted = false;
    };
  }, [user]);

  const refreshAll = async () => {
    setRefreshing(true);
    setError(null);
    setMessage(null);
    try {
      await loadWorkspaceData();
    } catch (refreshError: any) {
      setError(refreshError?.response?.data?.detail || 'Erro ao atualizar dados.');
    } finally {
      setRefreshing(false);
    }
  };

  const handleRenameWorkspace = async (event: FormEvent) => {
    event.preventDefault();
    if (!activeWorkspace || !workspaceName.trim()) return;

    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      await updateWorkspace(activeWorkspace.id, workspaceName.trim());
      setMessage('Nome do painel atualizado.');
      await refreshAll();
    } catch (renameError: any) {
      setError(renameError?.response?.data?.detail || 'Erro ao atualizar nome do painel.');
    } finally {
      setSaving(false);
    }
  };

  const handleCreateWorkspace = async (event: FormEvent) => {
    event.preventDefault();
    if (!newWorkspaceName.trim()) return;

    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      await createWorkspace(newWorkspaceName.trim());
      setNewWorkspaceName('');
      setMessage('Novo painel criado com sucesso.');
      await refreshAll();
    } catch (createError: any) {
      setError(createError?.response?.data?.detail || 'Erro ao criar painel.');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteWorkspace = async () => {
    if (!activeWorkspace) return;
    const confirmed = window.confirm(
      `Deseja excluir o painel "${activeWorkspace.name}"? Apenas painéis sem transações e sem outros membros podem ser excluídos.`
    );
    if (!confirmed) return;

    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      await deleteWorkspace(activeWorkspace.id);
      setMessage('Painel excluído.');
      await refreshAll();
    } catch (deleteError: any) {
      setError(deleteError?.response?.data?.detail || 'Erro ao excluir painel.');
    } finally {
      setSaving(false);
    }
  };

  const handleInvite = async (event: FormEvent) => {
    event.preventDefault();
    if (!activeWorkspace) return;
    if (!inviteEmail.trim()) return;

    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      await createWorkspaceInvite(activeWorkspace.id, inviteEmail.trim());
      setInviteEmail('');
      setMessage('Convite enviado.');
      await refreshAll();
    } catch (inviteError: any) {
      setError(inviteError?.response?.data?.detail || 'Erro ao enviar convite.');
    } finally {
      setSaving(false);
    }
  };

  const handleRemoveMember = async (member: WorkspaceMember) => {
    if (!activeWorkspace) return;
    const confirmed = window.confirm(`Remover ${member.email || member.user_id} deste painel?`);
    if (!confirmed) return;

    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      await removeWorkspaceMember(activeWorkspace.id, member.user_id);
      setMessage('Membro removido.');
      await refreshAll();
    } catch (removeError: any) {
      setError(removeError?.response?.data?.detail || 'Erro ao remover membro.');
    } finally {
      setSaving(false);
    }
  };

  const handleAcceptInvite = async (inviteId: string) => {
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      await acceptInvite(inviteId);
      setMessage('Convite aceito.');
      await refreshAll();
    } catch (acceptError: any) {
      setError(acceptError?.response?.data?.detail || 'Erro ao aceitar convite.');
    } finally {
      setSaving(false);
    }
  };

  const handleConfirmPremium = async () => {
    if (planType === 'paid') {
      setShowSubscribeModal(false);
      return;
    }

    setConfirmingSubscribe(true);
    setError(null);
    setMessage(null);
    try {
      await updatePlan('paid');
      setShowSubscribeModal(false);
      setMessage('Assinatura premium ativada com sucesso.');
      await refreshAll();
    } catch (planError: any) {
      setError(planError?.response?.data?.detail || 'Erro ao ativar assinatura premium.');
    } finally {
      setConfirmingSubscribe(false);
    }
  };

  if (loading || !user) return null;

  return (
    <AppShell>
      <div className="page-header">
        <h1 className="page-title">Gestão do Painel</h1>
        <p className="page-subtitle">Assinatura, configuração de painel e membros</p>
      </div>

      {loadingPage ? (
        <div className="flex justify-center py-16">
          <Loader className="w-8 h-8 animate-spin text-[var(--color-brand-primary)]" />
        </div>
      ) : (
        <div className="space-y-5 animate-fade-in">
          {error && (
            <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
          )}
          {message && (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</div>
          )}

          <div className="card p-5">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <p className="text-xs uppercase tracking-wider text-[var(--color-text-muted)]">Assinatura</p>
                <h2 className="mt-1 text-xl font-semibold text-[var(--color-text-primary)]">
                  {planType === 'paid' ? 'Premium' : 'Free'}
                </h2>
                <p className="text-sm text-[var(--color-text-secondary)]">
                  Limites: {workspaceLimit} painéis e até {memberLimit} pessoa(s) por painel
                </p>
              </div>
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
                <span className="inline-flex items-center justify-center rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700">
                  {planType === 'paid' ? 'Premium ativo' : 'Plano Free ativo'}
                </span>
                <button
                  type="button"
                  onClick={() => setShowSubscribeModal(true)}
                  className="btn btn-primary w-full sm:w-auto"
                >
                  <WalletCards className="w-4 h-4" />
                  {planType === 'paid' ? 'Gerenciar assinatura' : 'Assinar Premium'}
                </button>
                <button type="button" onClick={refreshAll} className="btn btn-ghost w-full sm:w-auto" disabled={refreshing}>
                  <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
                  Atualizar
                </button>
              </div>
            </div>
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <div className="card p-5 space-y-4">
              <h3 className="text-base font-semibold text-[var(--color-text-primary)]">Painel ativo</h3>
              {!activeWorkspace ? (
                <p className="text-sm text-[var(--color-text-secondary)]">Nenhum painel encontrado.</p>
              ) : (
                <>
                  <form onSubmit={handleRenameWorkspace} className="space-y-3">
                    <label className="label">Nome do painel</label>
                    <div className="flex flex-col sm:flex-row gap-2">
                      <input
                        value={workspaceName}
                        onChange={(event) => setWorkspaceName(event.target.value)}
                        className="input sm:flex-1"
                        placeholder="Nome do painel"
                      />
                      <button type="submit" className="btn btn-primary w-full sm:w-auto" disabled={!isWorkspaceOwner || saving}>
                        <Save className="w-4 h-4" />
                        Salvar
                      </button>
                    </div>
                  </form>

                  <div className="rounded-lg bg-[var(--color-bg-accent)] px-3 py-2 text-xs text-[var(--color-text-secondary)]">
                    ID: {activeWorkspace.id}
                  </div>

                  <div className="flex flex-col sm:flex-row gap-2">
                    <button
                      type="button"
                      onClick={handleDeleteWorkspace}
                      className="btn btn-ghost border border-red-200 text-red-600 hover:bg-red-50 w-full sm:w-auto"
                      disabled={!isWorkspaceOwner || saving}
                    >
                      <Trash2 className="w-4 h-4" />
                      Excluir painel
                    </button>
                  </div>
                </>
              )}
            </div>

            <div className="card p-5 space-y-4">
              <h3 className="text-base font-semibold text-[var(--color-text-primary)]">Criar novo painel</h3>
              <form onSubmit={handleCreateWorkspace} className="space-y-3">
                <label className="label">Nome do novo painel</label>
                <div className="flex flex-col sm:flex-row gap-2">
                  <input
                    value={newWorkspaceName}
                    onChange={(event) => setNewWorkspaceName(event.target.value)}
                    className="input sm:flex-1"
                    placeholder="Ex.: Casa, Viagens, Projeto..."
                  />
                  <button type="submit" className="btn btn-primary w-full sm:w-auto" disabled={saving}>
                    <Plus className="w-4 h-4" />
                    Criar
                  </button>
                </div>
              </form>
              <p className="text-xs text-[var(--color-text-muted)]">
                Você está usando {workspaces.length}/{workspaceLimit} painéis.
              </p>
            </div>
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <div className="card p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-semibold text-[var(--color-text-primary)]">Membros</h3>
                <span className="inline-flex items-center gap-1 text-xs text-[var(--color-text-secondary)]">
                  <Users className="w-3.5 h-3.5" />
                  {members.length}/{activeWorkspace?.member_limit || memberLimit}
                </span>
              </div>
              <div className="space-y-2">
                {members.map((member) => (
                  <div
                    key={member.user_id}
                    className="flex items-center justify-between rounded-lg border border-[var(--color-border)] px-3 py-2"
                  >
                    <div>
                      <p className="text-sm font-medium text-[var(--color-text-primary)]">{member.email || member.user_id}</p>
                      <p className="text-xs text-[var(--color-text-muted)]">{member.role}</p>
                    </div>
                    {isWorkspaceOwner && member.role !== 'owner' && (
                      <button
                        type="button"
                        onClick={() => handleRemoveMember(member)}
                        className="btn btn-ghost border border-red-200 px-3 py-2 text-xs text-red-600 hover:bg-red-50"
                        disabled={saving}
                      >
                        <UserMinus className="w-3.5 h-3.5" />
                        Remover
                      </button>
                    )}
                  </div>
                ))}
                {members.length === 0 && (
                  <p className="text-sm text-[var(--color-text-secondary)]">Sem membros neste painel.</p>
                )}
              </div>
            </div>

            <div className="card p-5 space-y-4">
              <h3 className="text-base font-semibold text-[var(--color-text-primary)]">Convidar pessoa</h3>
              <form onSubmit={handleInvite} className="space-y-3">
                <div>
                  <label className="label">E-mail</label>
                  <input
                    className="input"
                    type="email"
                    placeholder="email@dominio.com"
                    value={inviteEmail}
                    onChange={(event) => setInviteEmail(event.target.value)}
                  />
                </div>
                <p className="text-xs text-[var(--color-text-muted)]">
                  O convite adiciona essa pessoa ao painel ativo.
                </p>

                <button type="submit" className="btn btn-primary w-full sm:w-auto" disabled={!isWorkspaceOwner || saving}>
                  <MailPlus className="w-4 h-4" />
                  Enviar convite
                </button>
              </form>
            </div>
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <div className="card p-5 space-y-3">
              <h3 className="text-base font-semibold text-[var(--color-text-primary)]">Convites recebidos</h3>
              {receivedInvites.length === 0 ? (
                <p className="text-sm text-[var(--color-text-secondary)]">Nenhum convite pendente.</p>
              ) : (
                receivedInvites.map((invite) => (
                  <div key={invite.id} className="rounded-lg border border-[var(--color-border)] p-3">
                    <p className="text-sm text-[var(--color-text-primary)]">{invite.invitee_email}</p>
                    <p className="text-xs text-[var(--color-text-secondary)]">
                      Modo: {invite.invite_mode === 'shared' ? 'Compartilhado' : 'Isolado'}
                    </p>
                    <button
                      type="button"
                      className="btn btn-primary mt-2"
                      onClick={() => handleAcceptInvite(invite.id)}
                      disabled={saving}
                    >
                      Aceitar convite
                    </button>
                  </div>
                ))
              )}
            </div>

            <div className="card p-5 space-y-3">
              <h3 className="text-base font-semibold text-[var(--color-text-primary)]">Convites enviados</h3>
              {sentInvites.length === 0 ? (
                <p className="text-sm text-[var(--color-text-secondary)]">Nenhum convite enviado.</p>
              ) : (
                sentInvites.slice(0, 8).map((invite) => (
                  <div key={invite.id} className="rounded-lg border border-[var(--color-border)] p-3">
                    <p className="text-sm text-[var(--color-text-primary)]">{invite.invitee_email}</p>
                    <p className="text-xs text-[var(--color-text-secondary)]">
                      Status: {invite.status} | Modo: {invite.invite_mode === 'shared' ? 'Compartilhado' : 'Isolado (legado)'}
                    </p>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {showSubscribeModal && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl">
            <div className="mb-3 flex items-start justify-between">
              <div>
                <h3 className="text-xl font-semibold text-[var(--color-text-primary)]">Gestão de assinatura</h3>
                <p className="text-sm text-[var(--color-text-secondary)]">
                  Plano atual: {planType === 'paid' ? 'Premium' : 'Free'}
                </p>
              </div>
              <button type="button" onClick={() => setShowSubscribeModal(false)} className="rounded-lg p-2 hover:bg-gray-100">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-accent)] p-4 text-sm text-[var(--color-text-secondary)]">
              <p className="font-semibold text-[var(--color-text-primary)]">Pagamento (placeholder)</p>
              <ul className="mt-2 space-y-1">
                <li>Cartão de crédito (em breve)</li>
                <li>PIX (em breve)</li>
                <li>Boleto (em breve)</li>
              </ul>
            </div>

            {planType === 'free' ? (
              <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-700">
                <p className="font-semibold text-emerald-800">Ao assinar o Premium você terá:</p>
                <ul className="mt-2 space-y-1">
                  <li>Até 3 painéis por conta</li>
                  <li>Até 2 pessoas por painel</li>
                  <li>Gestão completa de membros</li>
                </ul>
              </div>
            ) : (
              <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
                <p className="font-semibold text-slate-800">Assinatura ativa.</p>
                <p className="mt-1">Troca de plano e gestão de cobrança serão liberadas nesta tela.</p>
              </div>
            )}

            <div className="mt-5 flex flex-col-reverse sm:flex-row justify-end gap-2">
              <button type="button" className="btn btn-ghost w-full sm:w-auto" onClick={() => setShowSubscribeModal(false)}>
                Cancelar
              </button>
              {planType === 'free' && (
                <button type="button" className="btn btn-primary w-full sm:w-auto" onClick={handleConfirmPremium} disabled={confirmingSubscribe}>
                  {confirmingSubscribe ? (
                    <>
                      <Loader className="w-4 h-4 animate-spin" />
                      Processando...
                    </>
                  ) : (
                    <>
                      <Crown className="w-4 h-4" />
                      Confirmar assinatura
                    </>
                  )}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
