'use client';

import { Check, X } from 'lucide-react';
import Link from 'next/link';

interface PlanFeature {
  label: string;
  free: string | boolean;
  pro: string | boolean;
  familia: string | boolean;
}

const FEATURES: PlanFeature[] = [
  { label: 'Uploads por mês', free: '2', pro: 'Ilimitado', familia: 'Ilimitado' },
  { label: 'Histórico de transações', free: '3 meses', pro: '12 meses', familia: 'Ilimitado' },
  { label: 'Membros por painel', free: '1', pro: '1', familia: '4' },
  { label: 'Cartões cadastrados', free: '2', pro: '5', familia: '10' },
  { label: 'Exportação de dados', free: false, pro: true, familia: true },
  { label: 'Divisão de despesas', free: false, pro: false, familia: true },
];

function FeatureValue({ value }: { value: string | boolean }) {
  if (typeof value === 'string') {
    return <span className="text-sm text-[var(--color-text-primary)] font-medium">{value}</span>;
  }
  if (value) {
    return <Check className="w-5 h-5 text-emerald-600 mx-auto" aria-label="Incluído" />;
  }
  return <X className="w-5 h-5 text-[var(--color-text-muted)] mx-auto" aria-label="Não incluído" />;
}

export default function PricingTable() {
  return (
    <div className="w-full">
      {/* Mobile: stacked cards */}
      <div className="grid grid-cols-1 gap-6 md:hidden">
        {/* Free */}
        <div className="card p-6">
          <h3 className="text-lg font-bold text-[var(--color-text-primary)]">Free</h3>
          <p className="mt-1 text-3xl font-bold text-[var(--color-text-primary)]">
            R$0<span className="text-sm font-normal text-[var(--color-text-secondary)]">/mês</span>
          </p>
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">Sem cartão de crédito</p>
          <ul className="mt-4 space-y-3">
            {FEATURES.map((f) => (
              <li key={f.label} className="flex items-center justify-between text-sm">
                <span className="text-[var(--color-text-secondary)]">{f.label}</span>
                <FeatureValue value={f.free} />
              </li>
            ))}
          </ul>
          <Link
            href="/login"
            className="btn btn-ghost border border-[var(--color-border)] w-full mt-6"
          >
            Comece grátis
          </Link>
        </div>

        {/* Pro */}
        <div className="card p-6 ring-2 ring-[var(--color-brand-primary)] relative">
          <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-[var(--color-brand-primary)] text-white text-xs font-semibold px-3 py-1 rounded-full">
            Popular
          </span>
          <h3 className="text-lg font-bold text-[var(--color-text-primary)]">Pro</h3>
          <p className="mt-1 text-3xl font-bold text-[var(--color-brand-primary)]">
            R$19<span className="text-sm font-normal text-[var(--color-text-secondary)]">/mês</span>
          </p>
          <ul className="mt-4 space-y-3">
            {FEATURES.map((f) => (
              <li key={f.label} className="flex items-center justify-between text-sm">
                <span className="text-[var(--color-text-secondary)]">{f.label}</span>
                <FeatureValue value={f.pro} />
              </li>
            ))}
          </ul>
          <Link
            href="/login"
            className="btn btn-primary w-full mt-6"
          >
            Assinar Pro
          </Link>
        </div>

        {/* Família */}
        <div className="card p-6">
          <h3 className="text-lg font-bold text-[var(--color-text-primary)]">Família</h3>
          <p className="mt-1 text-3xl font-bold text-[var(--color-text-primary)]">
            R$39<span className="text-sm font-normal text-[var(--color-text-secondary)]">/mês</span>
          </p>
          <ul className="mt-4 space-y-3">
            {FEATURES.map((f) => (
              <li key={f.label} className="flex items-center justify-between text-sm">
                <span className="text-[var(--color-text-secondary)]">{f.label}</span>
                <FeatureValue value={f.familia} />
              </li>
            ))}
          </ul>
          <Link
            href="/login"
            className="btn btn-ghost border border-[var(--color-border)] w-full mt-6"
          >
            Assinar Família
          </Link>
        </div>
      </div>

      {/* Desktop: comparison table */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-[var(--color-border)]">
              <th className="py-4 pr-6 text-sm font-semibold text-[var(--color-text-secondary)]">
                Funcionalidade
              </th>
              <th className="py-4 px-6 text-center">
                <div>
                  <p className="text-base font-bold text-[var(--color-text-primary)]">Free</p>
                  <p className="text-2xl font-bold text-[var(--color-text-primary)] mt-1">R$0</p>
                  <p className="text-xs text-[var(--color-text-muted)]">Sem cartão de crédito</p>
                </div>
              </th>
              <th className="py-4 px-6 text-center relative">
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-[var(--color-brand-primary)] text-white text-[10px] font-semibold px-2.5 py-0.5 rounded-full">
                  Popular
                </span>
                <div>
                  <p className="text-base font-bold text-[var(--color-brand-primary)]">Pro</p>
                  <p className="text-2xl font-bold text-[var(--color-brand-primary)] mt-1">R$19<span className="text-sm font-normal text-[var(--color-text-secondary)]">/mês</span></p>
                </div>
              </th>
              <th className="py-4 pl-6 text-center">
                <div>
                  <p className="text-base font-bold text-[var(--color-text-primary)]">Família</p>
                  <p className="text-2xl font-bold text-[var(--color-text-primary)] mt-1">R$39<span className="text-sm font-normal text-[var(--color-text-secondary)]">/mês</span></p>
                </div>
              </th>
            </tr>
          </thead>
          <tbody>
            {FEATURES.map((f, i) => (
              <tr
                key={f.label}
                className={`border-b border-[var(--color-border)] ${i % 2 === 0 ? 'bg-[var(--color-bg-accent)]/50' : ''}`}
              >
                <td className="py-3.5 pr-6 text-sm text-[var(--color-text-secondary)]">{f.label}</td>
                <td className="py-3.5 px-6 text-center"><FeatureValue value={f.free} /></td>
                <td className="py-3.5 px-6 text-center"><FeatureValue value={f.pro} /></td>
                <td className="py-3.5 pl-6 text-center"><FeatureValue value={f.familia} /></td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td className="py-6 pr-6"></td>
              <td className="py-6 px-6 text-center">
                <Link href="/login" className="btn btn-ghost border border-[var(--color-border)]">
                  Comece grátis
                </Link>
              </td>
              <td className="py-6 px-6 text-center">
                <Link href="/login" className="btn btn-primary">
                  Assinar Pro
                </Link>
              </td>
              <td className="py-6 pl-6 text-center">
                <Link href="/login" className="btn btn-ghost border border-[var(--color-border)]">
                  Assinar Família
                </Link>
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
