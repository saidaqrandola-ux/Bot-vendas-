import discord

STATUS_LABELS = {
    "aguardando_pagamento": "🟡 Aguardando pagamento",
    "comprovante_enviado": "🔵 Comprovante enviado",
    "pagamento_aprovado": "🟢 Pagamento aprovado",
    "em_preparacao": "📦 Em preparação",
    "enviado": "🚚 Enviado",
    "entregue": "📬 Entregue",
    "finalizado": "✅ Finalizado",
    "cancelado": "❌ Cancelado",
    "recusado": "🔴 Pagamento recusado",
}


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def embed_resumo_pedido(pedido: dict, cor=discord.Color.blurple()) -> discord.Embed:
    embed = discord.Embed(title=f"🧾 Pedido {pedido['id']}", color=cor)
    embed.add_field(name="👕 Produto", value=pedido.get("produto_nome", "-"), inline=True)
    embed.add_field(name="📏 Tamanho", value=pedido.get("tamanho", "-"), inline=True)
    embed.add_field(name="📦 Quantidade", value=str(pedido.get("quantidade", "-")), inline=True)

    if pedido.get("personalizacao_nome") or pedido.get("personalizacao_numero"):
        embed.add_field(
            name="🔢 Personalização",
            value=f"{pedido.get('personalizacao_nome', '-')} / nº {pedido.get('personalizacao_numero', '-')}",
            inline=False,
        )

    if pedido.get("cupom_codigo"):
        embed.add_field(name="🎟️ Cupom", value=f"{pedido['cupom_codigo']} (-{pedido.get('desconto', 0):.2f})", inline=True)

    embed.add_field(name="🚚 Frete", value=f"R$ {pedido.get('frete', 0):.2f}", inline=True)
    embed.add_field(name="💰 Total", value=f"R$ {pedido.get('valor_total', 0):.2f}", inline=True)
    embed.add_field(name="📊 Status", value=status_label(pedido.get("status", "")), inline=False)

    if pedido.get("rastreio"):
        embed.add_field(name="📮 Rastreamento", value=pedido["rastreio"], inline=False)

    return embed


def embed_confirmacao_dados(dados: dict) -> discord.Embed:
    embed = discord.Embed(title="📋 CONFIRME SEUS DADOS", color=discord.Color.gold())
    embed.add_field(name="👤 Nome", value=dados.get("nome_completo", "-"), inline=False)
    embed.add_field(name="🏠 Endereço", value=dados.get("endereco", "-"), inline=True)
    embed.add_field(name="🔢 Número", value=dados.get("numero", "-"), inline=True)
    embed.add_field(name="🏢 Complemento", value=dados.get("complemento") or "-", inline=True)
    embed.add_field(name="📍 Cidade", value=dados.get("cidade", "-"), inline=True)
    embed.add_field(name="🗺️ Estado", value=dados.get("estado", "-"), inline=True)
    embed.add_field(name="🌎 País", value=dados.get("pais", "-"), inline=True)
    embed.add_field(name="📮 CEP", value=dados.get("cep", "-"), inline=True)
    embed.add_field(name="📱 Telefone", value=dados.get("telefone", "-"), inline=True)
    embed.add_field(name="🪪 CPF", value=dados.get("cpf", "-"), inline=True)
    embed.add_field(name="📧 E-mail", value=dados.get("email", "-"), inline=False)
    embed.set_footer(text="Confira com atenção antes de confirmar. Esses dados serão usados para a entrega.")
    return embed


def embed_pagamento_pix(valor: float, pix_key: str) -> discord.Embed:
    embed = discord.Embed(title="💳 PAGAMENTO VIA PIX", color=discord.Color.green())
    embed.add_field(name="Valor do pedido", value=f"R$ {valor:.2f}", inline=False)
    embed.add_field(name="Chave PIX", value=f"`{pix_key}`", inline=False)
    embed.set_footer(text="Após pagar, clique em '✅ Já fiz o pagamento' e envie o comprovante.")
    return embed
