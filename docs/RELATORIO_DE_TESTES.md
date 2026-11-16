# Relatório de testes

**Data da execução:** 16/11/2026
**Ambiente:** Python 3.13.18 · Node 22.23.4 · PostgreSQL 16.15 · Chromium (Playwright)

## 1. Resumo

| Suíte | Itens | Resultado | Tempo |
|---|---|---|---|
| Backend — SQLite | 53 testes | **53 passaram** | 38,0 s |
| Backend — PostgreSQL 16 | 53 testes | **53 passaram** | 38,2 s |
| Interface — Playwright | 17 etapas | **17 passaram** | ~40 s |
| Migração Alembic | upgrade → downgrade → upgrade | **OK** (20 tabelas, reversível) | — |
| Build do frontend | `tsc -b && vite build` | **OK**, sem erro de tipo | 3,0 s |
| Carga demonstrativa | `scripts.seed --reset` | **OK** em SQLite e PostgreSQL | — |

Nenhuma falha pendente. Nenhum erro de console no navegador durante o fluxo.

## 2. Testes de validação (23)
`backend/tests/test_validacao.py`

* CNPJ: válido formatado e não formatado, dígito verificador incorreto, dígitos
  repetidos, tamanho inválido, vazio; CNPJs gerados para a massa de teste são
  matematicamente válidos; CPF válido e inválido.
* Conversão de valores: `R$ 1.234,56`, `1.234,56`, `1,234.56`, `1234.56`,
  negativo entre parênteses, vazio e nulo.
* Conversão de datas: `dd/mm/aaaa`, ISO, `dd.mm.aaaa`, texto inválido, serial do
  Excel. Período de apuração em três formatos.
* Detecção de colunas: a planilha exatamente como descrita no escopo do projeto
  é mapeada 100% sem colunas ignoradas; variações ("cnpj do contribuinte",
  "empresa", "vencimento procuracao", "perdcomp") também são reconhecidas, e
  coluna desconhecida é devolvida como ignorada.
* Normalização de situação declarada ("Homologada", "deferida parcialmente",
  texto desconhecido → `None`).

## 3. Testes de regra de negócio (18)
`backend/tests/test_regras_negocio.py`

