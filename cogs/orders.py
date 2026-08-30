import discord
from discord import app_commands
from discord.ext import commands

import database as db
from utils import embeds
from utils.permissions import cargo_requerido_atendente, is_atendente

STATUS_CHOICES = [
    "aguardando_pagamento", "comprovante_enviado", "pagamento_aprovado",
    "em_preparacao", "enviado", "entregue", "finalizado", "cancelado", "recusado",
]


class AprovacaoView(discord.ui.View):
    """Anexada à notificação de comprovante recebido no canal interno da equipe."""

    def __init__(self, pedido_id: str):
        super().__init__(timeout=None)
        self.pedido_id = pedido_id

    @discord.ui.button(label="Aprovar pagamento", emoji="🟢", style=discord.ButtonStyle.success)
    async def aprovar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_atendente(interaction.user):
            return await interaction.response.send_message("🚫 Apenas atendentes/CEO podem aprovar pagamentos.", ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        pedido = db.obter_pedido(self.pedido_id)
        if not pedido:
            return await interaction.followup.send("Pedido não encontrado.", ephemeral=True)
        db.atualizar_pedido(self.pedido_id, status="pagamento_aprovado", atendente_id=interaction.user.id)
        pedido = db.obter_pedido(self.pedido_id)
        from cogs import notifications
        await notifications.notificar_pagamento_aprovado(interaction.guild, pedido)
        button.disabled = True
        await interaction.message.edit(view=self)
        await interaction.followup.send(f"🟢 Pagamento do pedido {self.pedido_id} aprovado.", ephemeral=True)

    @discord.ui.button(label="Recusar pagamento", emoji="🔴", style=discord.ButtonStyle.danger)
    async def recusar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_atendente(interaction.user):
            return await interaction.response.send_message("🚫 Apenas atendentes/CEO podem recusar pagamentos.", ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        pedido = db.obter_pedido(self.pedido_id)
        if not pedido:
            return await interaction.followup.send("Pedido não encontrado.", ephemeral=True)
        db.atualizar_pedido(self.pedido_id, status="recusado", atendente_id=interaction.user.id)
        # devolve estoque reservado
        db.ajustar_estoque(pedido["produto_id"], pedido["tamanho"], pedido["quantidade"])
        pedido = db.obter_pedido(self.pedido_id)
        from cogs import notifications
        await notifications.notificar_pagamento_recusado(interaction.guild, pedido)
        button.disabled = True
        await interaction.message.edit(view=self)
        await interaction.followup.send(f"🔴 Pagamento do pedido {self.pedido_id} recusado.", ephemeral=True)


class Orders(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    pedido_group = app_commands.Group(name="pedido", description="Gestão de pedidos (atendente)")
    cliente_group = app_commands.Group(name="cliente", description="Consulta de clientes (atendente)")
    rastreio_group = app_commands.Group(name="rastreio-atendente", description="Gestão de rastreamento (atendente)")

    async def cog_load(self):
        pass

    def _checar_atendente(self, interaction: discord.Interaction) -> bool:
        return is_atendente(interaction.user)

    async def _resposta_sem_permissao(self, interaction: discord.Interaction):
        await interaction.response.send_message("🚫 Apenas atendentes ou o CEO podem usar este comando.", ephemeral=True)

    # ---------------- /pedido ----------------
    @pedido_group.command(name="consultar", description="Consultar um pedido pelo ID")
    async def pedido_consultar(self, interaction: discord.Interaction, pedido_id: str):
        if not self._checar_atendente(interaction):
            return await self._resposta_sem_permissao(interaction)
        pedido = db.obter_pedido(pedido_id.upper())
        if not pedido:
            return await interaction.response.send_message("Pedido não encontrado.", ephemeral=True)
        await interaction.response.send_message(embed=embeds.embed_resumo_pedido(pedido), ephemeral=True)

    @pedido_group.command(name="buscar", description="Buscar pedidos por status")
    async def pedido_buscar(self, interaction: discord.Interaction, status: str = ""):
        if not self._checar_atendente(interaction):
            return await self._resposta_sem_permissao(interaction)
        pedidos = db.buscar_pedidos(status=status or None)
        if not pedidos:
            return await interaction.response.send_message("Nenhum pedido encontrado.", ephemeral=True)
        texto = "\n".join(f"{p['id']} — {embeds.status_label(p['status'])} — R$ {p['valor_total']:.2f}" for p in pedidos[:25])
        await interaction.response.send_message(f"📋 Pedidos:\n{texto}", ephemeral=True)

    async def _mudar_status(self, interaction, pedido_id, novo_status, mensagem):
        if not self._checar_atendente(interaction):
            return await self._resposta_sem_permissao(interaction)
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)
        pedido = db.obter_pedido(pedido_id.upper())
        if not pedido:
            return await interaction.followup.send("Pedido não encontrado.", ephemeral=True)
        db.atualizar_pedido(pedido["id"], status=novo_status, atendente_id=interaction.user.id)
        pedido = db.obter_pedido(pedido["id"])
        from cogs import notifications
        await notifications.notificar_status(interaction.guild, pedido)
        await interaction.followup.send(f"{mensagem} — {pedido['id']}", ephemeral=True)

    @pedido_group.command(name="aprovar", description="Aprovar o pagamento de um pedido")
    async def pedido_aprovar(self, interaction: discord.Interaction, pedido_id: str):
        await self._mudar_status(interaction, pedido_id, "pagamento_aprovado", "🟢 Pagamento aprovado")

    @pedido_group.command(name="recusar", description="Recusar o pagamento de um pedido")
    async def pedido_recusar(self, interaction: discord.Interaction, pedido_id: str):
        if not self._checar_atendente(interaction):
            return await self._resposta_sem_permissao(interaction)
        pedido = db.obter_pedido(pedido_id.upper())
        if not pedido:
            return await interaction.response.send_message("Pedido não encontrado.", ephemeral=True)
        db.ajustar_estoque(pedido["produto_id"], pedido["tamanho"], pedido["quantidade"])
        await self._mudar_status(interaction, pedido_id, "recusado", "🔴 Pagamento recusado (estoque devolvido)")

    @pedido_group.command(name="preparar", description="Marcar pedido como em preparação")
    async def pedido_preparar(self, interaction: discord.Interaction, pedido_id: str):
        await self._mudar_status(interaction, pedido_id, "em_preparacao", "📦 Pedido em preparação")

    @pedido_group.command(name="enviar", description="Marcar pedido como enviado")
    async def pedido_enviar(self, interaction: discord.Interaction, pedido_id: str, rastreio: str = ""):
        if rastreio:
            db.atualizar_pedido(pedido_id.upper(), rastreio=rastreio)
        await self._mudar_status(interaction, pedido_id, "enviado", "🚚 Pedido enviado")

    @pedido_group.command(name="finalizar", description="Marcar pedido como finalizado")
    async def pedido_finalizar(self, interaction: discord.Interaction, pedido_id: str):
        await self._mudar_status(interaction, pedido_id, "finalizado", "✅ Pedido finalizado")

    @pedido_group.command(name="cancelar", description="Cancelar um pedido")
    async def pedido_cancelar_atendente(self, interaction: discord.Interaction, pedido_id: str):
        if not self._checar_atendente(interaction):
            return await self._resposta_sem_permissao(interaction)
        pedido = db.obter_pedido(pedido_id.upper())
        if not pedido:
            return await interaction.response.send_message("Pedido não encontrado.", ephemeral=True)
        if pedido["status"] not in ("finalizado", "cancelado"):
            db.ajustar_estoque(pedido["produto_id"], pedido["tamanho"], pedido["quantidade"])
        await self._mudar_status(interaction, pedido_id, "cancelado", "❌ Pedido cancelado")

    @pedido_group.command(name="reabrir", description="Reabrir um pedido cancelado/recusado")
    async def pedido_reabrir(self, interaction: discord.Interaction, pedido_id: str):
        await self._mudar_status(interaction, pedido_id, "aguardando_pagamento", "🔓 Pedido reaberto")

    @pedido_group.command(name="observacao", description="Adicionar uma observação interna ao pedido")
    async def pedido_observacao(self, interaction: discord.Interaction, pedido_id: str, texto: str):
        if not self._checar_atendente(interaction):
            return await self._resposta_sem_permissao(interaction)
        pedido = db.obter_pedido(pedido_id.upper())
        if not pedido:
            return await interaction.response.send_message("Pedido não encontrado.", ephemeral=True)
        nova_obs = (pedido.get("observacoes") or "") + f"\n[{interaction.user}]: {texto}"
        db.atualizar_pedido(pedido["id"], observacoes=nova_obs.strip())
        await interaction.response.send_message("📝 Observação adicionada.", ephemeral=True)

    # ---------------- /cliente ----------------
    @cliente_group.command(name="consultar", description="Ver dados de um cliente")
    async def cliente_consultar(self, interaction: discord.Interaction, usuario: discord.Member):
        if not self._checar_atendente(interaction):
            return await self._resposta_sem_permissao(interaction)
        pedidos = db.pedidos_do_cliente(usuario.id)
        embed = discord.Embed(title=f"👤 {usuario}", color=discord.Color.blurple())
        embed.add_field(name="Total de pedidos", value=str(len(pedidos)))
        if pedidos:
            ultimo = pedidos[0]
            embed.add_field(name="Último pedido", value=f"{ultimo['id']} ({embeds.status_label(ultimo['status'])})")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @cliente_group.command(name="pedidos", description="Listar todos os pedidos de um cliente")
    async def cliente_pedidos(self, interaction: discord.Interaction, usuario: discord.Member):
        if not self._checar_atendente(interaction):
            return await self._resposta_sem_permissao(interaction)
        pedidos = db.pedidos_do_cliente(usuario.id)
        if not pedidos:
            return await interaction.response.send_message("Este cliente não tem pedidos.", ephemeral=True)
        texto = "\n".join(f"{p['id']} — {embeds.status_label(p['status'])} — R$ {p['valor_total']:.2f}" for p in pedidos[:25])
        await interaction.response.send_message(texto, ephemeral=True)

    # ---------------- /rastreio-atendente ----------------
    @rastreio_group.command(name="adicionar", description="Adicionar código de rastreio a um pedido")
    async def rastreio_adicionar(self, interaction: discord.Interaction, pedido_id: str, codigo: str):
        if not self._checar_atendente(interaction):
            return await self._resposta_sem_permissao(interaction)
        await interaction.response.defer(ephemeral=True, thinking=True)
        db.atualizar_pedido(pedido_id.upper(), rastreio=codigo)
        pedido = db.obter_pedido(pedido_id.upper())
        from cogs import notifications
        await notifications.notificar_status(interaction.guild, pedido)
        await interaction.followup.send(f"📮 Rastreio adicionado ao pedido {pedido_id.upper()}.", ephemeral=True)

    @rastreio_group.command(name="atualizar", description="Atualizar o código de rastreio de um pedido")
    async def rastreio_atualizar(self, interaction: discord.Interaction, pedido_id: str, codigo: str):
        await self.rastreio_adicionar.callback(self, interaction, pedido_id, codigo)

    # Nota: "/produto consultar" e "/estoque consultar" (disponíveis para atendentes)
    # ficam no cog admin.py junto com o restante dos comandos desses dois grupos,
    # para evitar dois cogs registrando o mesmo app_commands.Group.


async def setup(bot: commands.Bot):
    await bot.add_cog(Orders(bot))
