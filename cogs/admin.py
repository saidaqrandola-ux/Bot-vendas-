import datetime

import discord
from discord import app_commands
from discord.ext import commands

import database as db
from utils.permissions import is_ceo, is_atendente


def _erro_ceo():
    return "🚫 Apenas o CEO pode usar este comando."


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    produto_group = app_commands.Group(name="produto", description="Gestão de produtos")
    estoque_group = app_commands.Group(name="estoque", description="Gestão de estoque")
    preco_group = app_commands.Group(name="preco", description="Gestão de preços de venda")
    custo_group = app_commands.Group(name="custo", description="Gestão de preço de custo")
    cupom_group = app_commands.Group(name="cupom-admin", description="Gestão de cupons (CEO)")
    frete_group = app_commands.Group(name="frete", description="Gestão de frete")

    # ---------------- /produto ----------------
    @produto_group.command(name="adicionar", description="Adicionar um novo produto (CEO)")
    async def produto_adicionar(
        self, interaction: discord.Interaction, nome: str, preco_venda: float, preco_custo: float,
        permite_personalizacao: bool, descricao: str = "", imagem_url: str = "",
    ):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        produto_id = db.criar_produto(nome, descricao, preco_venda, preco_custo, permite_personalizacao, imagem_url)
        await interaction.response.send_message(f"✅ Produto **{nome}** criado com ID `{produto_id}`.", ephemeral=True)

    @produto_group.command(name="editar", description="Editar um produto existente (CEO)")
    async def produto_editar(
        self, interaction: discord.Interaction, produto_id: int, nome: str = "", descricao: str = "",
        imagem_url: str = "",
    ):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        campos = {k: v for k, v in {"nome": nome, "descricao": descricao, "imagem_url": imagem_url}.items() if v}
        if not campos:
            return await interaction.response.send_message("Nada para editar.", ephemeral=True)
        db.editar_produto(produto_id, **campos)
        await interaction.response.send_message(f"✅ Produto `{produto_id}` atualizado.", ephemeral=True)

    @produto_group.command(name="remover", description="Remover um produto (CEO)")
    async def produto_remover(self, interaction: discord.Interaction, produto_id: int):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        db.remover_produto(produto_id)
        await interaction.response.send_message(f"🗑️ Produto `{produto_id}` removido.", ephemeral=True)

    @produto_group.command(name="listar", description="Listar todos os produtos, incluindo ocultos (CEO)")
    async def produto_listar(self, interaction: discord.Interaction):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        produtos = db.listar_produtos(apenas_visiveis=False)
        if not produtos:
            return await interaction.response.send_message("Nenhum produto cadastrado.", ephemeral=True)
        texto = "\n".join(
            f"`{p['id']}` {p['nome']} — venda R$ {p['preco_venda']:.2f} / custo R$ {p['preco_custo']:.2f} "
            f"{'🙈 oculto' if p['oculto'] else ''} {'⭐' if p['destaque'] else ''}"
            for p in produtos
        )
        await interaction.response.send_message(texto[:1900], ephemeral=True)

    @produto_group.command(name="destaque", description="Marcar/desmarcar produto como destaque (CEO)")
    async def produto_destaque(self, interaction: discord.Interaction, produto_id: int, destaque: bool):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        db.editar_produto(produto_id, destaque=int(destaque))
        await interaction.response.send_message(f"⭐ Produto `{produto_id}` destaque = {destaque}.", ephemeral=True)

    @produto_group.command(name="ocultar", description="Ocultar/reexibir um produto no catálogo (CEO)")
    async def produto_ocultar(self, interaction: discord.Interaction, produto_id: int, ocultar: bool):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        db.editar_produto(produto_id, oculto=int(ocultar))
        await interaction.response.send_message(f"🙈 Produto `{produto_id}` oculto = {ocultar}.", ephemeral=True)

    @produto_group.command(name="consultar", description="Consultar detalhes de um produto (atendente/CEO)")
    async def produto_consultar(self, interaction: discord.Interaction, produto_id: int):
        if not is_atendente(interaction.user):
            return await interaction.response.send_message("🚫 Apenas atendentes ou o CEO podem usar este comando.", ephemeral=True)
        produto = db.obter_produto(produto_id)
        if not produto:
            return await interaction.response.send_message("Produto não encontrado.", ephemeral=True)
        estoque = db.obter_estoque(produto_id)
        texto_estoque = "\n".join(f"{t}: {q}" for t, q in estoque.items()) or "Sem estoque cadastrado."
        campos_publicos = f"👕 **{produto['nome']}** — R$ {produto['preco_venda']:.2f}\n📦 Estoque:\n{texto_estoque}"
        if is_ceo(interaction.user):
            campos_publicos += f"\n💵 Custo: R$ {produto['preco_custo']:.2f}"
        await interaction.response.send_message(campos_publicos, ephemeral=True)

    # ---------------- /estoque ----------------
    @estoque_group.command(name="consultar", description="Consultar estoque de um produto (atendente/CEO)")
    async def estoque_consultar(self, interaction: discord.Interaction, produto_id: int):
        await Admin.produto_consultar.callback(self, interaction, produto_id)

    @estoque_group.command(name="adicionar", description="Adicionar estoque de um tamanho (CEO)")
    async def estoque_adicionar(self, interaction: discord.Interaction, produto_id: int, tamanho: str, quantidade: int):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        db.ajustar_estoque(produto_id, tamanho.upper(), quantidade)
        await interaction.response.send_message(f"📦 +{quantidade} no tamanho {tamanho.upper()}.", ephemeral=True)

    @estoque_group.command(name="remover", description="Remover estoque de um tamanho (CEO)")
    async def estoque_remover(self, interaction: discord.Interaction, produto_id: int, tamanho: str, quantidade: int):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        db.ajustar_estoque(produto_id, tamanho.upper(), -quantidade)
        await interaction.response.send_message(f"📦 -{quantidade} no tamanho {tamanho.upper()}.", ephemeral=True)

    @estoque_group.command(name="ajustar", description="Definir o estoque exato de um tamanho (CEO)")
    async def estoque_ajustar(self, interaction: discord.Interaction, produto_id: int, tamanho: str, quantidade: int):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        db.set_estoque(produto_id, tamanho.upper(), quantidade)
        await interaction.response.send_message(f"📦 Estoque de {tamanho.upper()} ajustado para {quantidade}.", ephemeral=True)

    @estoque_group.command(name="alerta", description="Ver produtos com estoque baixo ou esgotado (CEO)")
    async def estoque_alerta(self, interaction: discord.Interaction):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message(_erro_ceo(), ephemeral=True)
        import config

        linhas = []
        for p in db.listar_produtos(apenas_visiveis=False):
            estoque = db.obter_estoque(p["id"])
            for tamanho, qtd in estoque.items():
                if qtd == 0:
                    linhas.append(f"🔴 {p['nome']} ({tamanho}) — ESGOTADO")
                elif qtd <= config.ESTOQUE_BAIXO_LIMITE:
                    linhas.append(f"🟡 {p['nome']} ({tamanho}) — {qtd} restante(s)")
        await interaction.response.send_message("\n".join(linhas) or "✅ Nenhum alerta de estoque.", ephemeral=True)

    # ---------------- /preco e /custo ----------------
    @preco_group.command(name="ver", description="Ver preços de um produto (CEO)")
    async def preco_ver(self, interaction: discord.Interaction, produto_id: int):
