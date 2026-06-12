@echo off
echo Criando ambiente virtual...
python -m venv .venv
call .venv\Scripts\activate
echo Instalando dependencias...
pip install -r requirements.txt
playwright install chromium
if not exist .env copy .env.example .env
if not exist config.yaml copy config.example.yaml config.yaml
echo.
echo Pronto. Agora edite os arquivos .env e config.yaml.
echo Para testar: python -m app.main --once
pause
