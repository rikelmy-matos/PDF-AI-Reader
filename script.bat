@echo off
SETLOCAL

REM Garante que o script está rodando na pasta onde ele está salvo
cd /d "%~dp0"

SET "PYTHON_EXE=C:\Users\Acer\AppData\Local\Programs\Python\Python310\python.exe"
SET "PYTHON_APP_FILE=app.py"
SET "REQUIREMENTS_FILE=requirements.txt"
SET "VENV_DIR=.venv_uv"

echo.
echo ===============================
echo LIMPEZA INICIAL DO VENV
echo ===============================
IF EXIST "%VENV_DIR%" (
    echo Removendo ambiente virtual antigo...
    rmdir /s /q "%VENV_DIR%"
    IF ERRORLEVEL 1 (
        echo ERRO: Nao foi possivel remover o venv.
        PAUSE
        EXIT /B 1
    )
    echo Ambiente virtual removido.
) ELSE (
    echo Nenhum ambiente virtual existente.
)

echo.
echo ===============================
echo Instalando/atualizando uv...
echo ===============================
"%PYTHON_EXE%" -m pip install --upgrade uv
IF ERRORLEVEL 1 (
    echo ERRO ao instalar uv.
    PAUSE
    EXIT /B 1
)

echo.
echo ===============================
echo Criando venv com uv...
echo ===============================
"%PYTHON_EXE%" -m uv venv "%VENV_DIR%"
IF ERRORLEVEL 1 (
    echo ERRO ao criar venv. Verifique permissoes e caminho.
    PAUSE
    EXIT /B 1
)

echo.
echo ===============================
echo Ativando venv...
echo ===============================
CALL "%VENV_DIR%\Scripts\activate.bat"
IF ERRORLEVEL 1 (
    echo ERRO ao ativar venv.
    PAUSE
    EXIT /B 1
)

echo.
echo ===============================
echo Instalando dependencias...
echo ===============================
uv pip install -r "%REQUIREMENTS_FILE%"
IF ERRORLEVEL 1 (
    echo ERRO ao instalar dependencias.
    PAUSE
    EXIT /B 1
)

echo.
echo ===============================
echo Executando app...
echo ===============================
python "%PYTHON_APP_FILE%" "%~1" "%~2"
SET "APP_EXIT_CODE=%ERRORLEVEL%"

:: REMOVEMOS O PAUSE PARA QUE O TERMINAL FECHE AUTOMATICAMENTE
EXIT /B %APP_EXIT_CODE%
ENDLOCAL

deactivate

