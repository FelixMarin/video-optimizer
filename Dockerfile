FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instala dependencias del sistema necesarias para procesamiento de vídeo y compilación
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       gcc \
       ffmpeg \
       git \
       ca-certificates \
       libffi-dev \
       libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia solo requirements primero para usar cache de Docker
COPY requirements.txt /app/

RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# Copia el resto del proyecto
COPY . /app

# Directorios por defecto para montaje de datos
RUN mkdir -p /app/inputs /app/outputs

# Por defecto ejecuta el módulo CLI; puede pasarse argumentos al contenedor
ENTRYPOINT ["python", "-m", "optimize_video"]
CMD ["-h"]
