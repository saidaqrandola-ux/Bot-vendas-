"""
Configuração central do bot da loja.
Todos os valores sensíveis (token, etc.) devem vir de variáveis de ambiente (.env),
NUNCA hardcoded no código-fonte que vai para o GitHub.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ------------------------------------------------------------------
# Token do bot (obrigatório via variável de ambiente / Railway "Variables")
# ------------------------------------------------------------------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# ------------------------------------------------------------------
# IDs de cargos
# ------------------------------------------------------------------
CEO_ROLE_ID = int(os.getenv("CEO_ROLE_ID", "1543348239854469202"))
ATENDENTE_ROLE_ID = int(os.getenv("ATENDENTE_ROLE_ID", "1543348241238724768"))

# ------------------------------------------------------------------
# PIX
# ------------------------------------------------------------------
# Chave PIX exibida ao cliente. Pode ser sobrescrita via variável de ambiente PIX_KEY.
PIX_KEY = os.getenv("PIX_KEY", "11949850080")
PIX_MERCHANT_NAME = os.getenv("PIX_MERCHANT_NAME", "LOJA")[:25]  # limite do padrão EMV
PIX_MERCHANT_CITY = os.getenv("PIX_MERCHANT_CITY", "SAO PAULO")[:15]

# ------------------------------------------------------------------
# Canais internos (o bot cria/usa esses canais por nome dentro da categoria configurada,
# ou você pode fixar IDs específicos via variável de ambiente)
# ------------------------------------------------------------------
CANAL_COMPROVANTES_ID = os.getenv("CANAL_COMPROVANTES_ID")  # canal privado da equipe
CANAL_NOTIFICACOES_ID = os.getenv("CANAL_NOTIFICACOES_ID")  # avisos de novo pedido etc.
CATEGORIA_TICKETS_ID = os.getenv("CATEGORIA_TICKETS_ID")    # categoria onde tickets são criados

# ------------------------------------------------------------------
# Banco de dados
# ------------------------------------------------------------------
DATABASE_PATH = os.getenv("DATABASE_PATH", "loja.db")

# ------------------------------------------------------------------
# Estoque baixo - a partir de quantas unidades avisar a equipe
# ------------------------------------------------------------------
ESTOQUE_BAIXO_LIMITE = int(os.getenv("ESTOQUE_BAIXO_LIMITE", "3"))

# ------------------------------------------------------------------
# Regras automáticas de precificação
# ------------------------------------------------------------------
# Acréscimo fixo por unidade quando o cliente escolhe um tamanho especial
TAMANHOS_COM_ACRESCIMO = {
    "XXL": 10.0,
    "2GG": 10.0,
    "XXXL": 20.0,
    "3GG": 20.0,
}

# Taxa fixa cobrada quando o cliente personaliza (nome e/ou número)
TAXA_PERSONALIZACAO = float(os.getenv("TAXA_PERSONALIZACAO", "29.90"))

# Desconto automático por quantidade de peças no mesmo pedido.
# A partir de 10 peças o desconto não é automático (fica "a consultar" com a equipe).
FAIXAS_DESCONTO_QUANTIDADE = [
    (10, None),   # 10+ peças: sem desconto automático, equipe consulta manualmente
    (5, 35.0),
    (3, 20.0),
    (2, 10.0),
]


def desconto_por_quantidade(quantidade: int) -> float:
    """Retorna o desconto automático (em R$) para uma dada quantidade de peças."""
    for minimo, valor in FAIXAS_DESCONTO_QUANTIDADE:
        if quantidade >= minimo:
            return valor or 0.0
    return 0.0
