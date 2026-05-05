'use client';

import UploadForm from '../../../components/UploadForm';

export default function UploadPage() {
    return (
        <>
            {/* Header */}
            <div className="page-header mb-8">
                <h1 className="page-title">Importar Arquivos</h1>
                <p className="page-subtitle">Cartão, patrimônio e outros (em breve)</p>
            </div>

            <div className="max-w-xl mx-auto">
                <UploadForm />
            </div>
        </>
    );
}
