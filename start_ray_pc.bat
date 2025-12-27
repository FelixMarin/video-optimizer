@echo off
echo 🔄 Deteniendo cualquier instancia previa de Ray...
ray stop

echo 🚀 Iniciando Ray como nodo worker con recurso gpu10bit...
ray start --num-gpus=1 --address=192.168.0.107:6379 --disable-usage-stats

echo ✅ Ray iniciado correctamente en el PC.
pause
