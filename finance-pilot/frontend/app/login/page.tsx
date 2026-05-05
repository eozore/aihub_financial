'use client';
import { useState } from 'react';
import { signInWithPopup, GoogleAuthProvider } from 'firebase/auth';
import { auth } from '../../lib/firebase';
import { useRouter } from 'next/navigation';
import { Loader } from 'lucide-react';

export default function LoginPage() {
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const router = useRouter();

    const handleGoogleLogin = async () => {
        setLoading(true);
        setError('');

        try {
            const provider = new GoogleAuthProvider();
            await signInWithPopup(auth, provider);
            router.push('/dashboard');
        } catch (err: any) {
            console.error(err);
            if (err.code === 'auth/popup-closed-by-user') {
                setError('');
            } else if (err.code === 'auth/unauthorized-domain') {
                setError('Domínio não autorizado no Firebase.');
            } else {
                setError('Erro ao fazer login. Tente novamente.');
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center p-6 bg-[var(--color-bg-primary)]">
            {/* Login Card */}
            <div className="w-full max-w-sm animate-fade-in">
                <div className="card p-8 text-center bg-white shadow-xl rounded-2xl border-none">
                    {/* Logo */}
                    <div className="w-20 h-20 mx-auto mb-6 rounded-full overflow-hidden flex items-center justify-center bg-white shadow-sm ring-1 ring-gray-100">
                        <img src="/logo.png" alt="Logo" className="w-full h-full object-cover" />
                    </div>

                    <h1 className="text-2xl font-bold text-[var(--color-text-primary)] mb-1">
                        AI Finance
                    </h1>
                    <p className="text-[var(--color-text-secondary)] text-sm mb-8">
                        Controle financeiro inteligente
                    </p>

                    {/* Error */}
                    {error && (
                        <div className="bg-red-50 text-red-600 text-sm p-3 rounded-lg mb-6 border border-red-100">
                            {error}
                        </div>
                    )}

                    {/* Google Button */}
                    <button
                        onClick={handleGoogleLogin}
                        disabled={loading}
                        className="w-full h-12 bg-white border border-[var(--color-border)] hover:border-[var(--color-text-secondary)] hover:shadow-md text-[var(--color-text-primary)] font-medium rounded-xl transition-all flex items-center justify-center gap-3 disabled:opacity-60 disabled:cursor-not-allowed"
                    >
                        {loading ? (
                            <Loader className="w-5 h-5 animate-spin text-[var(--color-brand-primary)]" />
                        ) : (
                            <svg className="w-5 h-5" viewBox="0 0 24 24">
                                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
                            </svg>
                        )}
                        <span>{loading ? 'Entrando...' : 'Continuar com Google'}</span>
                    </button>

                    <p className="text-xs text-[var(--color-text-muted)] mt-6">
                        Acesso restrito.
                    </p>
                </div>

                <div className="text-center mt-8">
                    <a
                        href="https://victorzoredev.github.io/zore-portfolio/"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-block text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-brand-primary)] transition-colors"
                    >
                        Powered by <strong>Victor Zoré</strong>
                    </a>
                </div>
            </div>
        </div>
    );
}
