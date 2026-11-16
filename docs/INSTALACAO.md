# Instalação e configuração

## 1. Requisitos

| Componente | Versão mínima | Observação |
|---|---|---|
| Python | 3.11 (testado em 3.13) | backend |
| Node.js | 20 (testado em 22) | frontend |
| PostgreSQL | 14 (testado em 16) | produção; SQLite serve para desenvolvimento |
| Docker + Compose | 24 | opcional, caminho recomendado para produção |

## 2. Instalação local (desenvolvimento)

### 2.1 Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
```

```bash
pip install -r requirements-dev.txt
```

```bash
export MT_DATABASE_URL="sqlite+pysqlite:///./monitor_tributario.db"
```

```bash
MT_SCHEDULER_ENABLED=false python3 -m scripts.seed --reset
```

```bash
python3 -m uvicorn app.main:app --reload --port 8000
```

A API sobe em `http://localhost:8000`; documentação interativa em `/docs`.

### 2.2 Frontend

```bash
cd frontend && npm install
```

```bash
npm run dev
```

O Vite sobe em `http://localhost:5173` e encaminha `/api` para a porta 8000.

### 2.3 Build integrado (um único processo)

```bash
cd frontend && npm run build
```

Com `frontend/dist` presente, o próprio FastAPI serve a interface em
`http://localhost:8000`, com fallback de rotas do React Router.

## 3. PostgreSQL

```bash
createdb monitor && createuser monitor --pwprompt
```

```bash
export MT_DATABASE_URL="postgresql+psycopg://monitor:SENHA@localhost:5432/monitor"
```

```bash
cd backend && alembic upgrade head
```

```bash
cd backend && MT_SCHEDULER_ENABLED=false python3 -m scripts.seed
```

## 4. Docker Compose (recomendado)

```bash
cp .env.example .env
```

Gere as duas chaves obrigatórias e cole no `.env`:

```bash
python3 -c "import secrets; print('MT_SECRET_KEY=' + secrets.token_urlsafe(48))"
```

```bash
python3 -c "from cryptography.fernet import Fernet; print('MT_FERNET_KEY=' + Fernet.generate_key().decode())"
```

```bash
docker compose up --build -d
```

```bash
docker compose exec backend python -m scripts.seed
```

| Serviço | Endereço |
|---|---|
| Interface | http://localhost:8080 |
| API | http://localhost:8000 |
| Documentação da API | http://localhost:8000/docs |
| PostgreSQL | porta interna 5432 (não exposta) |

O backend roda `alembic upgrade head` antes de iniciar.

## 5. Variáveis de ambiente

Todas usam o prefixo `MT_`. As principais:

| Variável | Padrão | Função |
|---|---|---|
| `MT_DATABASE_URL` | SQLite local | string de conexão |
| `MT_SECRET_KEY` | inseguro (dev) | assinatura dos tokens JWT — **obrigatória em produção** |
| `MT_FERNET_KEY` | derivada da secret | criptografia em repouso — defina em produção |
| `MT_ENVIRONMENT` | `dev` | `dev`/`test`/`staging`/`prod` (em `prod` recusa chave padrão) |
| `MT_ACCESS_TOKEN_MINUTES` | 480 | validade do token |
| `MT_CORS_ORIGINS` | localhost:5173 | origens permitidas (lista JSON) |
| `MT_CONNECTOR_PROCURACAO` / `_COMPENSACAO` / `_SITUACAO_FISCAL` | `simulador` | fonte por domínio |
| `MT_SCHEDULER_ENABLED` | `true` | liga o agendador |
| `MT_MONITORAMENTO_CRON` | `0 6 * * *` | cron padrão quando não há regras |
| `MT_CONSULTA_DESATUALIZADA_DIAS` | 7 | limite de frescor da informação |
| `MT_ALERTA_PROCURACAO_DIAS` | `[30,15,7,0]` | faixas de alerta de vencimento |
| `MT_EMAIL_ENABLED` + `MT_SMTP_*` | desligado | envio de e-mail |
| `MT_LOGIN_MAX_TENTATIVAS` / `MT_LOGIN_BLOQUEIO_MINUTOS` | 5 / 15 | bloqueio temporário contra força bruta |
| `MT_ARQUIVOS_DIR` | `<raiz>/arquivos` | onde ficam os anexos |
| `MT_UPLOAD_MAX_MB` | 25 | tamanho máximo de anexo |
| `MT_INTEGRA_CONTADOR_MODO_HOMOLOGACAO` | `false` | grava respostas brutas para mapeamento |
| `MT_IA_LLM_ENABLED` + `MT_ANTHROPIC_API_KEY` | desligado | redação opcional por LLM |
| `MT_INTEGRA_CONTADOR_*` | desligado | ver `INTEGRACAO_RECEITA_FEDERAL.md` |

## 6. Produção — lista de verificação

- [ ] `MT_ENVIRONMENT=prod`, `MT_DEBUG=false`
- [ ] `MT_SECRET_KEY` e `MT_FERNET_KEY` gerados e guardados em cofre de segredos
- [ ] HTTPS terminando em proxy reverso (HSTS já é enviado pela aplicação)
- [ ] `MT_CORS_ORIGINS` restrito ao domínio real
- [ ] PostgreSQL com senha forte, sem porta pública, backup automatizado e testado
- [ ] Trocar as senhas dos usuários de demonstração ou removê-los
- [ ] Conectores apontando para fontes reais (`manual` ou `integra_contador`);
      **nunca** deixar `simulador` em produção
- [ ] Agendador ativo em **uma única** instância do backend
- [ ] Volume `certificados/` com permissão restrita (0400) e fora do versionamento
- [ ] Volume de anexos (`MT_ARQUIVOS_DIR`) em disco persistente e incluído no backup
- [ ] Backup automatizado **e restauração testada** (`backend/scripts/`, ver OPERACAO.md)
- [ ] Rodar o checklist em *Fontes de dados* → **Prontidão para produção** e zerar os itens críticos
- [ ] Monitorar `/api/health` e o log de execuções

## 7. Problemas comuns

| Sintoma | Causa provável | Solução |
|---|---|---|
| `401` logo após o login | relógio fora de hora ou `MT_SECRET_KEY` alterada | sincronize o horário; relogue |
| `RuntimeError: Defina MT_SECRET_KEY` | `MT_ENVIRONMENT=prod` com chave padrão | gere e configure a chave |
| Planilha não reconhecida | cabeçalho ausente ou formato não suportado | baixe o modelo em Importação → "Baixar modelo" |
| Todos os semáforos cinza | nenhuma consulta executada ainda | rode Monitoramento → Executar |
| Agendador inativo | `MT_SCHEDULER_ENABLED=false` | ligue a variável e reinicie |
| E-mails em `DESABILITADO` | `MT_EMAIL_ENABLED=false` | configure SMTP e ligue a variável |
| Login respondendo 429 | bloqueio por tentativas malsucedidas | aguarde o prazo informado em `Retry-After` ou peça a um ADMIN para redefinir a senha |
| Anexo recusado | extensão fora da lista ou conteúdo incompatível | confira os tipos aceitos em *Documentos* na ficha do cliente |
