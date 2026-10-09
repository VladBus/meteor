@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1

set "PROJECT_DIR=%~dp0"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
set "PYTHON_EXE=%PROJECT_DIR%\.venv\Scripts\python.exe"
set "MAIN_SCRIPT=%PROJECT_DIR%\main.py"
set "LOG_DIR=%PROJECT_DIR%\logs"
set "BATCH_LOG=%LOG_DIR%\batch_startup.log"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1

echo ==================================================>> "%BATCH_LOG%"
echo [%date% %time%] Запуск meteor>> "%BATCH_LOG%"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Не найден интерпретатор: %PYTHON_EXE%>> "%BATCH_LOG%"
    echo Создайте .venv и установите requirements.txt.
    exit /b 2
)

if not exist "%MAIN_SCRIPT%" (
    echo [ERROR] Не найден файл: %MAIN_SCRIPT%>> "%BATCH_LOG%"
    exit /b 2
)

cd /d "%PROJECT_DIR%"
"%PYTHON_EXE%" "%MAIN_SCRIPT%" >> "%BATCH_LOG%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"

echo [%date% %time%] Завершение meteor, код=%EXIT_CODE%>> "%BATCH_LOG%"
exit /b %EXIT_CODE%
