# TrustBPO - Extrator de Notas Fiscais

Sistema para extração automatizada de informações de notas fiscais em PDF.

## Pré-requisitos

1. Python 3.8+
2. Tesseract OCR instalado no sistema
3. Poppler instalado (necessário para pdf2image)

## Instalação

### Instalar Tesseract OCR

#### Windows
1. Baixe o instalador do [Tesseract OCR para Windows](https://github.com/UB-Mannheim/tesseract/wiki)
2. Instale no caminho padrão `C:\Program Files\Tesseract-OCR\`
3. Certifique-se de instalar o pacote de idioma português

#### Linux
```bash
sudo apt-get update
sudo apt-get install tesseract-ocr
sudo apt-get install tesseract-ocr-por  # Português
```

### Instalar Poppler

#### Windows
1. Baixe o Poppler para Windows do [poppler-windows](https://github.com/oschwartz10612/poppler-windows/releases/)
2. Adicione o diretório `bin` ao PATH

#### Linux
```bash
sudo apt-get install poppler-utils
```

### Instalar Dependências Python

```bash
pip install -r requirements.txt
```

## Configuração

### Configurar Caminhos

Antes de executar o sistema, é necessário configurar os caminhos corretos no arquivo `app.py`:

1. **Caminho do Tesseract OCR**: Linha 386
   ```python
   pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
   ```

2. **Pasta dos PDFs**: Linha 388
   ```python
   pasta_pdf = r"C:\Repos\Poc\TrustBPO\Faturas"
   ```

3. **Pasta Raiz do Projeto**: Linha 389
   ```python
   pasta_raiz = r"C:\Repos\Poc\TrustBPO"
   ```

**Importante**: Ajuste estes caminhos de acordo com a sua instalação e estrutura de pastas.

## Uso

1. Coloque os arquivos PDF na pasta configurada em `pasta_pdf`
2. Execute o script:

```bash
python app.py
```

O script processará todos os PDFs na pasta e gerará um arquivo CSV com as informações extraídas na pasta raiz do projeto.
