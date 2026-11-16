# Relatório de testes

**Data da execução:** 16/11/2026 (atualizado após os módulos de CRUD, relatórios, documentos e produção)
**Ambiente:** Python 3.13.18 · Node 22.23.4 · PostgreSQL 16.15 · Chromium (Playwright)

## 1. Resumo

| Suíte | Itens | Resultado | Tempo |
|---|---|---|---|
| Backend — SQLite | 85 testes | **85 passaram** | 87 s |
| Backend — PostgreSQL 16 | 85 testes | **85 passaram** | 87 s |
| Interface — Playwright | 25 etapas | **25 passaram** | ~90 s |
| Migrações Alembic (0001→0003) | upgrade → downgrade → upgrade | **OK** (22 tabelas, reversível) | — |
| Backup e restauração | ciclo completo com perda simulada | **OK** (dados recompostos) | — |
| Build do frontend | `tsc -b && vite build` | **OK**, sem erro de tipo | 3,4 s |
| Lint do backend | `ruff check` | **OK**, sem apontamentos | — |
| Carga demonstrativa | `scripts.seed --reset` | **OK** em SQLite e PostgreSQL | — |

Distribuição dos 85 testes: validação (23), regras de negócio (19), API e
permissões (12), documentos (12), produção e hardening (7), CRUD (6) e
relatórios (6).

Nenhuma falha pendente. Nenhum erro de console no navegador durante o fluxo.

## 1.1 Defeitos encontrados e corrigidos durante os testes

Os testes não serviram só de carimbo — três defeitos reais apareceram e foram
corrigidos:

| # | Defeito | Como apareceu | Correção |
|---|---|---|---|
| 1 | Valores `Decimal` quebravam a gravação de payloads JSON | teste de registro manual de PER/DCOMP falhou com `TypeError` | conversor `app/core/serial.py` aplicado em todos os payloads |
| 2 | Comparativos redundantes de R$ 0,00 a cada execução sem mudança | inspeção visual da ficha do cliente após várias execuções | comparativo só é gravado quando o conteúdo muda (há teste cobrindo) |
| 3 | Banco de desenvolvimento desatualizado em relação ao modelo derrubava o login (HTTP 500) | o fluxo de interface falhou logo no login após a migração 0003 | base recriada; o teste de interface passou a abortar cedo em falha essencial, em vez de arrastar 25 etapas |

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

## 4.1 Testes de CRUD e permissões (6)
`backend/tests/test_crud.py`

