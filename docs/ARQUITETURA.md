# Arquitetura — Monitor Tributário

## 1. Visão geral

```
┌──────────────────────────────────────────────────────────────────────────┐
│ NAVEGADOR                                                                │
│  React 18 + TypeScript + Vite + Recharts (SPA)                           │
│  Painel · Clientes · Importação · Compensações · Procurações             │
│  Situação fiscal · Alertas · Monitoramento · Fontes · Auditoria          │
└──────────────┬───────────────────────────────────────────────────────────┘
               │ HTTPS + JWT (Bearer)
┌──────────────▼───────────────────────────────────────────────────────────┐
│ API — FastAPI                                                            │
│  ├─ api/        rotas, validação Pydantic, RBAC, auditoria               │
│  ├─ services/   regras de negócio (importação, compensações, fiscal...)  │
│  ├─ ia/         motor de regras explicável + resumos                     │
│  ├─ connectors/ abstração das fontes de informação                       │
│  └─ core/       config, segurança, criptografia, sessão de banco         │
└───────┬─────────────────────────────┬────────────────────────────────────┘
        │                             │
┌───────▼─────────┐        ┌──────────▼──────────────────────────────────┐
│ PostgreSQL 16   │        │ APScheduler (monitoramento agendado)        │
│ 19 tabelas      │        │ jobs cron por regra cadastrada              │
│ histórico       │        └──────────┬──────────────────────────────────┘
│ imutável        │                   │
└─────────────────┘        ┌──────────▼──────────────────────────────────┐
                           │ FONTES DE DADOS (conectores plugáveis)      │
                           │  manual ........ importação de resultado    │
                           │  simulador ..... ambiente de teste          │
                           │  integra_contador  API SERPRO (desligada)   │
                           └─────────────────────────────────────────────┘
```

## 2. Decisões de projeto e seus motivos

### 2.1 Proveniência como cidadã de primeira classe
Toda informação fiscal gravada carrega quatro atributos: **origem**
(`OrigemInformacao`), **disponibilidade** (`Disponibilidade`), **data/hora da
consulta** e, quando aplicável, **hash do conteúdo**. Isso permite responder, em
qualquer momento: *de onde veio este dado, quando, e o que mudou desde então.*

`Disponibilidade` é deliberadamente separada do resultado de negócio:

| Valor | Significado |
|---|---|
| `OK` | consulta concluída, dados retornados |
| `SEM_DADOS` | consulta concluída, fonte não localizou registro |
| `INDISPONIVEL` | fonte fora do ar, erro de rede, bloqueio |
| `NAO_AUTORIZADO` | falta procuração, poderes ou credencial |
| `NAO_CONSULTADO` | nunca houve consulta automática |

Sem essa separação, um erro de rede viraria "cliente regular" — exatamente o
risco que o projeto precisa evitar.

### 2.2 Conectores plugáveis
Cada domínio (procuração, compensação, situação fiscal) tem um conector
configurável por variável de ambiente. Os três implementam o mesmo contrato
(`app/connectors/base.py`) e devolvem `ResultadoConsulta`. Consequências:

* a aplicação funciona hoje sem nenhuma integração real;
* trocar de fonte não altera regra de negócio nem o modelo de dados;
* a tela **Fontes de dados** publica as limitações declaradas por cada conector.

### 2.3 Snapshots imutáveis + comparativo derivado
A situação fiscal nunca sofre `UPDATE`: cada consulta cria um
`situacao_fiscal_snapshot`. A comparação entre dois snapshots gera
`situacao_fiscal_comparativo`, que classifica cada pendência em **novo**,
**baixado**, **remanescente** ou **alterado**, usando uma chave estável
(categoria + código/descrição + período). O comparativo sempre carrega a
ressalva de que a variação **não** implica causalidade com as compensações.

### 2.4 Motor de regras explicável (camada de "IA")
`app/ia/analise.py` recebe o estado persistido e os diffs da consulta e produz
objetos `Achado`, cada um com: tipo, criticidade, título, mensagem, **explicação
do porquê** e **lista de evidências** (fonte, data da consulta, campo, valor
anterior, valor novo). Os alertas gravados são projeções desses achados.

A reescrita por LLM (`app/ia/resumo.py`) é **opcional e desligada por padrão**;
quando ligada, recebe apenas os fatos já apurados, é instruída a não acrescentar
informação e, em caso de falha, o texto determinístico é mantido.

### 2.5 Deduplicação por estado observado
Cada achado produz uma `dedup_key` que inclui o estado observado
(ex.: `COMP:<id>:MUDANCA:HOMOLOGADA->EM_ANALISE`). Rodar o monitoramento dez
vezes no mesmo estado não gera dez alertas; mudar o estado gera um alerta novo.
Alertas resolvidos que voltam a ocorrer são **reabertos**, preservando histórico.

