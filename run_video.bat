@echo off
setlocal enabledelayedexpansion

:: --- Validación de parámetros ---
if "%~2"=="" (
    echo Uso: %~nx0 ruta\al\video.mp4 ruta\de\salida
    exit /b 1
)

set "INPUT_FILE=%~1"
set "OUTPUT_DIR=%~2"

:: --- Comprobaciones ---
if not exist "%INPUT_FILE%" (
    echo Error: El archivo de entrada no existe: %INPUT_FILE%
    exit /b 1
)

if not exist "%OUTPUT_DIR%" (
    echo Error: La carpeta de salida no existe: %OUTPUT_DIR%
    exit /b 1
)

:: --- Rutas absolutas ---
for %%A in ("%INPUT_FILE%") do set "INPUT_FILE_ABS=%%~fA"
for %%A in ("%INPUT_FILE_ABS%") do set "INPUT_DIR_ABS=%%~dpA"
for %%A in ("%OUTPUT_DIR%") do set "OUTPUT_DIR_ABS=%%~fA"

:: Quitar barra final si existe
if "%INPUT_DIR_ABS:~-1%"=="\" set "INPUT_DIR_ABS=%INPUT_DIR_ABS:~0,-1%"
if "%OUTPUT_DIR_ABS:~-1%"=="\" set "OUTPUT_DIR_ABS=%OUTPUT_DIR_ABS:~0,-1%"

:: --- Nombre del archivo ---
for %%A in ("%INPUT_FILE_ABS%") do set "INPUT_BASENAME=%%~nxA"

:: --- Ejecución del contenedor ---
docker run --rm -it --gpus all ^
    -v "%INPUT_DIR_ABS%":/app/inputs ^
    -v "%OUTPUT_DIR_ABS%":/app/outputs ^
    felixmurcia/video-optimizer:cuda ^
    -i "/app/inputs/%INPUT_BASENAME%" ^
    -o "/app/outputs"

endlocal
