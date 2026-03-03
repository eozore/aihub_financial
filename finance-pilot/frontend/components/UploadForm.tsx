'use client';

import { useState, useRef } from 'react';
import { uploadCurrentAccount, uploadInvoice, uploadNetWorth } from '../services/api';
import { UploadCloud, FileText, Check, Loader, X } from 'lucide-react';
import clsx from 'clsx';

const OWNERS = ['Victor', 'Larissa'];
type UploadType = 'invoice_nubank' | 'net_worth_monthly' | 'current_account';

export default function UploadForm() {
    const [file, setFile] = useState<File | null>(null);
    const [uploadType, setUploadType] = useState<UploadType>('invoice_nubank');
    const [owner, setOwner] = useState<string>('Victor');
    const [monthRef, setMonthRef] = useState(new Date().toISOString().slice(0, 7));
    const [status, setStatus] = useState<'idle' | 'uploading' | 'success' | 'error'>('idle');
    const [message, setMessage] = useState('');
    const [isDragOver, setIsDragOver] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragOver(false);
        const droppedFile = e.dataTransfer.files[0];
        if (droppedFile && droppedFile.name.endsWith('.csv')) {
            setFile(droppedFile);
            setStatus('idle');
        }
    };

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const selectedFile = e.target.files?.[0];
        if (selectedFile) {
            setFile(selectedFile);
            setStatus('idle');
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!file) return;

        setStatus('uploading');
        setMessage('');

        try {
            if (uploadType === 'invoice_nubank') {
                await uploadInvoice(file, owner, monthRef);
            } else if (uploadType === 'current_account') {
                await uploadCurrentAccount(file, owner, monthRef);
            } else {
                await uploadNetWorth(file, owner);
            }
            setStatus('success');
            setMessage('Arquivo processado com sucesso!');
            setFile(null);
        } catch (error: any) {
            setStatus('error');
            setMessage(error.response?.data?.detail || 'Erro ao enviar arquivo.');
        }
    };

    const clearFile = () => {
        setFile(null);
        setStatus('idle');
        if (fileInputRef.current) {
            fileInputRef.current.value = '';
        }
    };

    return (
        <form onSubmit={handleSubmit} className="space-y-6">
            {/* Upload Type */}
            <div className="card p-5">
                <label className="label">Tipo de arquivo</label>
                <select
                    value={uploadType}
                    onChange={(e) => {
                        setUploadType(e.target.value as UploadType);
                        setStatus('idle');
                        setMessage('');
                    }}
                    className="input"
                >
                    <option value="invoice_nubank">Fatura de cartão (Nubank CSV)</option>
                    <option value="net_worth_monthly">Controle mensal (Patrimônio/Acúmulo CSV)</option>
                    <option value="current_account">Conta corrente (CSV Nubank)</option>
                </select>
                <p className="mt-2 text-xs text-[var(--text-secondary)]">
                    {uploadType === 'invoice_nubank'
                        ? 'Importa transações do cartão (dashboard de gastos).'
                        : uploadType === 'net_worth_monthly'
                            ? 'Importa uma série mensal do seu patrimônio/acúmulo (tela de Patrimônio).'
                            : 'Importa entradas e saídas da conta corrente e gera despesas a partir das saídas.'}
                </p>
            </div>

            {/* Drop Zone */}
            <div
                onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
                onDragLeave={() => setIsDragOver(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={clsx(
                    "card border-2 border-dashed p-12 text-center cursor-pointer transition-all",
                    isDragOver
                        ? "border-[var(--brand-primary)] bg-[var(--bg-accent)]"
                        : "border-[var(--border-color)] hover:border-[var(--border-hover)]",
                    file && "border-solid border-[var(--brand-primary)] bg-[var(--bg-accent)]"
                )}
            >
                <input
                    ref={fileInputRef}
                    type="file"
                    accept=".csv"
                    onChange={handleFileSelect}
                    className="hidden"
                />

                {file ? (
                    <div className="flex items-center justify-center gap-3">
                        <div className="w-12 h-12 bg-[var(--brand-primary)] rounded-xl flex items-center justify-center">
                            <FileText className="w-6 h-6 text-white" />
                        </div>
                        <div className="text-left">
                            <p className="font-medium text-[var(--text-primary)]">{file.name}</p>
                            <p className="text-sm text-[var(--text-secondary)]">
                                {(file.size / 1024).toFixed(1)} KB
                            </p>
                        </div>
                        <button
                            type="button"
                            onClick={(e) => { e.stopPropagation(); clearFile(); }}
                            className="ml-4 p-2 hover:bg-red-100 rounded-lg text-red-500 transition-colors"
                        >
                            <X className="w-5 h-5" />
                        </button>
                    </div>
                ) : (
                    <>
                        <div className="w-16 h-16 bg-[var(--bg-accent)] rounded-2xl flex items-center justify-center mx-auto mb-4">
                            <UploadCloud className={clsx(
                                "w-8 h-8",
                                isDragOver ? "text-[var(--brand-primary)]" : "text-[var(--text-muted)]"
                            )} />
                        </div>
                        <p className="font-medium text-[var(--text-primary)] mb-1">
                            Arraste seu arquivo CSV aqui
                        </p>
                        <p className="text-sm text-[var(--text-secondary)]">
                            ou clique para selecionar
                        </p>
                    </>
                )}
            </div>

            {/* Form Fields */}
            {(uploadType === 'invoice_nubank' || uploadType === 'current_account' || uploadType === 'net_worth_monthly') && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                        <label className="label">Responsável</label>
                        <select
                            value={owner}
                            onChange={(e) => setOwner(e.target.value)}
                            className="input"
                        >
                            {OWNERS.map(o => (
                                <option key={o} value={o}>{o}</option>
                            ))}
                        </select>
                    </div>

                    {uploadType !== 'net_worth_monthly' && (
                        <div>
                            <label className="label">Mês Referência</label>
                            <input
                                type="month"
                                value={monthRef}
                                onChange={(e) => setMonthRef(e.target.value)}
                                className="input"
                            />
                        </div>
                    )}
                </div>
            )}

            {/* Status Message */}
            {message && (
                <div className={clsx(
                    "p-4 rounded-lg text-sm flex items-center gap-2",
                    status === 'success' && "bg-green-50 text-green-700 border border-green-200",
                    status === 'error' && "bg-red-50 text-red-700 border border-red-200"
                )}>
                    {status === 'success' && <Check className="w-5 h-5" />}
                    {status === 'error' && <X className="w-5 h-5" />}
                    {message}
                </div>
            )}

            {/* Submit Button */}
            <button
                type="submit"
                disabled={!file || status === 'uploading'}
                className={clsx(
                    "btn btn-primary w-full h-12",
                    (!file || status === 'uploading') && "opacity-50 cursor-not-allowed"
                )}
            >
                {status === 'uploading' ? (
                    <>
                        <Loader className="w-5 h-5 animate-spin" />
                        Processando...
                    </>
                ) : (
                    <>
                        <UploadCloud className="w-5 h-5" />
                        Enviar Arquivo
                    </>
                )}
            </button>
        </form>
    );
}
