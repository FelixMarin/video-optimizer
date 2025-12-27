#!/usr/bin/env bash
set -euo pipefail

echo "🔄 Deteniendo cualquier instancia previa de Ray..."
if command -v ray >/dev/null 2>&1; then
  ray stop || true
else
  echo "Aviso: 'ray' no encontrado en PATH. Asegúrate de activar el entorno o instalar Ray."
fi

echo "🚀 Iniciando Ray como nodo worker con recurso gpu10bit..."
ray start --num-gpus=1 --address=192.168.0.105:6379 --disable-usage-stats

echo "✅ Ray iniciado correctamente en el PC."
read -n1 -s -r -p $'Presione cualquier tecla para continuar...\n'
