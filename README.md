# Extrator de Notas Fiscais

Sistema para extração automatizada de informações de notas fiscais em arquivos PDF.

## Pré‑requisitos

- Python 3.8 ou superior  
- Tesseract OCR instalado no sistema  
- Poppler instalado (necessário para o uso do `pdf2image`)

## Instalação

### Instalar Tesseract OCR

#### Windows
1. Baixe o instalador do [Tesseract OCR para Windows](https://github.com/UB-Mannheim/tesseract/wiki)  
2. Instale no caminho padrão, por exemplo:  
   `C:\Program Files\Tesseract-OCR\`  
3. Certifique-se de instalar também o pacote de idioma português.

#### Linux
sudo apt-get update
sudo apt-get install tesseract-ocr
sudo apt-get install tesseract-ocr-por  # Suporte ao idioma português


#### Instalar Poppler
Baixe o Poppler para Windows em poppler-windows

Adicione o diretório bin do Poppler à variável de ambiente PATH

#### Linux
sudo apt-get install poppler-utils
Instalar Dependências Python
bash
Copiar
Editar
pip install -r requirements.txt
Configuração
Antes de executar o sistema, abra o arquivo app.py e ajuste os caminhos conforme a sua máquina:

#### Caminho do Tesseract OCR:

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
Pasta onde estão os PDFs a serem processados:

pasta_pdf = r"C:\Caminho\Para\Seus\PDFs"
Pasta raiz do projeto:

pasta_raiz = r"C:\Caminho\Para\O\Projeto"
Importante: Ajuste esses caminhos de acordo com a estrutura do seu ambiente.

#### Uso
Coloque os arquivos PDF na pasta configurada em pasta_pdf.

#### Execute o script:
python app.py