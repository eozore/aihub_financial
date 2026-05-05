'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  UploadCloud,
  Search,
  BarChart3,
  Wallet,
  ArrowRight,
  ChevronDown,
  Shield,
  Zap,
  Users,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import PricingTable from '../../components/PricingTable';

const STEPS = [
  {
    icon: UploadCloud,
    title: 'Importe seu extrato',
    description: 'Faça upload do PDF da sua fatura. Suportamos Nubank e mais bancos em breve.',
  },
  {
    icon: Search,
    title: 'Revise e categorize',
    description: 'A IA categoriza seus gastos automaticamente. Você revisa e ajusta o que quiser.',
  },
  {
    icon: BarChart3,
    title: 'Acompanhe no dashboard',
    description: 'Veja seus gastos por categoria, pessoa e período em gráficos claros.',
  },
];

const FAQ_ITEMS = [
  {
    question: 'Preciso de cartão de crédito para começar?',
    answer:
      'Não. O plano Free é totalmente gratuito e não exige cartão de crédito. Você pode usar a plataforma sem compromisso.',
  },
  {
    question: 'Quais bancos são suportados?',
    answer:
      'Atualmente suportamos faturas do Nubank (PDF). Estamos trabalhando para adicionar outros bancos como Itaú, Bradesco e Inter em breve.',
  },
  {
    question: 'Meus dados financeiros estão seguros?',
    answer:
      'Sim. Usamos autenticação via Google (Firebase Auth), isolamento completo de dados por workspace e criptografia em trânsito. Seus dados nunca são compartilhados com terceiros.',
  },
  {
    question: 'Posso usar com meu parceiro(a) ou família?',
    answer:
      'Sim! O plano Família permite até 4 membros no mesmo painel, com divisão automática de despesas entre os participantes.',
  },
  {
    question: 'Como funciona a categorização automática?',
    answer:
      'Usamos inteligência artificial (Gemini) para extrair e categorizar transações do seu extrato. Você pode criar regras personalizadas para ajustar a categorização ao seu estilo.',
  },
  {
    question: 'Posso cancelar a assinatura a qualquer momento?',
    answer:
      'Sim. Você pode cancelar sua assinatura Pro ou Família a qualquer momento. Seus dados permanecem acessíveis no plano Free.',
  },
];

