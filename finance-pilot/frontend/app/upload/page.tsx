'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '../../context/AuthContext';
import AppShell from '../../components/AppShell';
import UploadForm from '../../components/UploadForm';

export default function UploadPage() {
    const { user, loading } = useAuth();
    const router = useRouter();

    useEffect(() => {
        if (!loading && !user) router.push('/login');
    }, [user, loading, router]);

    if (loading || !user) return null;

    return (
        <AppShell>
            {/* Header */}
            <div className="page-header mb-8">
                <h1 className="page-title">Importar Arquivos</h1>
                <p className="page-subtitle">Cartão, patrimônio e outros (em breve)</p>
            </div>

            <div className="max-w-xl mx-auto">
                <UploadForm />
            </div>
        </AppShell>
    );
}
