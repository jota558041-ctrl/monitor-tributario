#!/usr/bin/env bash
# Restauração do Monitor Tributário.
#
#   ./scripts/restaurar.sh backups/monitor-AAAAMMDD-HHMMSS.dump [banco-destino]
#
# Por segurança, restaura em um banco DIFERENTE do de produção, a menos que
# PERMITIR_SOBRESCREVER=1 seja informado explicitamente.
set -euo pipefail

DUMP="${1:?informe o arquivo .dump}"
DESTINO_BANCO="${2:-monitor_restaurado}"
ARQUIVOS_DIR="${MT_ARQUIVOS_DIR:-./arquivos}"

[[ -f "$DUMP" ]] || { echo "Arquivo não encontrado: $DUMP" >&2; exit 1; }

if [[ -f "$DUMP.sha256" ]]; then
  echo "==> Conferindo integridade"
  (cd "$(dirname "$DUMP")" && sha256sum -c "$(basename "$DUMP").sha256")
fi

if [[ -n "${MT_DATABASE_URL:-}" ]]; then
  URL="${MT_DATABASE_URL#*://}"; URL="${URL#postgresql+psycopg://}"
  CREDENCIAL="${URL%@*}"; RESTO="${URL##*@}"
  export PGUSER="${PGUSER:-${CREDENCIAL%%:*}}"
  if [[ "$CREDENCIAL" == *:* ]]; then export PGPASSWORD="${PGPASSWORD:-${CREDENCIAL#*:}}"; fi
  HOSTPORTA="${RESTO%%/*}"
  export PGHOST="${PGHOST:-${HOSTPORTA%%:*}}"
  [[ "$HOSTPORTA" == *:* ]] && export PGPORT="${PGPORT:-${HOSTPORTA##*:}}"
  BANCO_ATUAL="${RESTO##*/}"
  if [[ "$DESTINO_BANCO" == "$BANCO_ATUAL" && "${PERMITIR_SOBRESCREVER:-0}" != "1" ]]; then
    echo "Recusado: '$DESTINO_BANCO' é o banco em uso. Para sobrescrever mesmo assim," >&2
    echo "execute com PERMITIR_SOBRESCREVER=1." >&2
    exit 2
  fi
fi

echo "==> Recriando o banco $DESTINO_BANCO"
psql -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS \"$DESTINO_BANCO\";" \
                                     -c "CREATE DATABASE \"$DESTINO_BANCO\";" >/dev/null

echo "==> Restaurando $DUMP"
pg_restore --dbname="$DESTINO_BANCO" --no-owner --no-privileges "$DUMP"

ANEXOS="${DUMP/monitor-/anexos-}"; ANEXOS="${ANEXOS%.dump}.tar.gz"
if [[ -f "$ANEXOS" ]]; then
  echo "==> Restaurando anexos de $ANEXOS em $ARQUIVOS_DIR"
  mkdir -p "$(dirname "$ARQUIVOS_DIR")"
  tar -xzf "$ANEXOS" -C "$(dirname "$ARQUIVOS_DIR")"
fi

echo "==> Conferência rápida"
psql -d "$DESTINO_BANCO" -tc "select 'clientes: ' || count(*) from cliente;"
psql -d "$DESTINO_BANCO" -tc "select 'compensacoes: ' || count(*) from compensacao;"
psql -d "$DESTINO_BANCO" -tc "select 'alertas: ' || count(*) from alerta;"
echo "==> Restauração concluída em $DESTINO_BANCO"
