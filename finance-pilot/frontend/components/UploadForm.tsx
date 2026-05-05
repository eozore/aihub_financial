'use client';

import { useState, useRef } from 'react';
import { uploadFile, UploadPreviewResponse } from '../services/api';
import { UploadCloud, FileText, Loader, X } from 'lucide-react';
import clsx from 'clsx';
import UploadPreview from './UploadPreview';

export default function UploadForm() {
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<'idle' | 'uploading' | 'preview' | 'error'>('idle');
  const [message, setMessage] = useState('');
  const [isDragOver, setIsDragOver] = useState(false);
  const [previewData, setPreviewData] = useState<UploadPreviewResponse | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const ACCEPTED_EXTENSIONS = ['.pdf', '.csv'];
  const ACCEPTED_MIME_TYPES = ['application/pdf', 'text/csv', 'text/plain'];

  const isAcceptedFile = (f: File): boolean => {
    const ext = f.name.toLowerCase().slice(f.name.lastIndexOf('.'));
    return ACCEPTED_EXTENSIONS.includes(ext) || ACCEPTED_MIME_TYPES.includes(f.type);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile && isAcceptedFile(droppedFile)) {
      setFile(droppedFile);
      setStatus('idle');
      setMessage('');
    } else if (droppedFile) {
      setMessage('Formato não suportado. Envie um arquivo PDF ou CSV.');
      setStatus('error');
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      setFile(selectedFile);
      setStatus('idle');
      setMessage('');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;

    setStatus('uploading');
    setMessage('');

    try {
      const preview = await uploadFile(file);
      setPreviewData(preview);
      setStatus('preview');
    } catch (error: unknown) {
      setStatus('error');
      const axiosError = error as { response?: { data?: { detail?: string } } };
      setMessage(axiosError.response?.data?.detail || 'Erro ao processar arquivo.');
    }
  };

  const clearFile = () => {
    setFile(null);
    setStatus('idle');
    setMessage('');
    setPreviewData(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handlePreviewBack = () => {
    setStatus('idle');
    setPreviewData(null);
  };

  // Show preview screen after successful upload
  if (status === 'preview' && previewData) {
    return (
      <UploadPreview
        data={previewData}
        onBack={handlePreviewBack}
        onConfirmed={() => {
          clearFile();
        }}
      />
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Drop Zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') fileInputRef.current?.click(); }}
        className={clsx(
          'card border-2 border-dashed p-12 text-center cursor-pointer transition-all',
          isDragOver
            ? 'border-[var(--color-brand-primary)] bg-[var(--color-bg-accent)]'
            : 'border-[var(--color-border)] hover:border-[var(--color-border-hover)]',
          file && 'border-solid border-[var(--color-brand-primary)] bg-[var(--color-bg-accent)]'
        )}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.csv"
          onChange={handleFileSelect}
          className="hidden"
          aria-label="Selecionar arquivo PDF ou CSV"
        />

        {file ? (
          <div className="flex items-center justify-center gap-3">
            <div className="w-12 h-12 bg-[var(--color-brand-primary)] rounded-xl flex items-center justify-center">
              <FileText className="w-6 h-6 text-white" />
            </div>
            <div className="text-left">
              <p className="font-medium text-[var(--color-text-primary)]">{file.name}</p>
              <p className="text-sm text-[var(--color-text-secondary)]">
                {(file.size / 1024).toFixed(1)} KB
              </p>
            </div>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); clearFile(); }}
              className="ml-4 p-2 hover:bg-red-100 rounded-lg text-red-500 transition-colors"
              aria-label="Remover arquivo"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        ) : (
          <>
            <div className="w-16 h-16 bg-[var(--color-bg-accent)] rounded-2xl flex items-center justify-center mx-auto mb-4">
              <UploadCloud className={clsx(
                'w-8 h-8',
                isDragOver ? 'text-[var(--color-brand-primary)]' : 'text-[var(--color-text-muted)]'
              )} />
            </div>
            <p className="font-medium text-[var(--color-text-primary)] mb-1">
              Arraste seu arquivo PDF ou CSV aqui
            </p>
            <p className="text-sm text-[var(--color-text-secondary)]">
              ou clique para selecionar
            </p>
            <p className="text-xs text-[var(--color-text-muted)] mt-2">
              Faturas de cartão (PDF) e extratos (CSV) são detectados automaticamente
            </p>
          </>
        )}
      </div>

      {/* Status Message */}
      {message && (
        <div className={clsx(
          'p-4 rounded-lg text-sm flex items-center gap-2',
          status === 'error' && 'bg-red-50 text-red-700 border border-red-200'
        )}>
          <X className="w-5 h-5 shrink-0" />
          {message}
        </div>
      )}

      {/* Submit Button */}
      <button
        type="submit"
        disabled={!file || status === 'uploading'}
        className={clsx(
          'btn btn-primary w-full h-12',
          (!file || status === 'uploading') && 'opacity-50 cursor-not-allowed'
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
            Enviar e Visualizar
          </>
        )}
      </button>
    </form>
  );
}
