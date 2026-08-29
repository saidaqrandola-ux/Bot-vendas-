"""
Geração de PIX Copia-e-Cola (BR Code / EMV) + QR Code dinâmico.

Implementa o padrão público do Banco Central (EMV QR Code) usado por todo
PIX estático/dinâmico simples. Não depende de nenhuma API externa: o valor
exato do pedido é embutido no próprio payload, então cada QR Code gerado
já vem com o valor correto do pedido.
"""

import io
import qrcode

import config


def _tlv(id_: str, value: str) -> str:
    """Monta um campo TLV (Tag-Length-Value) no formato EMV."""
    length = f"{len(value):02d}"
    return f"{id_}{length}{value}"


def _crc16_ccitt(payload: str) -> str:
    """CRC16-CCITT (falso XModem) usado para o campo 63 do payload PIX."""
    poly = 0x1021
    crc = 0xFFFF
    data = (payload + "6304").encode("utf-8")
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def _somente_ascii_alfanumerico(texto: str) -> str:
    """O padrão EMV só aceita um conjunto limitado de caracteres; remove acentos/símbolos."""
    import unicodedata

    normalizado = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in normalizado if not unicodedata.combining(c))
    return "".join(c for c in sem_acento if c.isalnum() or c in " -").strip()


def gerar_payload_pix(valor: float, pedido_id: str) -> str:
    """
    Gera o payload "Copia e Cola" do PIX para o valor exato do pedido.
    pedido_id é usado como txid (referência) para facilitar a conciliação manual.
    """
    chave = config.PIX_KEY.strip()
    nome = _somente_ascii_alfanumerico(config.PIX_MERCHANT_NAME) or "LOJA"
    cidade = _somente_ascii_alfanumerico(config.PIX_MERCHANT_CITY) or "SAO PAULO"

    # txid: só letras/números, até 25 caracteres, sem hífen (padrão do BC)
    txid = pedido_id.replace("-", "")[:25] or "***"

    merchant_account_info = _tlv("00", "br.gov.bcb.pix") + _tlv("01", chave)
    additional_data = _tlv("05", txid)

    payload = (
        _tlv("00", "01")  # Payload Format Indicator
        + _tlv("26", merchant_account_info)  # Merchant Account Info - PIX
        + _tlv("52", "0000")  # Merchant Category Code
        + _tlv("53", "986")  # Moeda: BRL
        + _tlv("54", f"{valor:.2f}")  # Valor da transação
        + _tlv("58", "BR")  # País
        + _tlv("59", nome[:25])  # Nome do recebedor
        + _tlv("60", cidade[:15])  # Cidade do recebedor
        + _tlv("62", additional_data)  # Dados adicionais (txid)
    )

    crc = _crc16_ccitt(payload)
    return payload + "6304" + crc


def gerar_qrcode_bytes(payload: str) -> io.BytesIO:
    """Gera a imagem do QR Code (PNG) em memória a partir do payload PIX."""
    img = qrcode.make(payload, box_size=8, border=2)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer
