import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from utils.permissions import is_atendente, is_ceo, cargo_requerido_atendente

CATEGORIAS_TICKET = ["Comprar", "Pagamento", "Pedido", "Entrega", "Produto", "Dúvida", "Problema"]


async def criar_canal_ticket(
    guild: discord.Guild,
    cliente: discord.Member,
    categoria: str,
    pedido_id: str | None = None,
) -> discord.TextChannel:
    """Cria um canal de ticket privado, visível apenas para o cliente, atendentes e CEO."""
    ceo_role = guild.get_role(config.CEO_ROLE_ID)
    atendente_role = guild.get_role(config.ATENDENTE_ROLE_ID)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        cliente: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
    }
    if ceo_role:
        overwrites[ceo_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
    if atendente_role:
        overwrites[atendente_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    categoria_obj = None
    if config.CATEGORIA_TICKETS_ID:
        categoria_obj = guild.get_channel(int(config.CATEGORIA_TICKETS_ID))

    nome_canal = f"pedido-{pedido_id.lower()}" if pedido_id else f"ticket-{cliente.name}".lower()
    canal = await guild.create_text_channel(
        name=nome_canal[:95],
        overwrites=overwrites,
        category=categoria_obj if isinstance(categoria_obj, discord.CategoryChannel) else None,
        topic=f"Categoria: {categoria} | Cliente: {cliente} | Pedido: {pedido_id or '-'}",
    )
    db.criar_ticket(canal.id, pedido_id, categoria, cliente.id)
    return canal


class TicketControlView(discord.ui.View):
    """Botões fixos de controle de ticket (persistente entre reinícios do bot)."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Assumir", emoji="🎧", style=discord.ButtonStyle.primary, custom_id="ticket:assumir")
    async def assumir(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_atendente(interaction.user):
            return await interaction.response.send_message("🚫 Apenas atendentes podem assumir tickets.", ephemeral=True)
        db.atualizar_ticket(interaction.channel_id, atendente_id=interaction.user.id)
        await interaction.response.send_message(f"🎧 Ticket assumido por {interaction.user.mention}.")

    @discord.ui.button(label="Transferir", emoji="🔄", style=discord.ButtonStyle.secondary, custom_id="ticket:transferir")
    async def transferir(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_atendente(interaction.user):
            return await interaction.response.send_message("🚫 Apenas atendentes podem transferir tickets.", ephemeral=True)
        db.atualizar_ticket(interaction.channel_id, atendente_id=None)
        await interaction.response.send_message("🔄 Ticket liberado para outro atendente assumir.")

    @discord.ui.button(label="Fechar", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="ticket:fechar")
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_atendente(interaction.user):
            return await interaction.response.send_message("🚫 Apenas atendentes podem fechar tickets.", ephemeral=True)
        db.atualizar_ticket(interaction.channel_id, status="fechado")
        await interaction.response.send_message("🔒 Este ticket será arquivado em 5 segundos...")
        await interaction.channel.edit(name=f"fechado-{interaction.channel.name}"[:95])
        await interaction.channel.set_permissions(interaction.guild.default_role, view_channel=False)


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(TicketControlView())

    @app_commands.command(name="suporte", description="Abrir um ticket de suporte")
    @app_commands.choices(
        categoria=[app_commands.Choice(name=c, value=c) for c in CATEGORIAS_TICKET]
    )
    async def suporte(self, interaction: discord.Interaction, categoria: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=True)
        canal = await criar_canal_ticket(interaction.guild, interaction.user, categoria.value)
        embed = discord.Embed(
            title=f"🎫 Ticket - {categoria.value}",
            description=f"Olá {interaction.user.mention}! Descreva sua solicitação. Um atendente já foi notificado.",
            color=discord.Color.blurple(),
        )
        await canal.send(embed=embed, view=TicketControlView())
        await interaction.followup.send(f"🎫 Ticket criado: {canal.mention}", ephemeral=True)

    @app_commands.command(name="ticket", description="Comandos de gestão de ticket (atendente)")
    @app_commands.describe(acao="assumir | transferir | fechar | reabrir")
    @cargo_requerido_atendente()
    async def ticket_cmd(self, interaction: discord.Interaction, acao: str):
        ticket = db.obter_ticket(interaction.channel_id)
        if not ticket:
            return await interaction.response.send_message("Este canal não é um ticket.", ephemeral=True)

        acao = acao.lower()
        if acao == "assumir":
            db.atualizar_ticket(interaction.channel_id, atendente_id=interaction.user.id)
            await interaction.response.send_message(f"🎧 Assumido por {interaction.user.mention}.")
        elif acao == "transferir":
            db.atualizar_ticket(interaction.channel_id, atendente_id=None)
            await interaction.response.send_message("🔄 Ticket liberado.")
        elif acao == "fechar":
            db.atualizar_ticket(interaction.channel_id, status="fechado")
            await interaction.response.send_message("🔒 Ticket fechado.")
            await interaction.channel.set_permissions(interaction.guild.default_role, view_channel=False)
        elif acao == "reabrir":
            db.atualizar_ticket(interaction.channel_id, status="aberto")
            await interaction.response.send_message("🔓 Ticket reaberto.")
        else:
            await interaction.response.send_message("Ação inválida. Use: assumir, transferir, fechar ou reabrir.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
