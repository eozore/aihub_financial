import type { Metadata } from 'next';
import LandingPageClient from './LandingPageClient';

export const metadata: Metadata = {
  title: 'Finance Pilot | Organize suas finanças em minutos',
  description:
    'Plataforma inteligente de gestão financeira para casais e famílias. Importe extratos PDF, categorize gastos automaticamente e acompanhe seu patrimônio.',
  keywords: [
    'gestão financeira',
    'controle de gastos',
    'finanças pessoais',
    'finanças para casais',
    'importar extrato PDF',
    'Nubank',
    'dashboard financeiro',
  ],
  openGraph: {
    title: 'Finance Pilot | Organize suas finanças em minutos',
    description:
      'Importe extratos PDF, categorize gastos automaticamente e acompanhe seu patrimônio. Comece grátis, sem cartão de crédito.',
    type: 'website',
    locale: 'pt_BR',
    siteName: 'Finance Pilot',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Finance Pilot | Organize suas finanças em minutos',
    description:
      'Importe extratos PDF, categorize gastos automaticamente e acompanhe seu patrimônio.',
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function LandingPage() {
  return <LandingPageClient />;
}
