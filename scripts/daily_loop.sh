#!/bin/sh
# Substitui o cron clássico (evita o problema de variáveis de ambiente não chegarem
# ao cron dentro do container). Roda em loop, dormindo até o próximo horário alvo.
set -e

HORA_ALVO="${INGESTAO_HORA:-07:00}"

while true; do
    agora_epoch=$(date +%s)
    alvo_epoch=$(date -d "$HORA_ALVO" +%s)

    if [ "$agora_epoch" -ge "$alvo_epoch" ]; then
        alvo_epoch=$(date -d "tomorrow $HORA_ALVO" +%s)
    fi

    espera=$((alvo_epoch - agora_epoch))
    echo "[cron-loop] Próxima ingestão diária: $(date -d @"$alvo_epoch") (em ${espera}s)"
    sleep "$espera"

    echo "[cron-loop] Rodando 'python -m app.cli run-daily'..."
    python -m app.cli run-daily || echo "[cron-loop] ATENÇÃO: run-daily terminou com erro (veja acima). Tentando de novo amanhã."
done