### Procurações — nada é presumido
| Teste | Garante |
|---|---|
| `procuracao_da_planilha_nao_e_considerada_ativa` | situação do sistema = `DESCONHECIDA`, declarada = `ATIVA`, semáforo **CINZA** |
| `procuracao_fica_ativa_somente_apos_validacao_por_fonte` | após consulta OK → `ATIVA`, semáforo **VERDE** |
| `semaforo_amarelo_quando_proxima_do_vencimento` | 9 dias para vencer → `PROXIMA_VENCIMENTO`, **AMARELO** |
| `consulta_indisponivel_nao_mantem_procuracao_como_ativa` | após falha → volta a `DESCONHECIDA`/**CINZA**, com as duas consultas no histórico |
| `alerta_de_procuracao_vencendo_tem_evidencia_e_faixa` | alerta traz evidência com data da consulta e faixa aplicada |

### Compensações — transmissão ≠ homologação
| Teste | Garante |
|---|---|
| `transmissao_nao_vira_homologacao` | `TRANSMITIDA` não gera alerta de não homologação nem vira homologação |
| `sem_situacao_informada_fica_sem_informacao` | ausência de dado → `SEM_INFORMACAO` |
| `mudanca_de_situacao_gera_evento_e_alerta` | `EM_ANALISE → NAO_HOMOLOGADA` cria evento e alerta crítico |
| `perda_de_homologacao_gera_alerta_critico` | `HOMOLOGADA → EM_ANALISE` gera `COMPENSACAO_PERDEU_HOMOLOGACAO` (CRÍTICA) com evidência `de=HOMOLOGADA` |
| `falha_de_consulta_preserva_situacao_conhecida` | indisponibilidade **não** rebaixa a situação; marca `INDISPONIVEL` e alerta de fonte |

### Situação fiscal — comparação sem causalidade
| Teste | Garante |
|---|---|
| `comparativo_identifica_novos_baixados_e_remanescentes` | classificação correta e ressalva presente |
| `cenario_do_enunciado_15k_para_5k` | diferença de −R$ 10.000,00, variação por pendência e ressalva na explicação |
| `debitos_suspensos_e_parcelamentos_nao_entram_no_total_exigivel` | total exigível isolado dos suspensos/parcelados |
| `indisponibilidade_nao_e_regularidade` | `INDISPONIVEL` ≠ `REGULAR`; explicação diz que não se conclui regularidade |
| `nao_autorizado_tambem_nao_e_regularidade` | idem para falta de poderes |
| `debito_remanescente_apos_homologacao` | cruza pendências remanescentes com PER/DCOMP homologadas e declara que **não afirma** nexo |

### Frescor e alertas
| Teste | Garante |
|---|---|
| `frescor_detecta_nunca_consultado` | gera `CONSULTA_DESATUALIZADA` para cliente sem consulta |
| `deduplicacao_de_alertas` | mesmo estado duas vezes → 1 alerta criado, 1 repetido |

## 4. Testes de API e permissões (12)
`backend/tests/test_api.py`

* `/api/health` e `/api/info` abertos; endpoints de negócio exigem token.
* Login inválido devolve 401 e registra `LOGIN_FALHA`.
* **AUDITOR** lê mas não escreve (403); **ANALISTA** não cria usuário (403).
* CNPJ inválido recusado com 422 na criação de cliente.
* **Fluxo completo** (`test_fluxo_completo_importacao_monitoramento_alertas`),
  em 12 verificações encadeadas:
  1. upload da planilha com 4 linhas → status `VALIDADO`, colunas mapeadas;
  2. 1 linha com CNPJ inválido bloqueada, 1 duplicada detectada;
  3. correção da linha inválida → revalidada como `CRIAR`;
  4. confirmação grava 2 clientes, 3 PER/DCOMP (a duplicada não entra), 1 ignorada;
  5. procurações importadas ficam **CINZA** (nenhuma verde);
  6. PER/DCOMP sem situação informada fica `SEM_INFORMACAO` e `NAO_CONSULTADO`;
  7. monitoramento executa sobre 2 clientes com consultas OK;
  8. após a consulta, procuração vencendo em 10 dias fica **AMARELA**;
  9. simulação `NAO_HOMOLOGAR` + nova execução gera alerta **CRÍTICO** com
     explicação e evidência datada;
  10. notificação registrada;
  11. dashboard reflete os números e indica o conector em uso;
  12. resumo da IA traz método, conteúdo e os três limites; auditoria contém
      `LOGIN`, `IMPORTACAO_CONFIRMADA`, `MONITORAMENTO` e `ALERTA_ACAO`.
* Registro manual de resultado de PER/DCOMP grava origem `IMPORTACAO_RELATORIO`
  e cria evento no histórico.
* Situação fiscal manual: duas consultas (R$ 15.000 → R$ 5.000) geram
  comparativo com diferença `-10000.00` e ressalva; visão geral mostra a variação.
* Modelo de planilha baixável em `.xlsx`; catálogo de campos exposto.
* `/api/integracoes/status` publica limitações e as 4 regras de ouro.
* Segregação por organização: cliente de outra empresa não é listado e retorna 404.

## 5. Teste de interface (17 etapas)
`e2e/fluxo-ui.mjs` — Playwright/Chromium, capturas em `e2e/capturas/`

| # | Etapa | Verificação |
|---|---|---|
| 1 | Login | tela renderiza |
| 2 | Autenticação | redireciona ao painel |
| 3 | Painel | KPIs de clientes, compensações e procurações; aviso de modo demonstração; ranking de atenção; gráficos renderizados |
| 4 | Clientes | ≥ 10 empresas demonstrativas |
| 5 | Ficha do cliente | resumo interpretado, procurações, PER/DCOMP e limites da IA |
| 6 | Compensações | classificações e a situação "sem informação atualizada" |
| 7 | Detalhe de PER/DCOMP | histórico de evolução e registro manual |
| 8 | Procurações | KPIs de semáforo, aviso de não presunção e indicadores coloridos |
| 9 | Situação fiscal | explicação de snapshot e colunas de comparação |
| 10 | Alerta | "Por que este alerta foi gerado", evidências e data da consulta |
| 11 | Monitoramento | simulador, regras e execuções |
| 12 | Execução pela interface | mensagem de sucesso com contadores |
| 13 | Fontes de dados | limitações declaradas, Integra Contador, regras de ouro |
| 14 | Auditoria | registros de login e monitoramento |
| 15 | Importação | assistente e histórico |
| 16 | Importação da planilha de teste | mapeamento de CNPJ, 1 linha com erro e 1 duplicada sinalizadas |
| 17 | Console | nenhum erro de JavaScript em todo o fluxo |

## 6. Carga demonstrativa verificada

Executando `python -m scripts.seed --reset`:

| Item | Quantidade |
|---|---|
| Clientes (CNPJs fictícios válidos) | 10 |
| Procurações | 10 |
| PER/DCOMP | 13 |
| Snapshots de situação fiscal | 27 |
| Comparativos entre consultas | 12 |
| Alertas gerados | 23 |
| Execuções de monitoramento | 3 (D−14, D−7 e hoje) |

Cobertura de cenários na massa: cliente regular com compensação homologada;
cliente com débitos; procuração vencida; procuração revogada; fonte
indisponível; fonte sem autorização (sem poderes); PER/DCOMP não homologada;
PER/DCOMP com intimação; parcelamento + obrigação acessória + débito suspenso;
cliente nunca consultado. A planilha de teste inclui ainda uma linha com CNPJ
inválido e uma PER/DCOMP duplicada, para exercitar validação e correção.

## 7. Compatibilidade de banco verificada

```
PostgreSQL 16.15 — 53/53 testes, seed completo, 19 tabelas criadas
SQLite  3.x      — 53/53 testes, seed completo
Alembic          — upgrade (20 tabelas) → downgrade (0) → upgrade (20)
```

## 8. Como reproduzir

```bash
cd backend && python3 -m pytest tests/ -v
```

```bash
cd backend && MT_DATABASE_URL="postgresql+psycopg://monitor@127.0.0.1:5432/monitor" python3 -m pytest tests/ -v
```

```bash
cd backend && MT_SCHEDULER_ENABLED=false python3 -m scripts.seed --reset && python3 -m uvicorn app.main:app --port 8000
```

```bash
node e2e/fluxo-ui.mjs http://127.0.0.1:8000
```

## 9. Limitações conhecidas

1. **Nenhuma consulta real à Receita Federal foi executada** — não há contrato,
   certificado nem procuração disponíveis neste ambiente. O que foi testado é a
   mecânica completa (consulta → gravação → comparação → alerta) sobre o conector
   simulador, além do comportamento correto do adaptador oficial quando não
   configurado (`NAO_AUTORIZADO`, nunca "regular").
2. **Mapeamento de resposta do Integra Contador é provisório**: o formato exato
   dos campos só pode ser fechado com acesso ao contrato. Os pontos de ajuste
   estão isolados em duas funções, indicados em `INTEGRACAO_RECEITA_FEDERAL.md`.
3. **E-mail não foi enviado de fato** (sem SMTP no ambiente): o teste cobre o
   registro da notificação e o estado `DESABILITADO` quando o envio está desligado.
4. **Docker não pôde ser executado neste ambiente** (sem daemon disponível); os
   arquivos `Dockerfile`/`docker-compose.yml` foram escritos, mas a subida do
   stack completo em contêineres ainda precisa ser validada na infraestrutura do
   cliente. O PostgreSQL foi validado diretamente, fora de contêiner.
5. Não há ainda teste de carga/performance com volume elevado (milhares de
   clientes × consultas diárias).
