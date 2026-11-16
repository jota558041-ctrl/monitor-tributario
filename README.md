# Monitor Tributário

Plataforma de monitoramento tributário para escritórios e consultorias que operam
compensações: importa a carteira de clientes, acompanha **PER/DCOMP**, **procurações
eletrônicas** e **situação fiscal**, compara consultas ao longo do tempo e gera
**alertas explicáveis** — com origem e data/hora de cada informação.

> **Estado atual:** protótipo funcional completo, operando com dados fictícios
> (conector *simulador*). A integração com serviços oficiais é um adaptador
> presente, documentado e **desligado por padrão** — ver
> [docs/INTEGRACAO_RECEITA_FEDERAL.md](docs/INTEGRACAO_RECEITA_FEDERAL.md).

---

## Princípios inegociáveis (implementados e testados)

| Princípio | Como o sistema garante |
|---|---|
| Transmissão **não** é homologação | Estados distintos e separados; situação só muda com evidência da fonte (`tests/test_regras_negocio.py::test_transmissao_nao_vira_homologacao`) |
| Procuração em planilha **não** é procuração ativa | A planilha alimenta `situacao_declarada`; a situação oficial exige validação por fonte, senão o semáforo fica **CINZA** |
| Falha de consulta **não** é ausência de pendência | `Disponibilidade` (OK / SEM_DADOS / INDISPONIVEL / NAO_AUTORIZADO / NAO_CONSULTADO) é separada do resultado de negócio |
| Toda informação tem procedência | Origem + data/hora + hash de conteúdo em cada consulta, snapshot e evento |
| A IA não inventa fato fiscal | Motor de regras determinístico; LLM opcional apenas reescreve fatos já apurados |
| Redução de débito **não** prova causalidade | Todo comparativo carrega ressalva explícita |

---

## Início rápido (3 minutos, sem Docker)

```bash
cd backend && python3 -m pip install -r requirements-dev.txt
```

```bash
cd backend && MT_SCHEDULER_ENABLED=false python3 -m scripts.seed --reset
```

```bash
cd backend && python3 -m uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

Acesse `http://localhost:5173` (ou `http://localhost:8000`, que serve o frontend
compilado quando existe `frontend/dist`).

**Credenciais de demonstração**

| Perfil | E-mail | Senha |
|---|---|---|
| Administrador | `admin@monitortributario.com.br` | `Admin@123456` |
| Analista | `analista@monitortributario.com.br` | `Analista@123456` |
| Auditor (somente leitura) | `auditor@monitortributario.com.br` | `Auditor@123456` |

## Com Docker

```bash
cp .env.example .env && docker compose up --build
```

Frontend em `http://localhost:8080`, API em `http://localhost:8000`,
documentação interativa em `http://localhost:8000/docs`.

---

## Módulos

1. **Cadastro e importação** — `.xlsx`/`.csv`, detecção automática de colunas,
   validação de CNPJ (módulo 11), duplicidades, correção linha a linha antes de
   gravar, histórico campo a campo.
2. **Compensações (PER/DCOMP)** — 9 classificações, despacho decisório, intimação,
   valores homologados/não homologados e linha do tempo de cada declaração.
3. **Procurações eletrônicas** — semáforo verde/amarelo/vermelho/cinza, alertas em
   30/15/7/0 dias, histórico de consultas.
4. **Situação fiscal** — snapshots imutáveis por consulta e comparativo
   (novos, baixados, remanescentes, alterados) com ressalva de causalidade.
5. **Integração** — camada de conectores com proveniência: `manual`, `simulador`
   e `integra_contador` (SERPRO), configurável por domínio.
6. **Interpretação (IA)** — achados explicáveis com evidência, resumo por cliente
   e ranking de clientes que exigem atenção.
7. **Painel administrativo** — React + TypeScript, identidade azul-marinho, KPIs,
   gráficos e filtros.
8. **Alertas automáticos** — regras com cron, criticidade mínima, escopo de
   clientes, notificações em sistema e e-mail (preparado), deduplicação.

## Documentação

| Documento | Conteúdo |
|---|---|
| [docs/ARQUITETURA.md](docs/ARQUITETURA.md) | Visão de componentes, fluxos e decisões de projeto |
| [docs/BANCO_DE_DADOS.md](docs/BANCO_DE_DADOS.md) | 19 tabelas, relacionamentos e migrações |
| [docs/INSTALACAO.md](docs/INSTALACAO.md) | Instalação local, Docker e produção |
| [docs/MANUAL_DE_USO.md](docs/MANUAL_DE_USO.md) | Passo a passo de cada tela |
| [docs/INTEGRACAO_RECEITA_FEDERAL.md](docs/INTEGRACAO_RECEITA_FEDERAL.md) | O que existe oficialmente, requisitos e limites |
| [docs/SEGURANCA_LGPD.md](docs/SEGURANCA_LGPD.md) | Controles de segurança e adequação à LGPD |
| [docs/RELATORIO_DE_TESTES.md](docs/RELATORIO_DE_TESTES.md) | Resultado dos testes executados |

## Estrutura

```
monitor-tributario/
├── backend/           FastAPI + SQLAlchemy + APScheduler
│   ├── app/
│   │   ├── api/       rotas HTTP
│   │   ├── connectors/ fontes de dados (manual, simulador, integra_contador)
│   │   ├── core/      config, banco, segurança, criptografia, auditoria
│   │   ├── ia/        motor de regras explicável e resumos
│   │   ├── models/    19 modelos ORM
│   │   ├── schemas/   contratos Pydantic
│   │   └── services/  regras de negócio
│   ├── alembic/       migrações
│   ├── scripts/       seed e massa demonstrativa
│   └── tests/         53 testes automatizados
├── frontend/          React 18 + TypeScript + Vite + Recharts
├── e2e/               teste de interface (Playwright) + capturas
├── data/              planilhas de teste e modelo de importação
└── docs/              documentação técnica e de uso
```

## Testes

```bash
cd backend && python3 -m pytest tests/ -v
```

```bash
node e2e/fluxo-ui.mjs http://127.0.0.1:8000
```

Resultado da última execução: **53 testes de backend** (SQLite e PostgreSQL 16) e
**17 etapas de interface** — todos passando. Detalhes em
[docs/RELATORIO_DE_TESTES.md](docs/RELATORIO_DE_TESTES.md).

## Licença e uso

Projeto desenvolvido sob encomenda. O uso das integrações oficiais depende de
contrato próprio com o provedor (SERPRO) e de procurações eletrônicas válidas
concedidas pelos contribuintes.