| Teste | Garante |
|---|---|
| `editar_cliente_registra_historico` | alteração cadastral grava histórico campo a campo |
| `procuracao_manual_nao_fica_validada` | lançamento manual nasce `DESCONHECIDA`/**CINZA** |
| `editar_procuracao_nao_valida_por_fonte` | editar à mão não marca `validada_por_fonte` |
| `editar_compensacao_nao_muda_situacao_e_gera_evento` | situação não muda por edição; evento `EDICAO_MANUAL` é criado |
| `exclusao_restrita_a_admin` | analista recebe 403; admin exclui e a ação fica auditada |
| `gestao_de_usuarios` | criação, senha fraca recusada, desativação bloqueia login, troca de perfil |

## 4.2 Testes de relatórios (6)
`backend/tests/test_relatorios.py`

* Carteira em Excel com as abas Clientes, Procurações, PER-DCOMP, Situação
  fiscal e **Procedência** — esta última contendo o aviso de que transmissão
  não equivale a homologação e o alerta de fonte em modo simulador.
* PDF do cliente íntegro (`%PDF-`), com mais de 2 KB de conteúdo.
* PDF de cliente de outra organização retorna 404.
* Relação de alertas traz as colunas "Por que foi gerado" e "Consulta da evidência".
* Extrato de consultas com cabeçalho e linhas.
* Geração de relatório fica registrada na auditoria; perfil AUDITOR pode exportar.

## 4.3 Testes de documentos (12)
`backend/tests/test_documentos.py`

| Teste | Garante |
|---|---|
| `upload_grava_metadados_e_arquivo` | categoria, tipo, tamanho e SHA-256 registrados |
| `download_devolve_conteudo_e_registra_auditoria` | conteúdo idêntico e evento `DOCUMENTO_VISUALIZADO` |
| `arquivos_recusados` (3 casos) | `.exe` recusado, `.pdf` falso recusado, arquivo vazio recusado |
| `tamanho_maximo` | limite configurável respeitado |
| `documento_restrito_exige_admin` | analista vê na lista mas recebe 403; tentativa é auditada |
| `duplicidade_avisa` | conteúdo idêntico é sinalizado pelo hash |
| `exclusao_apaga_arquivo_e_exige_admin` | analista 403; admin exclui e o arquivo some do disco |
| `integridade_detecta_arquivo_adulterado` | arquivo alterado no disco → 410, não entrega silenciosa |
| `segregacao_por_organizacao` | documento de outra empresa não é listado nem baixado |
| `vinculo_com_perdcomp` | anexo associado a uma PER/DCOMP específica |

## 4.4 Testes de produção e hardening (7)
`backend/tests/test_producao.py`

| Teste | Garante |
|---|---|
| `bloqueio_apos_tentativas_falhas` | 5 falhas → 429 com `Retry-After`; **nem a senha correta entra** durante o bloqueio; expirado o prazo, acesso e contadores normalizam |
| `bloqueio_registrado_na_auditoria` | evento `LOGIN_BLOQUEADO` gravado |
| `prontidao_aponta_pendencias_do_ambiente` | checklist acusa fonte em simulador como crítico |
| `prontidao_restrita_a_admin` | analista recebe 403 |
| `amostras_vazias_por_padrao` | modo homologação desligado de fábrica |
| `modo_homologacao_captura_amostra` | falha de chamada vira amostra com erro e `INDISPONIVEL` — nunca "regular" |
| `scripts_de_backup_existem_e_sao_executaveis` | scripts presentes, com `set -euo pipefail`, hash e trava de sobrescrita |

## 5. Teste de interface (25 etapas)
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
| 17 | Cadastro de cliente pela tela | cliente novo aparece na lista |
| 18 | CNPJ inválido na tela | recusado com mensagem clara |
| 19 | Procuração manual | entra como **CINZA**/desconhecida |
| 20 | PER/DCOMP manual | entra como "sem informação atualizada" |
| 21 | Gestão de usuários | lista e ação de redefinir senha (apenas ADMIN) |
| 22 | Exportar carteira | download `.xlsx` concluído |
| 23 | Posição em PDF | arquivo baixado começa com `%PDF-` |
| 24 | Anexo de documento | upload, hash exibido e download de volta com o mesmo nome |
| 25 | Console | nenhum erro de JavaScript em todo o fluxo |

O fluxo é **idempotente**: gera CNPJ válido e identificadores únicos a cada
execução, podendo rodar quantas vezes for preciso contra a mesma base. Etapas
essenciais (tela inicial e login) interrompem o fluxo quando falham.

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

## 6.1 Backup e restauração (ciclo completo)

| Passo | Resultado |
|---|---|
| Base com 10 clientes, 13 PER/DCOMP, 22 alertas e anexos | — |
| `scripts/backup.sh` | dump + anexos + hashes gerados |
| `sha256sum -c` | OK nos dois arquivos |
| `TRUNCATE cliente CASCADE` (perda simulada) | 0 clientes |
| `scripts/restaurar.sh` em banco separado | 10 clientes, 13 PER/DCOMP, 22 alertas |
| Restauração sobre o banco em uso, sem confirmação | **recusada** (trava funcionou) |
| Restauração com `PERMITIR_SOBRESCREVER=1` | base recomposta |

## 7. Compatibilidade de banco verificada

```
PostgreSQL 16.15 — 85/85 testes, seed completo, 21 tabelas criadas
SQLite  3.x      — 85/85 testes, seed completo
Alembic          — 0001 → 0002 → 0003, upgrade (22 tabelas) → downgrade → upgrade
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
6. O **modo homologação** foi exercitado apenas com falha de chamada (sem
   contrato ativo): comprova que o erro vira amostra e resulta em
   `INDISPONIVEL`, mas o formato real da resposta só poderá ser conferido com
   acesso ao contrato.
7. Bancos criados antes de uma migração precisam ser migrados (`alembic upgrade
   head`) ou recriados — foi o que causou o defeito nº 3 da seção 1.1 no
   ambiente de desenvolvimento.
