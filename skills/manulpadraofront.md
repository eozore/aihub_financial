Manual de Padronização Front-end: Ecossistema React Escalável

1. Visão Geral e Fundamentos da Stack

Na engenharia de software de alta performance, a padronização não é um luxo, mas um imperativo estratégico para reduzir a carga cognitiva e acelerar o time-to-market. Como Arquitetura Principal, determinamos a adoção do ecossistema React por sua dominância de mercado e resiliência, garantindo manutenibilidade e acesso aos melhores talentos. Para 2025/2026, nossa stack evolui para além do "React puro", integrando ferramentas que automatizam a performance e garantem segurança de tipos ponta a ponta.

Diretriz de Ferramental: Vite e TanStack Router

Para aplicações de página única (SPA), o Vite é o nosso padrão absoluto. Ele substitui métodos legados (Webpack/CRA) ao oferecer um ambiente de desenvolvimento instantâneo via ESM nativo. No entanto, para garantir a escalabilidade de rotas, mandatamos o uso do TanStack Router em projetos Vite. Ele provê roteamento baseado em arquivos (similar ao Next.js) e type-safety total, eliminando os erros de navegação comuns em bibliotecas como o antigo React Router DOM.

Diferenciação Estratégica: Vite vs. Next.js

A decisão entre Vite e Next.js deve seguir rigorosamente os critérios de SEO e autenticação:

Critério	Vite + TanStack Router (SPA)	Next.js (Framework)
Caso de Uso Principal	Dashboards, Aplicações Internas, Ferramentas SaaS.	E-commerce, Landing Pages, Portais Públicos.
SEO	Limitado (Client-Side Rendering).	Nativo e Otimizado (SSR/Static/Image Opt).
Roteamento	Type-safe via TanStack Router.	File-based nativo (App Router).
Complexidade	Baixa: Foco em lógica de cliente.	Média: Exige gestão de Server Components.


--------------------------------------------------------------------------------


2. Arquitetura de Pastas e Governança de Código

Uma estrutura previsível é a espinha dorsal da produtividade. Determinamos uma organização que isola responsabilidades, mas adota o princípio de Colocation (colocalização): arquivos de estilo e testes específicos de um componente devem residir na mesma pasta que o componente, facilitando a navegação e a refatoração.

Estrutura Mandatória (src/)

* components/: Átomos e moléculas de UI reutilizáveis (ex: Button/, Input/).
* pages/: Rotas da aplicação, organizadas conforme a hierarquia do TanStack Router ou Next.js.
* services/: Camada de infraestrutura e abstração de APIs (Axios/TanStack Query).
* hooks/: Lógica de estado compartilhada e reutilizável.
* assets/: Recursos estáticos e definições de design tokens.

O Fim da Memoização Manual: React Compiler 1.0

Com a estabilização do React Compiler, fica terminantemente depreciado o uso manual de useMemo e useCallback. A equipe não deve gastar tempo com otimizações de referencial que o compilador agora executa automaticamente. O foco deve ser na clareza da lógica de negócio, deixando a performance de re-renderização a cargo da ferramenta.


--------------------------------------------------------------------------------


3. Arquitetura de Estado: Mandato Zustand

Para eliminar o "Context Hell" e as re-renderizações desnecessárias em árvores complexas, estabelecemos o Zustand como padrão de estado global. Ele oferece uma API minimalista que separa explicitamente o estado das ações (actions).

Padrão de Implementação: O estado deve ser atômico. Ao criar um store, as funções de mutação devem ser declaradas dentro do próprio objeto, garantindo que a lógica de alteração de dados esteja centralizada e isolada dos componentes de interface. Isso permite que componentes apenas "assinem" os dados necessários, otimizando o ciclo de vida do React.


--------------------------------------------------------------------------------


4. Engenharia de Formulários: React Hook Form e Zod

O gerenciamento de formulários deve priorizar performance e segurança de dados. A combinação de React Hook Form (componentes não-controlados) e Zod (validação de schema) é obrigatória.

* Validação de Schema: Todo formulário deve possuir um schema Zod que defina a integridade dos dados antes do envio.
* Segurança de Tipos: Deve-se extrair os tipos de TypeScript diretamente do schema Zod (z.infer<typeof schema>), garantindo que o front-end e o back-end falem a mesma língua.
* UX: O feedback de erro deve ser imediato, utilizando as mensagens de erro tipadas provenientes da integração entre as duas bibliotecas.


--------------------------------------------------------------------------------


5. Estilização e Design System: Tailwind CSS

Adotamos o paradigma utility-first com Tailwind CSS. Ele é a ponte mais eficiente entre design e código na era da IA, integrando-se perfeitamente com ferramentas como Cursor e v0.

* Design Engineer Workflow: A equipe deve utilizar o Tailwind para manter a consistência de espaçamento, cores e tipografia (Fonte Poppins como padrão), evitando a inflação de arquivos CSS globais.
* Primitivos de UI: Para componentes complexos de acessibilidade (Modais, Selects), é mandatório o uso de Radix UI ou Base UI, estilizados via classes utilitárias do Tailwind para manter a identidade visual da marca.


--------------------------------------------------------------------------------


6. Integração de API: TanStack Query + Axios

Proibição de useEffect para busca de dados: Fica proibida a implementação de useEffect para chamadas de API. Esta prática é considerada um anti-padrão que gera dívida técnica e bugs de concorrência.

O Padrão TanStack Query

Determinamos o uso do TanStack Query em conjunto com a Suspense API do React. Esta combinação permite:

1. Skeleton Screens: Gestão nativa de estados de carregamento via Suspense.
2. Cashing e Revalidação: Sincronização automática com o servidor sem intervenção manual.
3. Axios Interceptors: O Axios deve ser configurado na pasta services com interceptores globais para gerenciar erros de autenticação (401), CORS e instâncias de URL base.


--------------------------------------------------------------------------------


7. Estratégia de Qualidade: Testes E2E com Playwright

A qualidade é garantida por testes que simulam o comportamento real do usuário. O Playwright (Microsoft) é a nossa ferramenta oficial por sua rapidez e suporte multi-browser.

* Foco Estratégico: A cobertura deve priorizar jornadas críticas: Login, Cadastro e fluxos de escrita/deleção (CRUD).
* Resiliência: Utilize seletores baseados em acessibilidade ou atributos de dados, garantindo que os testes não quebrem com mudanças triviais de estilo.
* IA-Assisted Testing: Encorajamos o uso de ferramentas de IA para gerar scripts de teste Playwright aderentes à estrutura de componentes, acelerando o ciclo de QA.


--------------------------------------------------------------------------------


8. Conclusão e Governança Técnica

Este manual é um documento vivo que define nossa maturidade técnica. Os pilares de Escalabilidade, Padronização e Qualidade aqui expostos visam transformar nossa base de código em um ativo de aceleração.

Visão 2026: Local-first e Evolução Estamos monitorando ativamente a transição para arquiteturas Local-first (como Zero, Electric SQL e TanStack DB), que priorizam a latência zero e o funcionamento offline. A governança técnica deste time deve estar pronta para integrar essas ferramentas conforme a necessidade de sincronização de dados evolui. A engenharia front-end moderna é sobre ser um "Design Engineer": unir estética impecável, performance automatizada e segurança de tipos em cada linha de código.
