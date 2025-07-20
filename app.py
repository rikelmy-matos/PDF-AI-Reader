import csv
import glob
import io
import json
import logging
import math
import os
import random
import re
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pdf2image
import pdfplumber
import pytesseract
import requests
from dotenv import load_dotenv
from PIL import Image

# Cria pasta de logs se não existir
os.makedirs("logs", exist_ok=True)

# Nome do arquivo de log com data/hora
log_filename = f"logs/processamento_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Configuração do logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_filename, encoding="utf-8-sig"),
        logging.StreamHandler(sys.stdout)  # também mostra no terminal
    ]
)

# Exemplo de uso:
logging.info("Iniciando processamento...")

# Carrega as variáveis do arquivo ini.env
load_dotenv("ini.env")

POPPLER_PATH = os.getenv("POPPLER_PATH", r"C:\poppler-24.08.0\Library\bin")

# TESSERACT_PATH
tesseract_path = os.getenv("TESSERACT_PATH", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
pytesseract.pytesseract.tesseract_cmd = tesseract_path

# DeepSeek API Key
DEEPSEEK_API_KEY_HARDCODED = os.getenv("DEEPSEEK_API_KEY", "")

# Pastas
pasta_pdf = os.getenv("PASTA_PDF", r"H:\Notas")
pasta_raiz = os.getenv("PASTA_SAIDA", r"C:\processados")

# --- FUNÇÕES AUXILIARES ---

def aguardar_arquivo_disponivel(caminho_arquivo: str, tentativas: int = 10, espera: int = 1) -> bool:
    """
    Aguarda até que o arquivo esteja disponível para leitura.
    """
    for i in range(tentativas):
        try:
            with open(caminho_arquivo, 'rb') as f:
                pass
            return True
        except (IOError, PermissionError) as e:
            print(f"⏳ Aguardando arquivo ficar disponível (tentativa {i+1}/{tentativas}): {str(e)}")
            logging.warning(f"Aguardando arquivo ficar disponível (tentativa {i+1}/{tentativas}): {str(e)}")
            time.sleep(espera)
    return False

def extrair_texto_pdf(caminho_pdf):
    """Extrai texto de um arquivo PDF, aguardando até que esteja disponível"""
    if not aguardar_arquivo_disponivel(caminho_pdf):
        raise IOError(f"Arquivo não disponível após várias tentativas: {caminho_pdf}")
    logging.info(f"Extraindo texto do PDF: {caminho_pdf}")
    texto_extraido = ""
    with pdfplumber.open(caminho_pdf) as pdf:
        for pagina in pdf.pages:
            texto_extraido += pagina.extract_text() + "\n"
    return texto_extraido.strip()

def extrair_campos(texto):
    resultado = {}
    
    # Split text into lines and find NF number on the right side
    linhas = texto.split('\n')
    numero_nota = ""
    
    for linha in linhas:
        # Look for 8-digit number at the start of a line or after significant whitespace
        match = re.search(r'(?:^|\s{2,})(\d{8})(?:\s|$)', linha)
        if match:
            numero_nota = match.group(1)
            break
    
    resultado["numero_nota"] = str(numero_nota) if numero_nota else ""

    # Extração do prestador e CNPJ (existente)
    prestador_match = re.search(r"(?:Prestador|Emitente).*?:\s*(.*)", texto, re.IGNORECASE)
    resultado["prestador"] = prestador_match.group(1).strip() if prestador_match else ""
    
    cnpj_match = re.search(r"CNPJ[^\d]*(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})", texto, re.IGNORECASE)
    resultado["cnpj"] = cnpj_match.group(1) if cnpj_match else ""

    # Extração do pagador
    pagador_match = re.search(r"(?:Tomador|Cliente|Pagador).*?:\s*(.*?)(?:\n|CNPJ|$)", texto, re.IGNORECASE)
    resultado["pagador"] = pagador_match.group(1).strip() if pagador_match else ""
    
    # CNPJ do pagador (procura após o nome do pagador)
    cnpj_pagador_match = re.search(r"(?:Tomador|Cliente|Pagador).*?(?:CNPJ[^\d]*(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}))", texto, re.IGNORECASE)
    resultado["cnpj_pagador"] = cnpj_pagador_match.group(1) if cnpj_pagador_match else ""

    # Detecção de forma de pagamento
    resultado["forma_pagamento"] = detectar_forma_pagamento(texto)

    valor_total_match = re.search(r"(?:Total a pagar|Valor Total da Nota|Total do contrato)[:\s]*R?\$?\s*([\d.,]+)", texto, re.IGNORECASE)
    resultado["valor_total"] = valor_total_match.group(1) if valor_total_match else "0"

    irrf_match = re.search(r"IRRF[:\s]*R?\$?\s*([\d.,]+)", texto, re.IGNORECASE)
    resultado["irrf"] = irrf_match.group(1) if irrf_match else "0"

    # --- Novos campos para corresponder à estrutura desejada ---
    # Estes campos serão vazios a menos que você adicione lógica para preenchê-los
    resultado["data_emissao_nf"] = ""
    resultado["operacao"] = ""
    resultado["observacoes"] = ""

    return resultado

def detectar_forma_pagamento(texto: str) -> str:
    """Detecta a forma de pagamento baseado no conteúdo do PDF."""
    texto_lower = texto.lower()
    
    # Verifica se contém referências ao Itaú
    if any(banco in texto_lower for banco in ["itau", "itaú", "banco 341"]):
        return "B"
    
    # Verifica se contém referências a outros bancos
    outros_bancos = ["banco", "bradesco", "santander", "bb", "banco do brasil", "caixa"]
    if any(banco in texto_lower for banco in outros_bancos):
        return "D"
    
    return ""  # Retorna vazio se não encontrar referência a bancos

def extrair_com_deepseek(texto_pdf: str) -> Optional[Dict[str, str]]:
    try:
        api_url = "https://api.deepseek.com/v1/chat/completions"  # DeepSeek API endpoint
        api_key = DEEPSEEK_API_KEY_HARDCODED  # Usando a chave hardcoded global

        messages = [
            {
                "role": "system",
                "content": """Você é um extrator de dados de nota fiscal. 
                Extraia os seguintes campos em JSON:
                - numero_nota (apenas números)
                - prestador (nome ou razão social)
                - cnpj (formato XX.XXX.XXX/XXXX-XX)
                - pagador (nome ou razão social do tomador/cliente)
                - cnpj_pagador (CNPJ do tomador/cliente)
                - valor_total (valor em formato numérico)
                - irrf (valor em formato numérico)
                - data_emissao (formato DD/MM/AAAA)
                - operacao (e.g., "MATERIA PRIMA", "SERVICO", "VENDA")
                - observacoes (texto livre, se houver)
                
                IMPORTANTE: Não confundir IRRF com CSLL, são impostos diferentes.

                Retorne um JSON válido, sem explicações ou comentários adicionais. NUNCA gere dados ficticios.
                Se um campo não for encontrado, retorne uma string vazia para ele."""
            },
            {
                "role": "user",
                "content": texto_pdf
            }
        ]

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        payload = {
            "model": "deepseek-chat",  # DeepSeek model name
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"}
        }

        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status() # Levanta um erro para códigos de status HTTP 4xx/5xx
        response_data = response.json()

        if 'choices' in response_data and len(response_data['choices']) > 0:
            content = response_data['choices'][0]['message']['content']
            try:
                dados = json.loads(content)
                return {
                    "numero_nota": str(dados.get("numero_nota", "")),
                    "prestador": str(dados.get("prestador", "")),
                    "cnpj": str(dados.get("cnpj", "")),
                    "pagador": str(dados.get("pagador", "")),
                    "cnpj_pagador": str(dados.get("cnpj_pagador", "")),
                    "valor_total": str(dados.get("valor_total", "0")),
                    "irrf": str(dados.get("irrf", "0")),
                    "data_emissao_nf": str(dados.get("data_emissao", "")),
                    "operacao": str(dados.get("operacao", "")),
                    "observacoes": str(dados.get("observacoes", ""))
                }
            except json.JSONDecodeError:
                print(f"Erro JSON DeepSeek:\n{content}")
                return None
        else:
            print(f"Resposta inesperada DeepSeek:\n{response_data}")
            return None

    except requests.exceptions.RequestException as req_e:
        print(f"Erro na requisição à DeepSeek: {req_e}")
        return None
    except Exception as e:
        print(f"Erro ao chamar DeepSeek: {str(e)}")
        return None

def parse_valor(valor_str: str) -> float:
    if not valor_str:
        return 0.0
    
    try:
        if isinstance(valor_str, (int, float)):
            return float(valor_str)
        
        valor_str = str(valor_str).strip()
        valor_limpo = re.sub(r'[R$\s]', '', valor_str)
        valor_limpo = re.sub(r'[^\d,.]', '', valor_limpo)
        
        if not valor_limpo:
            print(f"Valor vazio após limpeza: '{valor_str}'")
            return 0.0
            
        valor_limpo = valor_limpo.replace(',', '.')
        
        if valor_limpo.count('.') > 1:
            partes = valor_limpo.split('.')
            valor_limpo = ''.join(partes[:-1]) + '.' + partes[-1]
        
        resultado = float(valor_limpo)
        
        if not isinstance(resultado, float) or not math.isfinite(resultado):
            print(f"Resultado inválido: '{resultado}' para entrada '{valor_str}'")
            return 0.0
            
        return resultado
        
    except (ValueError, TypeError) as e:
        print(f"Erro ao converter valor: '{valor_str}'. Erro: {str(e)}")
        return 0.0

def verificar_necessidade_ocr(texto: str, caminho_pdf: str) -> bool:
    """Verifica se um PDF precisa de OCR."""
    texto_limpo = texto.strip()
    if len(texto_limpo) < 200:
        print(f"Texto extraído muito pequeno ({len(texto_limpo)} caracteres), provável necessidade de OCR")
        logging.warning(f"Texto muito pequeno extraído de {caminho_pdf} ({len(texto_limpo)} chars). Provável necessidade de OCR.")
        return True
        return True
    try:
        with pdfplumber.open(caminho_pdf) as pdf:
            num_paginas = len(pdf.pages)
            densidade = len(texto_limpo) / max(1, num_paginas)
            if densidade < 500:
                print(f"Densidade de texto baixa ({densidade:.1f} caracteres/página), provável necessidade de OCR")
                logging.warning(f"Densidade baixa ({densidade:.1f} chars/pág). OCR possivelmente necessário.")
                return True
    except Exception as e:
        print(f"Erro ao verificar densidade de texto: {str(e)}")
        logging.error(f"Erro ao verificar densidade do texto: {str(e)}")
    return False

def pdf_para_imagens(caminho_pdf: str) -> List[Image.Image]:
    """Converte um PDF em uma lista de imagens."""
    try:
        return pdf2image.convert_from_path(
            caminho_pdf, 
            dpi=300,
            fmt='png',
            poppler_path=POPPLER_PATH # Usando o caminho global do Poppler
        )
    except Exception as e:
        print(f"Erro ao converter PDF para imagens: {str(e)}")
        return []

def extrair_texto_com_ocr(imagem: Image.Image) -> str:
    """Extrai texto de uma imagem usando OCR."""
    try:
        texto = pytesseract.image_to_string(
            imagem, 
            lang='por',
            config='--psm 6'
        )
        return texto
    except Exception as e:
        print(f"Erro na extração OCR: {str(e)}")
        return ""

def processar_com_ocr_real(caminho_pdf: str) -> Optional[Dict[str, str]]:
    """Processa um PDF usando OCR real."""
    print("Iniciando processamento OCR...")
    try:
        imagens = pdf_para_imagens(caminho_pdf)
        if not imagens:
            return None # pdf_para_imagens já imprime o erro
        
        texto_completo = ""
        for i, img in enumerate(imagens):
            print(f"   Processando página {i+1}/{len(imagens)} com OCR...")
            texto_pagina = extrair_texto_com_ocr(img)
            texto_completo += texto_pagina + "\n"
        
        dados = extrair_com_deepseek(texto_completo)
        if dados is None:
            dados = extrair_campos(texto_completo) # Fallback para Regex nos dados OCRizados
        
        return dados
        
    except Exception as e:
        raise # Propaga a exceção para ser tratada no loop principal

def processar_com_ocr(caminho_pdf: str) -> Tuple[Optional[Dict[str, str]], bool]:
    """
    Processa um PDF usando OCR se necessário.
    """
    texto_extraido_pdfplumber = extrair_texto_pdf(caminho_pdf)
    
    if verificar_necessidade_ocr(texto_extraido_pdfplumber, caminho_pdf):
        dados_ocr_processados = processar_com_ocr_real(caminho_pdf)
        if dados_ocr_processados is not None:
            return dados_ocr_processados, True
        
    dados = extrair_com_deepseek(texto_extraido_pdfplumber)
    if dados is None:
        dados = extrair_campos(texto_extraido_pdfplumber)
    
    return dados, False

def classificar_tipo_documento(texto: str) -> str:
    texto_lower = texto.lower()

    # Palavras-chave para cheque
    palavras_chave_cheque = ["cheque", "pague por este", "compensação", "banco", "agência", "conta corrente", "cheque n"]
    if any(keyword in texto_lower for keyword in palavras_chave_cheque):
        return "CHEQUE"

    # Palavras-chave para nota fiscal (reforçadas)
    palavras_chave_nf = ["nota fiscal", "nf-e", "nfse", "danfe", "prestador", "tomador", "emitente", "valor total", "irrf", "município", "serviços"]
    if any(keyword in texto_lower for keyword in palavras_chave_nf):
        return "NOTA_FISCAL"
        
    return "DESCONHECIDO"

def extrair_numero_nf_do_arquivo(nome_arquivo: str) -> str:
    """Extrai o número da NF do nome do arquivo."""
    match = re.search(r'NF\s*(\d+)', nome_arquivo, re.IGNORECASE)
    if match:
        return match.group(1)
    # Tenta extrair qualquer sequência de dígitos se 'NF' não for encontrada
    match_any_digits = re.search(r'(\d+)', nome_arquivo)
    if match_any_digits:
        return match_any_digits.group(1)
    return ""

def formatar_valor_csv(valor: float) -> str:
    """Formata um valor float para o formato '- 0.000,00' para CSV."""
    try:
        valor = float(valor)
    except (ValueError, TypeError):
        return "" 
        
    valor_abs = abs(valor)
    valor_formatado = f"{valor_abs:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    if valor < 0:
        return f"- {valor_formatado}"
    return valor_formatado

# --- FUNÇÕES PARA ESCRITA DE CSV POR LINHA ---

def escrever_cabecalho_csv(caminho_csv: str, fieldnames: List[str], delimiter: str = ';'):
    """Escreve o cabeçalho no CSV se o arquivo não existir ou estiver vazio."""
    file_exists = os.path.exists(caminho_csv) and os.path.getsize(caminho_csv) > 0
    with open(caminho_csv, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter)
        if not file_exists:
            writer.writeheader()
            logging.info(f"Cabecalho escrito no CSV: {caminho_csv}")

def adicionar_linha_csv(caminho_csv: str, row_data: Dict[str, Any], fieldnames: List[str], delimiter: str = ';'):
    """Adiciona uma única linha ao CSV."""
    with open(caminho_csv, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter)
        writer.writerow(row_data)
    logging.info(f"Linha adicionada ao CSV: {caminho_csv}")

# --- BLOCO DA EXECUÇÃO PRINCIPAL (`if __name__ == "__main__":`) ---

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv("ini.env")

    # Lê do .env
    pasta_pdf = os.getenv("PASTA_PDF", r"H:\Notas")
    pasta_raiz = os.getenv("PASTA_SAIDA", r"C:\processados")

    logging.info(f"Pasta de PDFs: {pasta_pdf}")
    logging.info(f"Pasta de saída: {pasta_raiz}")

    # Sobrescreve se vier argumentos
    if len(sys.argv) > 1:
        pasta_pdf = sys.argv[1]
        print(f"[ARGUMENTO] Pasta de PDFs recebida: {pasta_pdf}")
    else:
        print(f"[ENV] Usando pasta de PDFs: {pasta_pdf}")

    if len(sys.argv) > 2:
        pasta_raiz = sys.argv[2]
        print(f"[ARGUMENTO] Pasta raiz recebida: {pasta_raiz}")
    else:
        print(f"[ENV] Usando pasta raiz: {pasta_raiz}")

    # Poppler e Tesseract
    POPPLER_PATH = os.getenv("POPPLER_PATH", r"C:\poppler-24.08.0\Library\bin")
    pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_PATH", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    DEEPSEEK_API_KEY_HARDCODED = os.getenv("DEEPSEEK_API_KEY", "")

    output_csv_sucesso = os.path.join(pasta_raiz, "notas_fiscais_extraidas.csv")
    output_csv_erro = os.path.join(pasta_raiz, "arquivos_com_erro.csv")
    output_csv_nao_suportados = os.path.join(pasta_raiz, "documentos_nao_suportados.csv")

    # Definir fieldnames para o CSV de SUCESSO com a nova estrutura e ordem
    fieldnames_sucesso = [
        "DATA EMISSÃO NF",
        "NOME FORNECEDOR",
        "NÚMERO NF",
        "OPERAÇÃO",
        "VALOR",
        "FORMA PAGAMENTO",
        "OBSERVAÇÕES",
        "Caminho do Arquivo"
    ]
    fieldnames_erro = ["caminho_arquivo", "erro_detalhes", "tipo_documento"]
    fieldnames_nao_suportados = ["caminho_arquivo", "tipo_documento", "detalhes"]

    # Escrever cabeçalhos nos CSVs se eles não existirem
    escrever_cabecalho_csv(output_csv_sucesso, fieldnames_sucesso)
    escrever_cabecalho_csv(output_csv_erro, fieldnames_erro)
    escrever_cabecalho_csv(output_csv_nao_suportados, fieldnames_nao_suportados)

    # Encontra todos os arquivos PDF recursivamente na pasta_pdf
    pdf_files = glob.glob(os.path.join(pasta_pdf, "**", "*.pdf"), recursive=True)
    logging.info(f"{len(pdf_files)} PDFs encontrados para processar.")

    if not pdf_files:
        print(f"Nenhum PDF encontrado em {pasta_pdf} ou suas subpastas.")
        sys.exit(1)

    total_arquivos = len(pdf_files)
    print(f"Encontrados {total_arquivos} arquivos PDF para processar")

    for idx, pdf_path in enumerate(pdf_files, 1):
        print(f"\n[{idx}/{total_arquivos}] Processando: {os.path.basename(pdf_path)}")
        logging.info(f"[{idx}/{len(pdf_files)}] Processando arquivo: {pdf_path}")
        
        texto_documento = "" 
        tipo_documento_detectado = "DESCONHECIDO" 

        try:
            # 1. Extrair texto inicial com pdfplumber
            texto_pdfplumber = extrair_texto_pdf(pdf_path)
            texto_documento = texto_pdfplumber

            # 2. Verificar e tentar OCR se necessário
            necessita_ocr = verificar_necessidade_ocr(texto_pdfplumber, pdf_path)
            if necessita_ocr:
                print("Texto inicial vazio/pequeno, tentando OCR para extração de texto.")
                ocr_texto = ""
                try:
                    imagens = pdf_para_imagens(pdf_path)
                    if not imagens:
                        raise Exception("Não foi possível converter o PDF em imagens para OCR. Verifique o Poppler e o caminho.")
                    
                    for i, img in enumerate(imagens):
                        print(f"   Processando página {i+1}/{len(imagens)} com OCR...")
                        ocr_texto += extrair_texto_com_ocr(img) + "\n"
                    texto_documento = ocr_texto.strip() 
                    
                    if not texto_documento: 
                         print(f"OCR não extraiu texto significativo de {os.path.basename(pdf_path)}. Documento pode ser ilegível ou vazio.")
                         
                except Exception as ocr_e:
                    print(f"Erro durante o processo de OCR para {os.path.basename(pdf_path)}: {str(ocr_e)}")
            
            # 3. Classificar o tipo de documento com base no texto disponível
            tipo_documento_detectado = classificar_tipo_documento(texto_documento)
            print(f"Tipo de documento detectado: {tipo_documento_detectado}")

            # 4. Tratar documentos não suportados (ex: cheques)
            if tipo_documento_detectado == "CHEQUE":
                print(f"Documento identificado como CHEQUE. Registrando em 'documentos_nao_suportados.csv' e pulando extração de NF.")
                adicionar_linha_csv(output_csv_nao_suportados, {
                    "caminho_arquivo": pdf_path,
                    "tipo_documento": "CHEQUE",
                    "detalhes": "Documento identificado como cheque. Não suportado para extração de Nota Fiscal."
                }, fieldnames_nao_suportados)
                continue 

            # 5. Tentar extração de campos da Nota Fiscal com DeepSeek e depois Regex
            dados_finais = None
            metodo_usado = "Desconhecido"

            dados_deepseek = extrair_com_deepseek(texto_documento)
            if dados_deepseek is not None:
                dados_finais = dados_deepseek
                metodo_usado = "DeepSeek"
            else:
                print("DeepSeek falhou ou retornou dados incompletos. Tentando Regex...")
                dados_regex = extrair_campos(texto_documento)
                if dados_regex is not None:
                    dados_finais = dados_regex
                    metodo_usado = "Regex"
            
            # 6. Se ainda não houver dados significativos (prestador OU numero_nota vazios), registre como erro.
            if dados_finais is None or not (dados_finais.get("prestador") and dados_finais.get("numero_nota")):
                print(f"Falha crítica: Não foi possível extrair dados significativos de {os.path.basename(pdf_path)}")
                erro_detalhes = f"Falha na extração de dados após todas as tentativas ({metodo_usado}). Tipo: {tipo_documento_detectado}."
                adicionar_linha_csv(output_csv_erro, {
                    "caminho_arquivo": pdf_path,
                    "erro_detalhes": erro_detalhes,
                    "tipo_documento": tipo_documento_detectado
                }, fieldnames_erro)
                continue

            # 7. Processar e formatar dados extraídos com sucesso para o CSV
            nome_fornecedor = str(dados_finais.get("prestador", "")).strip()
            numero_nf = str(dados_finais.get("numero_nota", "")).strip()
            
            # Fallback final para número da nota do nome do arquivo
            if not numero_nf:
                numero_nf = str(extrair_numero_nf_do_arquivo(os.path.basename(pdf_path)))
                if numero_nf:
                    print(f" Número da nota extraído do nome do arquivo: NF {numero_nf}")
            
            valor_total_float = parse_valor(dados_finais.get("valor_total", "0"))
            irrf_float = parse_valor(dados_finais.get("irrf", "0"))
            valor_final_float = round(valor_total_float - irrf_float, 2)
            valor_formatado = formatar_valor_csv(valor_final_float)
            
            forma_pagamento = dados_finais.get("forma_pagamento", "") or detectar_forma_pagamento(texto_documento)
            
            data_emissao_nf = str(dados_finais.get("data_emissao_nf", "")).strip()
            operacao = str(dados_finais.get("operacao", "")).strip()
            observacoes = str(dados_finais.get("observacoes", "")).strip()

            # NOVA LÓGICA: Se data_emissao_nf estiver vazia, tenta extrair do texto
            if not data_emissao_nf:
                data_match = re.search(r"(\d{2}/\d{2}/\d{4})", texto_documento)
                if data_match:
                    data_emissao_nf = data_match.group(1)
                    print(f" Data de emissão obtida por fallback: {data_emissao_nf}")

            # Exibir resultados no console
            print(f" Dados extraídos via {metodo_usado}:")
            print(f"   - NOME FORNECEDOR: {nome_fornecedor}")
            print(f"   - NÚMERO NF: {numero_nf}")
            print(f"   - VALOR: R${valor_formatado}")
            print(f"   - FORMA PAGAMENTO: {forma_pagamento}")
            print(f"   - DATA EMISSÃO NF: {data_emissao_nf}")
            print(f"   - OPERAÇÃO: {operacao}")
            print(f"   - OBSERVAÇÕES: {observacoes}")
            print(f"   - Caminho do Arquivo: {pdf_path}")
            
            # Adiciona a linha ao CSV de sucesso
            adicionar_linha_csv(output_csv_sucesso, {
                "DATA EMISSÃO NF": data_emissao_nf,
                "NOME FORNECEDOR": nome_fornecedor,
                "NÚMERO NF": numero_nf,
                "OPERAÇÃO": operacao,
                "VALOR": valor_formatado,
                "FORMA PAGAMENTO": forma_pagamento,
                "OBSERVAÇÕES": observacoes,
                "Caminho do Arquivo": pdf_path
            }, fieldnames_sucesso)
            
        except Exception as e:
            error_message = f"Erro inesperado no processamento do arquivo: {str(e)}"
            logging.error(f"Erro ao processar {pdf_path}: {str(e)}")
            print(f"Erro ao processar {os.path.basename(pdf_path)}: {error_message}")
            adicionar_linha_csv(output_csv_erro, {
                "caminho_arquivo": pdf_path, 
                "erro_detalhes": error_message,
                "tipo_documento": tipo_documento_detectado
            }, fieldnames_erro)
            continue

    logging.info("Processamento concluído.")
    logging.info(f"CSV sucesso: {output_csv_sucesso}")
    logging.info(f"CSV erro: {output_csv_erro}")
    logging.info(f"CSV não suportados: {output_csv_nao_suportados}")
    print(f"\nProcessamento concluído.")
    print(f"CSV de sucesso gerado/atualizado: {output_csv_sucesso}")
    print(f"CSV de erros gerado/atualizado: {output_csv_erro}")
    print(f"CSV de documentos não suportados gerado/atualizado: {output_csv_nao_suportados}")
