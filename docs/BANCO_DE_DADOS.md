# Banco de dados

PostgreSQL 16 em produção; SQLite é suportado para desenvolvimento e testes
(mesmos modelos, sem recurso exclusivo de um dialeto). Esquema versionado com
Alembic — revisão inicial `0001_inicial`, aplicada e revertida com sucesso.

## Mapa das 19 tabelas

### Identidade e governança
| Tabela | Função | Pontos relevantes |
|---|---|---|
| `organizacao` | Tenant (escritório) | toda entidade de negócio referencia `organizacao_id` |
| `usuario` | Acesso | `senha_hash` bcrypt, `perfil` ADMIN/ANALISTA/AUDITOR, único por (org, e-mail) |
| `audit_log` | Trilha de auditoria | ação, entidade, usuário, IP, detalhe JSON, data |
| `credencial_integracao` | Credenciais de fontes | `consumer_key`, `consumer_secret` e senha de certificado **cifrados** (Fernet) |

### Cadastro
| Tabela | Função | Pontos relevantes |
|---|---|---|
| `cliente` | Carteira | único por (org, CNPJ); guarda data da última consulta de cada domínio |
| `cliente_historico` | Histórico cadastral | campo, valor anterior, valor novo, origem, autor |
| `importacao` | Lote de importação | mapeamento de colunas, colunas ignoradas, resumo, status |
| `importacao_linha` | Staging linha a linha | dados brutos, normalizados, erros, avisos, ação, seleção |

### Procurações
| Tabela | Função | Pontos relevantes |
|---|---|---|
| `procuracao` | Procuração eletrônica | `situacao` (sistema) **separada** de `situacao_declarada` (planilha); `validada_por_fonte`; `disponibilidade` |
| `procuracao_consulta` | Histórico de consultas | toda tentativa, inclusive as que falharam, com payload e hash |

### Compensações
| Tabela | Função | Pontos relevantes |
|---|---|---|
| `compensacao` | PER/DCOMP | valores em `numeric(18,2)`; despacho, intimação, prazo, processo; situação em 9 estados |
| `compensacao_evento` | Linha do tempo | cadastro, consulta e mudança de situação, com `de → para`, origem e hash |

### Situação fiscal
| Tabela | Função | Pontos relevantes |
|---|---|---|
| `situacao_fiscal_snapshot` | Fotografia por consulta | **imutável**; totais por categoria; `pendencias` em JSON; `hash_conteudo` |
| `situacao_fiscal_comparativo` | Diferença entre snapshots | novos, baixados, remanescentes, alterados + ressalva de causalidade |

### Monitoramento e alertas
| Tabela | Função | Pontos relevantes |
|---|---|---|
| `regra_monitoramento` | Agendamento | cron, tipo, criticidade mínima, escopo de clientes, canais, destinatários |
| `execucao_monitoramento` | Resultado de cada rodada | OK / indisponíveis / não autorizadas / mudanças / alertas + detalhe JSON |
| `alerta` | Ocorrência | criticidade, explicação, `evidencias` JSON, status, `dedup_key` único por organização |
| `notificacao` | Entrega | canal, destinatário, status, assunto, corpo, erro |
| `estado_simulado` | "Mundo fiscal" fictício | **somente para testes**; alimenta o conector simulador |

## Relacionamentos essenciais

```
organizacao 1─┬─N usuario
              ├─N cliente ─┬─N procuracao ──N procuracao_consulta
              │            ├─N compensacao ──N compensacao_evento
              │            ├─N situacao_fiscal_snapshot
              │            ├─N situacao_fiscal_comparativo
              │            ├─N cliente_historico
              │            └─1 estado_simulado (ambiente de teste)
              ├─N importacao ──N importacao_linha
              ├─N regra_monitoramento ──N execucao_monitoramento
              ├─N alerta ──N notificacao
              └─N credencial_integracao
```

Um CNPJ pode ter **várias** PER/DCOMP e **várias** procurações — exigência do
enunciado, atendida pelas relações 1:N acima.

## Convenções

* **Chaves primárias**: `varchar(32)` com UUID4 hexadecimal (portável, sem
  extensão no PostgreSQL, sem colisão entre ambientes).
* **Dinheiro**: `numeric(18,2)` — nunca ponto flutuante.
* **Datas**: `date` para competências e validades; `timestamptz` para consultas
  e auditoria (sempre em UTC; a interface converte).
* **JSON**: listas de pendências, evidências e payloads brutos — flexíveis por
  natureza, pois dependem do formato da fonte.
* **Exclusão**: cascata a partir de `cliente` e `organizacao`; `audit_log` nunca
  é apagado por cascata (retenção própria).

## Índices

Além das PKs e FKs: `(organizacao_id, cnpj)` único em `cliente`;
`(organizacao_id, situacao_compensacao)` e `(organizacao_id, numero_perdcomp)`
em `compensacao`; `(cliente_id, consultado_em)` em `situacao_fiscal_snapshot`;
`(organizacao_id, status)` em `alerta`; `(organizacao_id, dedup_key)` único em
`alerta`; `(organizacao_id, created_at)` e `(entidade, entidade_id)` em
`audit_log`; data de vencimento em `procuracao`.

## Migrações

```bash
cd backend
alembic upgrade head          # aplica
alembic downgrade base        # reverte tudo
alembic revision --autogenerate -m "descrição"   # nova revisão
```

A URL vem de `MT_DATABASE_URL` (o `alembic.ini` não guarda credencial).
Em SQLite, `render_as_batch` é ativado automaticamente para permitir `ALTER`.

## Backup e retenção

```bash
docker compose exec db pg_dump -U monitor -Fc monitor > backups/monitor-$(date +%F).dump
docker compose exec -T db pg_restore -U monitor -d monitor --clean < backups/arquivo.dump
```

Parâmetros de retenção (dias): `MT_RETENCAO_CONSULTAS_DIAS` (padrão 1825) e
`MT_RETENCAO_AUDITORIA_DIAS` (padrão 1825). A rotina de expurgo deve respeitar
prazos legais de guarda fiscal antes de remover qualquer histórico.
