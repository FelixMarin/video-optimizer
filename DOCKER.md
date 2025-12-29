# Docker — video-optimizer

Instrucciones para crear las imágenes Docker, subirlas a Docker Hub, descargarlas y ejecutar contenedores.

## Build (local)
Desde la raíz del repo construye las imágenes usando los Dockerfile específicos:

```bash
# Jetson (imagen optimizada para dispositivos Jetson)
docker build -f Dockerfile.jetson -t video-optimizer:jetson .

# CUDA (PC/servidor con drivers NVIDIA + Docker >= 19.03)
docker build -f Dockerfile.cuda -t video-optimizer:cuda .
```

Nota: en comandos previos se observó un `video-optimezer:latest` (typo). Recomiendo usar nombres consistentes como `video-optimizer:jetson` y `video-optimizer:cuda` o `:latest` según prefieras.

## Tag y push a Docker Hub
Reemplaza `<DOCKERHUB_USER>` por el usuario de Docker Hub.

```bash
# Etiquetar para Docker Hub
docker tag video-optimizer:jetson <DOCKERHUB_USER>/video-optimizer:jetson
docker tag video-optimizer:cuda <DOCKERHUB_USER>/video-optimizer:cuda

# Login y push
docker login
docker push <DOCKERHUB_USER>/video-optimizer:jetson
docker push <DOCKERHUB_USER>/video-optimizer:cuda
```

## Descargar (pull)

```bash
docker pull <DOCKERHUB_USER>/video-optimizer:jetson
docker pull <DOCKERHUB_USER>/video-optimizer:cuda
```

## Ejecutar contenedores (ejemplos)

```bash
# Ejecutar (sin GPU) - expone el servidor Flask en el puerto 5000
docker run --rm -p 5000:5000 \
  -v $(pwd)/uploads:/app/uploads \
  -v $(pwd)/outputs:/app/outputs \
  <DOCKERHUB_USER>/video-optimizer:jetson

# Ejecutar en host con soporte NVIDIA (CUDA) - usa GPUs
docker run --gpus all --rm -p 5000:5000 \
  -v $(pwd)/uploads:/app/uploads \
  -v $(pwd)/outputs:/app/outputs \
  <DOCKERHUB_USER>/video-optimizer:cuda

# En Jetson (si el runtime usa nvidia-container-runtime)
docker run --runtime nvidia --rm -p 5000:5000 \
  -v $(pwd)/uploads:/app/uploads \
  -v $(pwd)/outputs:/app/outputs \
  <DOCKERHUB_USER>/video-optimizer:jetson
```

## Notas rápidas
- Si el host usa Docker >= 19.03 con el soporte `--gpus`, usa `--gpus all` para exponer GPUs al contenedor.
- En Jetson puede ser necesario usar `--runtime nvidia` o la imagen construida específicamente para Jetson; ajusta permisos y drivers según la plataforma.
- Monta `uploads/` y `outputs/` para que los ficheros procesados sean persistentes en el host.
- Si quieres que la imagen por defecto en Docker Hub sea `latest`, añade también el tag `:latest` antes de pushear.

## Ejemplo rápido de push con tag `latest`

```bash
docker tag video-optimizer:cuda <DOCKERHUB_USER>/video-optimizer:latest
docker push <DOCKERHUB_USER>/video-optimizer:latest
```
```bash
### CUDA
docker compose -f docker-compose.cuda.yml build 
docker compose -f docker-compose.cuda.yml run app python server-gpu.py
```
```bash
### JETSON
docker compose -f docker-compose.jetson.yml build
docker compose -f docker-compose.jetson.yml run app python server-gpu-jetson.py
```
## Ejecutar servidores con

```bash
./run_server.sh server-gpu-jetson
./run_server.sh server-gpu
./run_server.sh server
./run_server.sh server-gpu-ray
```
### Ejemplo real
```bash
./run_server.sh server-gpu-jetson
```

### Esto ejecuta
```bash
docker compose -f docker-compose.jetson.yml run --rm app python server-gpu-jetson.py
```