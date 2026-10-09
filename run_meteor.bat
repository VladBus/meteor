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

>> "%BATCH_LOG%" echo ==================================================
>> "%BATCH_LOG%" echo [%date% %time%] Запуск meteor

if not exist "%PYTHON_EXE%" (
    >> "%BATCH_LOG%" echo [ERROR] Не найден интерпретатор: %PYTHON_EXE%
    echo [ERROR] Не найден интерпретатор: %PYTHON_EXE%
    echo Создайте .venv и установите requirements.txt.
    exit /b 2
)

if not exist "%MAIN_SCRIPT%" (
    >> "%BATCH_LOG%" echo [ERROR] Не найден файл: %MAIN_SCRIPT%
    echo [ERROR] Не найден файл: %MAIN_SCRIPT%
    exit /b 2
)

cd /d "%PROJECT_DIR%"
"%PYTHON_EXE%" "%MAIN_SCRIPT%" >> "%BATCH_LOG%" 2>&1

rem Не полагаемся на переменную окружения ERRORLEVEL: извлекаем статус
rem через условие CMD и затем записываем его в журнал и консоль.
if errorlevel 2 (
    set "EXIT_CODE=2"
) else if errorlevel 1 (
    set "EXIT_CODE=1"
) else (
    set "EXIT_CODE=0"
)

>> "%BATCH_LOG%" echo [%date% %time%] Завершение meteor, код=%EXIT_CODE%
echo [%date% %time%] Завершение meteor, код=%EXIT_CODE%
exit /b %EXIT_CODE%