export default function LandingPageClient() {
  const { user, loading } = useAuth();
  const router = useRouter();

  // Redirect authenticated users to dashboard
  useEffect(() => {
    if (!loading && user) {
      router.replace('/dashboard');
    }
  }, [user, loading, router]);

  // Show nothing while checking auth to avoid flash
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[var(--color-bg-primary)]">
        <div className="w-10 h-10 border-4 border-[var(--color-brand-primary)] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // If user is authenticated, they'll be redirected — don't render landing
  if (user) return null;

  return (
    <div className="min-h-screen bg-[var(--color-bg-primary)]">
      {/* Navigation */}
      <nav className="sticky top-0 z-50 bg-white/80 backdrop-blur-md border-b border-[var(--color-border)]">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-[var(--color-brand-primary)] rounded-lg flex items-center justify-center">
              <Wallet className="text-white w-4 h-4" />
            </div>
            <span className="text-lg font-bold text-[var(--color-text-primary)]">Finance Pilot</span>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href="/login"
              className="text-sm font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors"
            >
              Entrar
            </Link>
            <Link href="/login" className="btn btn-primary text-sm py-2 px-4">
              Comece grátis
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 pt-16 pb-20 sm:pt-24 sm:pb-28">
          <div className="max-w-3xl mx-auto text-center">
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-[var(--color-text-primary)] leading-tight tracking-tight">
              Organize suas finanças{' '}
              <span className="text-[var(--color-brand-primary)]">em minutos</span>
            </h1>
            <p className="mt-6 text-lg sm:text-xl text-[var(--color-text-secondary)] max-w-2xl mx-auto leading-relaxed">
              Importe seu extrato PDF, categorize gastos com IA e acompanhe suas finanças
              em um dashboard claro. Para casais e famílias.
            </p>
            <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link href="/login" className="btn btn-primary text-base py-3 px-8 w-full sm:w-auto">
                Comece grátis
                <ArrowRight className="w-5 h-5" />
              </Link>
              <a
                href="#como-funciona"
                className="btn btn-ghost border border-[var(--color-border)] text-base py-3 px-8 w-full sm:w-auto"
              >
                Como funciona
                <ChevronDown className="w-5 h-5" />
              </a>
            </div>
            <p className="mt-4 text-sm text-[var(--color-text-muted)]">
              Grátis para sempre. Sem cartão de crédito.
            </p>
          </div>
        </div>
      </section>

      {/* Trust badges */}
      <section className="border-y border-[var(--color-border)] bg-white">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 text-center">
            <div className="flex flex-col items-center gap-2">
              <Shield className="w-6 h-6 text-[var(--color-brand-primary)]" />
              <p className="text-sm font-medium text-[var(--color-text-primary)]">Dados seguros</p>
              <p className="text-xs text-[var(--color-text-muted)]">Isolamento por workspace</p>
            </div>
            <div className="flex flex-col items-center gap-2">
              <Zap className="w-6 h-6 text-[var(--color-brand-primary)]" />
              <p className="text-sm font-medium text-[var(--color-text-primary)]">IA integrada</p>
              <p className="text-xs text-[var(--color-text-muted)]">Categorização automática</p>
            </div>
            <div className="flex flex-col items-center gap-2">
              <Users className="w-6 h-6 text-[var(--color-brand-primary)]" />
              <p className="text-sm font-medium text-[var(--color-text-primary)]">Para famílias</p>
              <p className="text-xs text-[var(--color-text-muted)]">Até 4 membros por painel</p>
            </div>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="como-funciona" className="py-16 sm:py-24">
        <div className="max-w-6xl mx-auto px-4 sm:px-6">
          <div className="text-center mb-12">
            <h2 className="text-3xl sm:text-4xl font-bold text-[var(--color-text-primary)]">
              Como funciona
            </h2>
            <p className="mt-3 text-[var(--color-text-secondary)] max-w-xl mx-auto">
              Três passos simples para ter controle total das suas finanças.
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {STEPS.map((step, i) => (
              <div key={step.title} className="card p-6 text-center">
                <div className="w-14 h-14 mx-auto rounded-2xl bg-[var(--color-bg-accent)] flex items-center justify-center mb-4">
                  <step.icon className="w-7 h-7 text-[var(--color-brand-primary)]" />
                </div>
                <span className="inline-block text-xs font-semibold text-[var(--color-brand-primary)] bg-[var(--color-bg-accent)] px-2.5 py-1 rounded-full mb-3">
                  Passo {i + 1}
                </span>
                <h3 className="text-lg font-semibold text-[var(--color-text-primary)] mb-2">
                  {step.title}
                </h3>
                <p className="text-sm text-[var(--color-text-secondary)] leading-relaxed">
                  {step.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Supported banks */}
      <section className="py-16 sm:py-20 bg-white border-y border-[var(--color-border)]">
        <div className="max-w-6xl mx-auto px-4 sm:px-6">
          <div className="text-center mb-10">
            <h2 className="text-3xl sm:text-4xl font-bold text-[var(--color-text-primary)]">
              Bancos suportados
            </h2>
            <p className="mt-3 text-[var(--color-text-secondary)]">
              Começamos com o banco digital mais popular do Brasil.
            </p>
          </div>
          <div className="flex flex-wrap items-center justify-center gap-6">
            <div className="card p-6 flex items-center gap-4 min-w-[200px]">
              <div className="w-12 h-12 rounded-xl bg-purple-100 flex items-center justify-center">
                <span className="text-purple-700 font-bold text-lg">Nu</span>
              </div>
              <div>
                <p className="font-semibold text-[var(--color-text-primary)]">Nubank</p>
                <p className="text-xs text-emerald-600 font-medium">Disponível</p>
              </div>
            </div>
            <div className="card p-6 flex items-center gap-4 min-w-[200px] opacity-50">
              <div className="w-12 h-12 rounded-xl bg-gray-100 flex items-center justify-center">
                <span className="text-gray-400 font-bold text-lg">+</span>
              </div>
              <div>
                <p className="font-semibold text-[var(--color-text-secondary)]">Mais bancos</p>
                <p className="text-xs text-[var(--color-text-muted)]">Em breve</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Screenshots / Product preview */}
      <section className="py-16 sm:py-24">
        <div className="max-w-6xl mx-auto px-4 sm:px-6">
          <div className="text-center mb-12">
            <h2 className="text-3xl sm:text-4xl font-bold text-[var(--color-text-primary)]">
              Veja o produto em ação
            </h2>
            <p className="mt-3 text-[var(--color-text-secondary)] max-w-xl mx-auto">
              Dashboard intuitivo com gráficos claros e categorização inteligente.
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="card p-8 bg-gradient-to-br from-[var(--color-bg-accent)] to-white">
              <div className="flex items-center gap-3 mb-4">
                <BarChart3 className="w-6 h-6 text-[var(--color-brand-primary)]" />
                <h3 className="font-semibold text-[var(--color-text-primary)]">Dashboard completo</h3>
              </div>
              <p className="text-sm text-[var(--color-text-secondary)] leading-relaxed">
                Gastos por categoria, por pessoa e tendências mensais. Tudo em um só lugar,
                com filtros por período e tipo de despesa.
              </p>
            </div>
            <div className="card p-8 bg-gradient-to-br from-[var(--color-bg-accent)] to-white">
              <div className="flex items-center gap-3 mb-4">
                <UploadCloud className="w-6 h-6 text-[var(--color-brand-primary)]" />
                <h3 className="font-semibold text-[var(--color-text-primary)]">Upload inteligente</h3>
              </div>
              <p className="text-sm text-[var(--color-text-secondary)] leading-relaxed">
                Arraste seu PDF, revise as transações extraídas pela IA e confirme a importação.
                Cartões são detectados automaticamente.
              </p>
            </div>
            <div className="card p-8 bg-gradient-to-br from-[var(--color-bg-accent)] to-white">
              <div className="flex items-center gap-3 mb-4">
                <Wallet className="w-6 h-6 text-[var(--color-brand-primary)]" />
                <h3 className="font-semibold text-[var(--color-text-primary)]">Patrimônio</h3>
              </div>
              <p className="text-sm text-[var(--color-text-secondary)] leading-relaxed">
                Acompanhe a evolução do seu patrimônio mês a mês, com validação automática
                de entrada e saída baseada nos seus extratos.
              </p>
            </div>
            <div className="card p-8 bg-gradient-to-br from-[var(--color-bg-accent)] to-white">
              <div className="flex items-center gap-3 mb-4">
                <Users className="w-6 h-6 text-[var(--color-brand-primary)]" />
                <h3 className="font-semibold text-[var(--color-text-primary)]">Gestão de painel</h3>
              </div>
              <p className="text-sm text-[var(--color-text-secondary)] leading-relaxed">
                Convide membros, gerencie cartões e configure regras de categorização
                personalizadas para o seu workspace.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="precos" className="py-16 sm:py-24 bg-white border-y border-[var(--color-border)]">
        <div className="max-w-6xl mx-auto px-4 sm:px-6">
          <div className="text-center mb-12">
            <h2 className="text-3xl sm:text-4xl font-bold text-[var(--color-text-primary)]">
              Planos e preços
            </h2>
            <p className="mt-3 text-[var(--color-text-secondary)] max-w-xl mx-auto">
              Comece grátis e evolua conforme sua necessidade. Sem surpresas.
            </p>
          </div>
          <PricingTable />
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" className="py-16 sm:py-24">
        <div className="max-w-3xl mx-auto px-4 sm:px-6">
          <div className="text-center mb-12">
            <h2 className="text-3xl sm:text-4xl font-bold text-[var(--color-text-primary)]">
              Perguntas frequentes
            </h2>
          </div>
          <div className="space-y-3">
            {FAQ_ITEMS.map((item) => (
              <details
                key={item.question}
                className="group card overflow-hidden"
              >
                <summary className="flex items-center justify-between cursor-pointer p-5 text-sm font-medium text-[var(--color-text-primary)] hover:bg-[var(--color-bg-accent)] transition-colors list-none [&::-webkit-details-marker]:hidden">
                  <span>{item.question}</span>
                  <ChevronDown className="w-5 h-5 text-[var(--color-text-muted)] transition-transform group-open:rotate-180 shrink-0 ml-4" />
                </summary>
                <div className="px-5 pb-5 text-sm text-[var(--color-text-secondary)] leading-relaxed">
                  {item.answer}
                </div>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="py-16 sm:py-24 bg-[var(--color-brand-primary)]">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 text-center">
          <h2 className="text-3xl sm:text-4xl font-bold text-white leading-tight">
            Pronto para organizar suas finanças?
          </h2>
          <p className="mt-4 text-lg text-white/80">
            Crie sua conta em segundos. Sem cartão de crédito, sem compromisso.
          </p>
          <Link
            href="/login"
            className="inline-flex items-center justify-center gap-2 mt-8 bg-white text-[var(--color-brand-primary)] font-semibold text-base py-3 px-8 rounded-lg hover:bg-gray-50 transition-colors"
          >
            Comece grátis agora
            <ArrowRight className="w-5 h-5" />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-[var(--color-border)] bg-white">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 bg-[var(--color-brand-primary)] rounded-md flex items-center justify-center">
              <Wallet className="text-white w-3 h-3" />
            </div>
            <span className="text-sm font-semibold text-[var(--color-text-primary)]">Finance Pilot</span>
          </div>
          <p className="text-xs text-[var(--color-text-muted)]">
            © {new Date().getFullYear()} Finance Pilot. Todos os direitos reservados.
          </p>
          <a
            href="https://victorzoredev.github.io/zore-portfolio/"
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-brand-primary)] transition-colors"
          >
            Powered by <strong>Victor Zoré</strong>
          </a>
        </div>
      </footer>
    </div>
  );
}