### 2.6 Multiempresa e segregação
Todas as entidades de negócio carregam `organizacao_id` e toda consulta filtra
por ele a partir do token JWT. Há teste automatizado que tenta ler um cliente de
outra organização e exige `404`.

## 3. Fluxos principais

### 3.1 Importação de planilha
```
upload .xlsx/.csv
   └─ leitura (pandas/openpyxl, detecção de separador e encoding)
      └─ detecção de colunas (exata → sinônimos → similaridade ≥ 0,86)
         └─ normalização por tipo (data BR/ISO/serial Excel, moeda BR/US, período)
            └─ validação (CNPJ módulo 11, e-mail, coerência de datas, duplicidade)
               └─ STAGING: importacao + importacao_linha (nada no cadastro ainda)
                  └─ correção pelo usuário (revalida a linha)
                     └─ CONFIRMAÇÃO → upsert cliente/procuração/PER-DCOMP
                        └─ histórico (cliente_historico, compensacao_evento)
```

### 3.2 Execução de monitoramento
```
para cada cliente ativo no escopo:
  procurações   → conector → registrar_consulta → diff → achados
  PER/DCOMP     → conector → registrar_consulta → diff → achados
  situação fiscal → conector → snapshot → comparar(anterior, atual) → achados
  frescor da informação → achados
registrar_achados (dedup) → alertas → notificações (sistema/e-mail)
execucao_monitoramento: contadores de OK / indisponível / não autorizado /
                        mudanças / alertas + detalhe por cliente
```

### 3.3 Agendamento
`RegraMonitoramento` (nome, tipo, cron, criticidade mínima, escopo de clientes,
canais, destinatários) é lida pelo APScheduler na inicialização e a cada
alteração (`recarregar()`), que reprograma os jobs. Sem regras cadastradas, vale
o cron padrão (`MT_MONITORAMENTO_CRON`).

## 4. Camadas e responsabilidades

| Camada | Pasta | Responsabilidade | Não faz |
|---|---|---|---|
| Rotas | `app/api` | HTTP, validação, RBAC, auditoria | regra de negócio |
| Serviços | `app/services` | regra de negócio e persistência | HTTP, I/O externo |
| Conectores | `app/connectors` | falar com fontes externas | decidir negócio |
| IA | `app/ia` | interpretar e explicar | criar fato, persistir |
| Modelos | `app/models` | estrutura de dados | lógica |
| Core | `app/core` | config, sessão, cripto, JWT, auditoria | domínio |

## 5. Segurança (resumo; detalhes em SEGURANCA_LGPD.md)

* Autenticação JWT HS256 com expiração configurável; senhas com **bcrypt** (12 rounds).
* Perfis **ADMIN**, **ANALISTA** (escrita) e **AUDITOR** (somente leitura).
* Campos sensíveis cifrados em repouso com **Fernet** (`TextoCriptografado`).
* Trilha de auditoria para login, leitura de ficha, alterações, consultas,
  importações, simulações e tratamento de alertas.
* Cabeçalhos de segurança em todas as respostas; HSTS em produção.
* **Nenhuma senha gov.br é armazenada.** Chave privada de certificado fica em
  volume protegido, nunca no banco; apenas a senha do arquivo é cifrada.

## 6. Escalabilidade e evolução

* API sem estado: escala horizontalmente atrás de um balanceador.
* O agendador deve rodar em **uma** instância (ou migrar para fila/worker
  dedicado — Celery/RQ — quando o volume justificar).
* Conectores já têm *rate limiting* por minuto (contratos de API costumam impor).
* Índices nas colunas de filtro mais usadas (organização, situação, datas, CNPJ).
* Snapshots crescem linearmente com clientes × frequência: política de retenção
  configurável (`MT_RETENCAO_CONSULTAS_DIAS`).

## 7. Tecnologias

| Camada | Tecnologia | Motivo |
|---|---|---|
| API | FastAPI 0.1xx | validação por tipos, OpenAPI automático, assíncrono |
| ORM | SQLAlchemy 2.0 | mapeamento tipado, portabilidade PostgreSQL/SQLite |
| Migrações | Alembic | versionamento do esquema |
| Banco | PostgreSQL 16 | integridade, JSONB, numeric exato para valores |
| Agendador | APScheduler | cron em processo, sem infraestrutura extra |
| Planilhas | pandas + openpyxl | leitura tolerante de `.xlsx`/`.csv` |
| Frontend | React 18 + TS + Vite | ecossistema maduro, build rápido, tipagem |
| Gráficos | Recharts | integração natural com React |
| Testes | pytest + Playwright | unidade/integração + interface real |
| Empacotamento | Docker + Compose | reprodutibilidade |
