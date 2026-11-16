#!/usr/bin/env bash
# Backup lógico do Monitor Tributário: banco + anexos.
#
#   ./scripts/backup.sh [diretorio-destino]
#
# Lê a conexão de MT_DATABASE_URL (ou das variáveis PG*). Mantém os últimos
# RETENCAO_DIAS backups e grava um .sha256 para conferência de integridade.
set -euo pipefail

DESTINO="${1:-${BACKUP_DIR:-./backups}}"
RETENCAO_DIAS="${RETENCAO_DIAS:-30}"
ARQUIVOS_DIR="${MT_ARQUIVOS_DIR:-./arquivos}"
CARIMBO="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$DESTINO"

# --- conexão -----------------------------------------------------------------
# Converte postgresql+psycopg://usuario:senha@host:porta/banco em variáveis PG*.
if [[ -n "${MT_DATABASE_URL:-}" ]]; then
  URL="${MT_DATABASE_URL#*://}"
  URL="${URL#postgresql+psycopg://}"
  CREDENCIAL="${URL%@*}"; RESTO="${URL##*@}"
  export PGUSER="${PGUSER:-${CREDENCIAL%%:*}}"
  if [[ "$CREDENCIAL" == *:* ]]; then export PGPASSWORD="${PGPASSWORD:-${CREDENCIAL#*:}}"; fi
  HOSTPORTA="${RESTO%%/*}"
  export PGHOST="${PGHOST:-${HOSTPORTA%%:*}}"
  [[ "$HOSTPORTA" == *:* ]] && export PGPORT="${PGPORT:-${HOSTPORTA##*:}}"
  export PGDATABASE="${PGDATABASE:-${RESTO##*/}}"
fi
: "${PGDATABASE:?defina MT_DATABASE_URL ou PGDATABASE}"

DUMP="$DESTINO/monitor-$CARIMBO.dump"
echo "==> Banco $PGDATABASE em ${PGHOST:-local}:${PGPORT:-5432} -> $DUMP"
pg_dump --format=custom --compress=6 --file="$DUMP"
sha256sum "$DUMP" > "$DUMP.sha256"

# --- anexos ------------------------------------------------------------------
if [[ -d "$ARQUIVOS_DIR" ]] && [[ -n "$(ls -A "$ARQUIVOS_DIR" 2>/dev/null)" ]]; then
  ANEXOS="$DESTINO/anexos-$CARIMBO.tar.gz"
  echo "==> Anexos de $ARQUIVOS_DIR -> $ANEXOS"
  tar -czf "$ANEXOS" -C "$(dirname "$ARQUIVOS_DIR")" "$(basename "$ARQUIVOS_DIR")"
  sha256sum "$ANEXOS" > "$ANEXOS.sha256"
else
  echo "==> Sem anexos para incluir ($ARQUIVOS_DIR vazio ou inexistente)"
fi

# --- expurgo -----------------------------------------------------------------
echo "==> Removendo backups com mais de $RETENCAO_DIAS dia(s)"
find "$DESTINO" -maxdepth 1 -name 'monitor-*.dump*' -mtime "+$RETENCAO_DIAS" -delete
find "$DESTINO" -maxdepth 1 -name 'anexos-*.tar.gz*' -mtime "+$RETENCAO_DIAS" -delete

echo "==> Concluído. Confira com: sha256sum -c $DUMP.sha256"
echo "    Backup NÃO testado não é backup: restaure periodicamente com restaurar.sh."
