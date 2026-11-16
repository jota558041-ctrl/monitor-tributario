# Operação: backup, restauração e prontidão para produção

## 1. Backup

O script `backend/scripts/backup.sh` salva **banco e anexos** e grava um
`.sha256` de cada arquivo para conferência posterior.

```bash
cd backend && MT_DATABASE_URL="postgresql+psycopg://monitor:SENHA@localhost:5432/monitor" ./scripts/backup.sh /caminho/para/backups
```

| Variável | Padrão | Função |
|---|---|---|
| `MT_DATABASE_URL` | — | conexão (também aceita as variáveis `PG*`) |
| `MT_ARQUIVOS_DIR` | `./arquivos` | diretório dos anexos |
| `BACKUP_DIR` | `./backups` | destino, se não vier por argumento |
| `RETENCAO_DIAS` | `30` | expurgo automático dos backups antigos |

Saída de cada execução:

```
monitor-AAAAMMDD-HHMMSS.dump          # pg_dump formato custom, comprimido
monitor-AAAAMMDD-HHMMSS.dump.sha256
anexos-AAAAMMDD-HHMMSS.tar.gz         # quando há anexos
anexos-AAAAMMDD-HHMMSS.tar.gz.sha256
```

Agendamento sugerido (diário, 2h da manhã):

```bash
0 2 * * * cd /opt/monitor-tributario/backend && ./scripts/backup.sh /var/backups/monitor >> /var/log/monitor-backup.log 2>&1
```

Com Docker Compose:

```bash
docker compose exec -T db pg_dump -U monitor -Fc monitor > backups/monitor-$(date +%F).dump
```

## 2. Restauração

```bash
cd backend && ./scripts/restaurar.sh /var/backups/monitor/monitor-20261116-183028.dump monitor_restaurado
```

O script confere o SHA-256, recria o banco de destino, restaura o dump,
restaura os anexos correspondentes e mostra uma contagem de conferência.

**Proteção contra engano:** restaurar sobre o banco que está em uso é recusado.
Para sobrescrever conscientemente:

```bash
PERMITIR_SOBRESCREVER=1 ./scripts/restaurar.sh backups/monitor-20261116-183028.dump monitor
```

### Teste de restauração realizado

O ciclo foi exercitado de ponta a ponta contra PostgreSQL 16:

| Passo | Resultado |
|---|---|
| Base com 10 clientes, 13 PER/DCOMP, 22 alertas e anexos | — |
| `backup.sh` | dump + anexos + hashes gerados |
| `sha256sum -c` | OK nos dois arquivos |
| `TRUNCATE cliente CASCADE` (perda simulada) | 0 clientes |
| `restaurar.sh` em banco separado | 10 clientes, 13 PER/DCOMP, 22 alertas |
| Restauração sobre o banco em uso, sem a variável | **recusada** |
| Restauração com `PERMITIR_SOBRESCREVER=1` | base de produção recomposta |

**Repita esse teste periodicamente.** Backup que nunca foi restaurado não é
backup — é esperança.

## 3. Checklist de prontidão para produção

A própria aplicação verifica a configuração: menu **Fontes de dados** (perfil
ADMIN) ou `GET /api/sistema/prontidao`. Os itens avaliados:

| Item | Critério |
|---|---|
| Ambiente | `MT_ENVIRONMENT=prod` |
| Modo debug | `MT_DEBUG=false` |
| Chave de assinatura (JWT) | `MT_SECRET_KEY` diferente da padrão |
| Chave de criptografia | `MT_FERNET_KEY` definida |
| Banco de dados | PostgreSQL (não SQLite) |
| Fontes de dados | nenhuma em `simulador` |
| Modo homologação | desligado |
| CORS | sem `localhost` em produção |
| Usuários de demonstração | nenhum ativo |
| Administradores ativos | entre 1 e 3 |
| Força bruta | bloqueio configurado |
| Agendador | ativo |
| E-mail | SMTP configurado |
| Retenção | ao menos 5 anos |

A verificação cobre a **configuração da aplicação**. TLS, firewall, isolamento
de rede do banco e a execução efetiva do backup dependem da infraestrutura e
precisam ser conferidos à parte.

## 4. Rotina sugerida

| Frequência | Tarefa |
|---|---|
| Diária | conferir execuções do monitoramento e alertas críticos |
| Diária | backup automático e verificação do log |
| Semanal | revisar alertas de procuração vencendo nos próximos 30 dias |
| Mensal | restaurar um backup em banco separado e conferir as contagens |
| Trimestral | revisar perfis de acesso, usuários ativos e procurações vigentes |
| Trimestral | reler a trilha de auditoria em busca de acessos fora do padrão |
| Anual | revisar política de retenção frente aos prazos fiscais |

## 5. Monitorar a própria aplicação

```bash
curl -fsS https://seu-dominio/api/health
```

Resposta saudável: `{"status":"ok","banco":"ok",...}`. Monitore também:

* `GET /api/monitoramento/execucoes` — execuções com `CONCLUIDA_COM_FALHAS`
  recorrentes indicam fonte instável ou procuração vencida;
* volume de alertas do tipo `FONTE_INDISPONIVEL`;
* crescimento do diretório de anexos e do banco frente à política de retenção.
