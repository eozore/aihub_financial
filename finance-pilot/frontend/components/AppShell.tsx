'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { LayoutDashboard, FileText, UploadCloud, LogOut, Menu, X, Wallet, Settings2, Crown, PieChart, UserCircle } from 'lucide-react';
import { auth } from '../lib/firebase';
import clsx from 'clsx';
import { activateWorkspace, getMe, getWorkspaces, WorkspaceSummary } from '../services/api';

const NAV_ITEMS = [
    { name: 'Dashboard', icon: LayoutDashboard, href: '/dashboard' },
    { name: 'Transações', icon: FileText, href: '/transactions' },
    { name: 'Patrimônio', icon: PieChart, href: '/patrimonio' },
    { name: 'Importar', icon: UploadCloud, href: '/upload' },
    { name: 'Painel', icon: Settings2, href: '/workspace' },
];

interface AppShellProps {
    children: React.ReactNode;
}

export default function AppShell({ children }: AppShellProps) {
    const pathname = usePathname();
    const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
    const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([]);
    const [activeWorkspaceId, setActiveWorkspaceId] = useState<string>('');
    const [planType, setPlanType] = useState<'free' | 'paid'>('free');
    const [switchingWorkspace, setSwitchingWorkspace] = useState(false);
    const planBadgeLabel = planType === 'paid' ? 'Premium' : 'Free';
    const planBadgeClass =
        planType === 'paid'
            ? 'bg-emerald-100 text-emerald-700'
            : 'bg-slate-100 text-slate-700';

    useEffect(() => {
        let mounted = true;
        const loadWorkspaceData = async () => {
            try {
                const [me, workspacePayload] = await Promise.all([getMe(), getWorkspaces()]);
                if (!mounted) return;
                setPlanType(me.plan_type);
                setWorkspaces(workspacePayload.workspaces || []);
                setActiveWorkspaceId(workspacePayload.active_workspace_id || me.active_workspace_id || '');
            } catch (error) {
                console.error('Failed to load workspace data', error);
            }
        };
        loadWorkspaceData();
        return () => {
            mounted = false;
        };
    }, []);

    const handleWorkspaceChange = async (workspaceId: string) => {
        if (!workspaceId || workspaceId === activeWorkspaceId) return;
        setSwitchingWorkspace(true);
        try {
            await activateWorkspace(workspaceId);
            setActiveWorkspaceId(workspaceId);
            window.location.reload();
        } catch (error) {
            console.error('Failed to switch workspace', error);
        } finally {
            setSwitchingWorkspace(false);
        }
    };

    return (
        <div className="min-h-screen bg-[var(--color-bg-primary)]">
            {/* === MOBILE TOP BAR === */}
            <header className="md:hidden fixed top-0 left-0 right-0 h-16 bg-white border-b border-[var(--color-border)] z-50 px-4 flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <div className="w-8 h-8 bg-[var(--color-brand-primary)] rounded-lg flex items-center justify-center">
                        <Wallet className="text-white w-4 h-4" />
                    </div>
                    <span className={clsx(
                        "inline-flex items-center rounded-full px-2.5 py-1 text-[10px] font-semibold",
                        planBadgeClass
                    )}>
                        {planBadgeLabel}
                    </span>
                </div>
                <button
                    onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                    className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                >
                    {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
                </button>
            </header>

            {/* === MOBILE MENU OVERLAY === */}
            {mobileMenuOpen && (
                <div className="md:hidden fixed inset-0 z-40">
                    <div
                        className="absolute inset-0 bg-black/20"
                        onClick={() => setMobileMenuOpen(false)}
                    />
                    <nav className="absolute top-16 left-0 right-0 bg-white border-b border-[var(--color-border)] py-2 animate-fade-in">
                        <div className="px-6 py-3 border-b border-[var(--color-border)]">
                            <p className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">
                                Painel Ativo ({planType === 'paid' ? 'Pago' : 'Free'})
                            </p>
                            <select
                                value={activeWorkspaceId}
                                onChange={(e) => handleWorkspaceChange(e.target.value)}
                                disabled={switchingWorkspace}
                                className="w-full rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm"
                            >
                                {workspaces.map((workspace) => (
                                    <option key={workspace.id} value={workspace.id}>
                                        {workspace.name}
                                    </option>
                                ))}
                            </select>
                        </div>
                        {NAV_ITEMS.map((item) => (
                            <Link
                                key={item.href}
                                href={item.href}
                                onClick={() => setMobileMenuOpen(false)}
                                className={clsx(
                                    "flex items-center gap-3 px-6 py-3 text-sm font-medium transition-colors",
                                    pathname === item.href
                                        ? "text-[var(--color-brand-primary)] bg-[var(--color-bg-accent)]"
                                        : "text-[var(--color-text-secondary)] hover:bg-gray-50"
                                )}
                            >
                                <item.icon className="w-5 h-5" />
                                {item.name}
                            </Link>
                        ))}
                        <button
                            onClick={() => auth.signOut()}
                            className="w-full flex items-center gap-3 px-6 py-3 text-sm font-medium text-red-500 hover:bg-red-50 transition-colors"
                        >
                            <LogOut className="w-5 h-5" />
                            Sair
                        </button>
                        <Link
                            href="/profile"
                            onClick={() => setMobileMenuOpen(false)}
                            className={clsx(
                                "flex items-center gap-3 px-6 py-3 text-sm font-medium transition-colors",
                                pathname === '/profile'
                                    ? "text-[var(--color-brand-primary)] bg-[var(--color-bg-accent)]"
                                    : "text-[var(--color-text-secondary)] hover:bg-gray-50"
                            )}
                        >
                            <UserCircle className="w-5 h-5" />
                            Meu Perfil
                        </Link>
                    </nav>
                </div>
            )}

            {/* === DESKTOP SIDEBAR === */}
            <aside className="hidden md:flex flex-col fixed left-0 top-0 h-screen w-60 bg-white border-r border-[var(--color-border)] z-50">
                {/* Logo */}
                <div className="h-16 px-6 flex items-center gap-3 border-b border-[var(--color-border)]">
                    <div className="w-9 h-9 flex items-center justify-center rounded-full overflow-hidden">
                        <img src="/logo.png" alt="Logo" className="w-full h-full object-cover" />
                    </div>
                    <span className={clsx(
                        "ml-auto inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[10px] font-semibold",
                        planBadgeClass
                    )}>
                        {planType === 'paid' ? <Crown className="w-3 h-3" /> : null}
                        {planBadgeLabel}
                    </span>
                </div>

                {/* Navigation */}
                <nav className="flex-1 py-6 px-3">
                    <div className="px-3 mb-5">
                        <p className="text-[10px] font-semibold text-[var(--color-text-muted)] uppercase tracking-wider mb-1">
                            Painel Ativo ({planType === 'paid' ? 'Pago' : 'Free'})
                        </p>
                        <select
                            value={activeWorkspaceId}
                            onChange={(e) => handleWorkspaceChange(e.target.value)}
                            disabled={switchingWorkspace}
                            className="w-full rounded-lg border border-[var(--color-border)] bg-white px-3 py-2 text-sm text-[var(--color-text-primary)]"
                        >
                            {workspaces.map((workspace) => (
                                <option key={workspace.id} value={workspace.id}>
                                    {workspace.name}
                                </option>
                            ))}
                        </select>
                        {planType === 'free' && (
                            <Link
                                href="/workspace"
                                className="mt-2 w-full inline-flex items-center justify-center gap-1 rounded-lg border border-[var(--color-border)] bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-700 hover:bg-amber-100"
                            >
                                <Crown className="w-3.5 h-3.5" />
                                Assinar Premium
                            </Link>
                        )}
                    </div>
                    <p className="px-3 text-[10px] font-semibold text-[var(--color-text-muted)] uppercase tracking-wider mb-3">
                        Menu
                    </p>
                    {NAV_ITEMS.map((item) => {
                        const isActive = pathname === item.href;
                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                className={clsx(
                                    "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all mb-1",
                                    isActive
                                        ? "bg-[var(--color-bg-accent)] text-[var(--color-brand-primary)]"
                                        : "text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-accent)] hover:text-[var(--color-text-primary)]"
                                )}
                            >
                                <item.icon className={clsx("w-5 h-5", isActive && "text-[var(--color-brand-primary)]")} />
                                {item.name}
                            </Link>
                        );
                    })}
                </nav>

                {/* Footer */}
                <div className="p-3 border-t border-[var(--color-border)] space-y-3">
                    <Link
                        href="/profile"
                        className={clsx(
                            "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all",
                            pathname === '/profile'
                                ? "bg-[var(--color-bg-accent)] text-[var(--color-brand-primary)]"
                                : "text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-accent)] hover:text-[var(--color-text-primary)]"
                        )}
                    >
                        <UserCircle className={clsx("w-5 h-5", pathname === '/profile' && "text-[var(--color-brand-primary)]")} />
                        Meu Perfil
                    </Link>
                    <button
                        onClick={() => auth.signOut()}
                        className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-[var(--color-text-secondary)] hover:bg-red-50 hover:text-red-500 transition-colors"
                    >
                        <LogOut className="w-5 h-5" />
                        Sair
                    </button>

                    <a
                        href="https://victorzoredev.github.io/zore-portfolio/"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block text-[10px] text-center text-[var(--color-text-muted)] hover:text-[var(--color-brand-primary)] transition-colors pt-2 border-t border-[var(--color-border)]"
                    >
                        Powered by <strong>Victor Zoré</strong>
                    </a>
                </div>
            </aside>

            {/* === MAIN CONTENT === */}
            <main className="md:ml-60 pt-16 md:pt-0 min-h-screen">
                <div className="p-6 md:p-8 max-w-7xl mx-auto">
                    {children}
                </div>
            </main>
        </div>
    );
}
