import discord

import config
import database as db
from utils import embeds


async def _canal_notificacoes(guild: discord.Guild):
    if config.CANAL_NOTIFICACOES_ID:
        canal = guild.get_channel(int(config.CANAL_NOTIFICACOES_ID))
        if canal:
            return canal
    return None


async def _canal_comprovantes(guild: discord.Guild):
    if config.CANAL_COMPROVANTES_ID:
        canal = guild.get_channel(int(config.CANAL_COMPROVANTES_ID))
        if canal:
            return canal
    return None


async def notificar_novo_pedido(guild: discord.Guild, pedido: dict):
    canal = await _canal_notificacoes(guild)
    if not canal:
        return
    await canal.send(
        f"🆕 Novo pedido **{pedido['id']}** de <@{pedido['cliente_id']}> — "
        f"{pedido['produto_nome']} ({pedido['tamanho']}) — R$ {pedido['valor_total']:.2f}"
    )


async def notificar_formulario_confirmado(guild: discord.Guild, pedido: dict):
    canal = await _canal_notificacoes(guild)
    if canal:
        await canal.send(f"📝 Formulário confirmado para o pedido **{pedido['id']}**.")


async def notificar_comprovante_enviado(guild: discord.Guild, pedido: dict, anexo: discord.Attachment):
    canal = await _canal_comprovantes(guild) or await _canal_notificacoes(guild)
    if not canal:
        return
    embed = discord.Embed(
        title=f"📸 Comprovante recebido — {pedido['id']}",
        description=f"Cliente: <@{pedido['cliente_id']}>\nValor: R$ {pedido['valor_total']:.2f}",
        color=discord.Color.blue(),
    )
    if anexo.content_type and anexo.content_type.startswith("image"):
        embed.set_image(url=anexo.url)
    else:
        embed.add_field(name="Arquivo", value=f"[Abrir comprovante]({anexo.url})")

    from cogs.orders import AprovacaoView

    await canal.send(embed=embed, view=AprovacaoView(pedido["id"]))


async def notificar_pagamento_aprovado(guild: discord.Guild, pedido: dict):
    canal = guild.get_channel(pedido["ticket_channel_id"]) if pedido.get("ticket_channel_id") else None
    if canal:
        await canal.send(f"🟢 Pagamento aprovado! Seu pedido **{pedido['id']}** entrará em preparação em breve.")


async def notificar_pagamento_recusado(guild: discord.Guild, pedido: dict, motivo: str = ""):
    canal = guild.get_channel(pedido["ticket_channel_id"]) if pedido.get("ticket_channel_id") else None
    if canal:
        texto = f"🔴 Pagamento recusado para o pedido **{pedido['id']}**."
        if motivo:
            texto += f"\nMotivo: {motivo}"
        await canal.send(texto)


async def notificar_status(guild: discord.Guild, pedido: dict):
    canal = guild.get_channel(pedido["ticket_channel_id"]) if pedido.get("ticket_channel_id") else None
    if canal:
        await canal.send(f"📦 Status atualizado: {embeds.status_label(pedido['status'])}")


async def notificar_produto_esgotado(guild: discord.Guild, produto_nome: str, tamanho: str):
    canal = await _canal_notificacoes(guild)
    if canal:
        await canal.send(f"🔴 **ESGOTADO**: {produto_nome} (tamanho {tamanho}) não tem mais estoque.")


async def notificar_estoque_baixo(guild: discord.Guild, produto_nome: str, tamanho: str, restante: int):
    canal = await _canal_notificacoes(guild)
    if canal:
        await canal.send(f"🟡 Estoque baixo: {produto_nome} (tamanho {tamanho}) — restam {restante} unidade(s).")


async def notificar_ticket_aberto(guild: discord.Guild, categoria: str, cliente: discord.Member):
    canal = await _canal_notificacoes(guild)
    if canal:
        await canal.send(f"🎫 Novo ticket ({categoria}) aberto por {cliente.mention}.")
