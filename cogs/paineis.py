import discord
from discord import app_commands
from discord.ext import commands

import database as db
from utils import embeds
from utils.permissions import is_ceo, is_atendente

from cogs.store import ProdutoView, mostrar_resumo  # reaproveita o fluxo de compra já existente
from cogs.tickets import criar_canal_ticket, CATEGORIAS_TICKET


# ------------------------------------------------------------------
# Painel do Cliente
# ------------------------------------------------------------------
class RastreioModal(discord.ui.Modal, title="Rastrear pedido"):
    pedido_id = discord.ui.TextInput(label="Número do pedido (ex: PED-00001)", max_length=20)

    async def on_submit(self, interaction: discord.Interaction):
        pedido = db.obter_pedido(self.pedido_id.value.strip().upper())
        if not pedido or pedido["cliente_id"] != interaction.user.id:
            return await interaction.response.send_message("Pedido não encontrado.", ephemeral=True)
        rastreio = pedido.get("rastreio") or "Ainda sem código de rastreio."
        await interaction.response.send_message(
            f"🚚 **{pedido['id']}** — {embeds.status_label(pedido['status'])}\n📮 Rastreio: {rastreio}",
            ephemeral=True,
        )


class SuporteCategoriaSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=c, value=c) for c in CATEGORIAS_TICKET]
        super().__init__(placeholder="Escolha a categoria do seu ticket...", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        canal = await criar_canal_ticket(interaction.guild, interaction.user, self.values[0])
        embed = discord.Embed(
            title=f"🎫 Ticket - {self.values[0]}",
            description=f"Olá {interaction.user.mention}! Descreva sua solicitação. Um atendente já foi notificado.",
            color=discord.Color.blurple(),
        )
        from cogs.tickets import TicketControlView
        await canal.send(embed=embed, view=TicketControlView())
        await interaction.followup.send(f"🎫 Ticket criado: {canal.mention}", ephemeral=True)


class SuporteCategoriaView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(SuporteCategoriaSelect())


class PainelClienteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Comprar", emoji="🛒", style=discord.ButtonStyle.success, custom_id="painel:comprar")
    async def comprar(self, interaction: discord.Interaction, button: discord.ui.Button):
        produtos = db.listar_produtos()
        if not produtos:
            return await interaction.response.send_message("Nenhum produto disponível no momento.", ephemeral=True)
        await interaction.response.send_message("🛒 Escolha o produto:", view=ProdutoView(produtos), ephemeral=True)

    @discord.ui.button(label="Catálogo", emoji="👕", style=discord.ButtonStyle.primary, custom_id="painel:catalogo")
    async def catalogo(self, interaction: discord.Interaction, button: discord.ui.Button):
        produtos = db.listar_produtos()
        if not produtos:
            return await interaction.response.send_message("Catálogo vazio no momento.", ephemeral=True)
        embeds_lista = []
        for p in produtos[:10]:
            disponiveis = db.tamanhos_disponiveis(p["id"])
            tamanhos_txt = ", ".join(disponiveis.keys()) if disponiveis else "🔴 ESGOTADO"
            marca = "⭐ " if p["destaque"] else ""
            embed = discord.Embed(
                title=f"{marca}{p['nome']} — R$ {p['preco_venda']:.2f}",
                description=f"Tamanhos: {tamanhos_txt}\n{p['descricao']}",
                color=discord.Color.blurple(),
            )
            if p.get("imagem_url"):
                embed.set_image(url=p["imagem_url"])
            embeds_lista.append(embed)
        await interaction.response.send_message(embeds=embeds_lista, ephemeral=True)

    @discord.ui.button(label="Meu pedido", emoji="📦", style=discord.ButtonStyle.secondary, custom_id="painel:meupedido")
    async def meupedido(self, interaction: discord.Interaction, button: discord.ui.Button):
        pedidos = db.pedidos_do_cliente(interaction.user.id)
        if not pedidos:
            return await interaction.response.send_message("Você ainda não fez nenhum pedido.", ephemeral=True)
        await interaction.response.send_message(embed=embeds.embed_resumo_pedido(pedidos[0]), ephemeral=True)

    @discord.ui.button(label="Rastrear", emoji="🚚", style=discord.ButtonStyle.secondary, custom_id="painel:rastrear")
    async def rastrear(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RastreioModal())

    @discord.ui.button(label="Suporte", emoji="🎫", style=discord.ButtonStyle.danger, custom_id="painel:suporte")
    async def suporte(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Escolha a categoria do seu atendimento:", view=SuporteCategoriaView(), ephemeral=True
        )


# ------------------------------------------------------------------
# Painel do Atendente
# ------------------------------------------------------------------
class PedidoIdModal(discord.ui.Modal, title="Consultar pedido"):
    pedido_id = discord.ui.TextInput(label="Número do pedido (ex: PED-00001)", max_length=20)

    async def on_submit(self, interaction: discord.Interaction):
        pedido = db.obter_pedido(self.pedido_id.value.strip().upper())
        if not pedido:
            return await interaction.response.send_message("Pedido não encontrado.", ephemeral=True)
        await interaction.response.send_message(embed=embeds.embed_resumo_pedido(pedido), ephemeral=True)


class ClienteIdModal(discord.ui.Modal, title="Consultar cliente"):
    usuario_id = discord.ui.TextInput(label="ID do usuário do Discord", max_length=25)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            uid = int(self.usuario_id.value.strip())
        except ValueError:
            return await interaction.response.send_message("ID inválido — precisa ser só números.", ephemeral=True)
        pedidos = db.pedidos_do_cliente(uid)
        if not pedidos:
            return await interaction.response.send_message("Esse cliente não tem pedidos.", ephemeral=True)
        texto = "\n".join(
            f"{p['id']} — {embeds.status_label(p['status'])} — R$ {p['valor_total']:.2f}" for p in pedidos[:20]
        )
        await interaction.response.send_message(f"<@{uid}>\n{texto}", ephemeral=True)


class RastreioAdicionarModal(discord.ui.Modal, title="Adicionar rastreio"):
    pedido_id = discord.ui.TextInput(label="Número do pedido", max_length=20)
    codigo = discord.ui.TextInput(label="Código de rastreio", max_length=60)

    async def on_submit(self, interaction: discord.Interaction):
        pid = self.pedido_id.value.strip().upper()
        pedido = db.obter_pedido(pid)
        if not pedido:
            return await interaction.response.send_message("Pedido não encontrado.", ephemeral=True)
        db.atualizar_pedido(pid, rastreio=self.codigo.value)
        pedido = db.obter_pedido(pid)
        from cogs import notifications
        await notifications.notificar_status(interaction.guild, pedido)
        await interaction.response.send_message(f"📮 Rastreio adicionado ao pedido {pid}.", ephemeral=True)


class EstoqueConsultarModal(discord.ui.Modal, title="Consultar estoque"):
    produto_id = discord.ui.TextInput(label="ID do produto", max_length=10)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            pid = int(self.produto_id.value.strip())
        except ValueError:
            return await interaction.response.send_message("ID inválido — precisa ser um número.", ephemeral=True)
        produto = db.obter_produto(pid)
        if not produto:
            return await interaction.response.send_message("Produto não encontrado.", ephemeral=True)
        estoque = db.obter_estoque(pid)
        texto = "\n".join(f"{t}: {q}" for t, q in estoque.items()) or "Sem estoque cadastrado."
        await interaction.response.send_message(f"👕 **{produto['nome']}**\n📦 Estoque:\n{texto}", ephemeral=True)


class PainelAtendenteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Pedidos", emoji="📋", style=discord.ButtonStyle.primary, custom_id="painel_at:pedidos")
    async def pedidos(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_atendente(interaction.user):
            return await interaction.response.send_message("🚫 Apenas atendentes ou o CEO podem usar este painel.", ephemeral=True)
        await interaction.response.send_modal(PedidoIdModal())

    @discord.ui.button(label="Tickets", emoji="🎫", style=discord.ButtonStyle.primary, custom_id="painel_at:tickets")
    async def tickets(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_atendente(interaction.user):
            return await interaction.response.send_message("🚫 Apenas atendentes ou o CEO podem usar este painel.", ephemeral=True)
        await interaction.response.send_message(
            "🎫 Os botões de **Assumir / Transferir / Fechar** ficam dentro de cada canal de ticket. "
            "Entre no ticket que quer gerenciar e use os botões (ou `/ticket assumir|transferir|fechar|reabrir`) lá dentro.",
            ephemeral=True,
        )

    @discord.ui.button(label="Clientes", emoji="👥", style=discord.ButtonStyle.secondary, custom_id="painel_at:clientes")
    async def clientes(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_atendente(interaction.user):
            return await interaction.response.send_message("🚫 Apenas atendentes ou o CEO podem usar este painel.", ephemeral=True)
        await interaction.response.send_modal(ClienteIdModal())

    @discord.ui.button(label="Rastreamento", emoji="🚚", style=discord.ButtonStyle.secondary, custom_id="painel_at:rastreio")
    async def rastreamento(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_atendente(interaction.user):
            return await interaction.response.send_message("🚫 Apenas atendentes ou o CEO podem usar este painel.", ephemeral=True)
        await interaction.response.send_modal(RastreioAdicionarModal())

    @discord.ui.button(label="Estoque", emoji="📦", style=discord.ButtonStyle.secondary, custom_id="painel_at:estoque")
    async def estoque(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_atendente(interaction.user):
            return await interaction.response.send_message("🚫 Apenas atendentes ou o CEO podem usar este painel.", ephemeral=True)
        await interaction.response.send_modal(EstoqueConsultarModal())


# ------------------------------------------------------------------
# Painel do CEO
# ------------------------------------------------------------------
class PainelCEOView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Dashboard", emoji="📊", style=discord.ButtonStyle.success, custom_id="painel_ceo:dashboard")
    async def dashboard(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message("🚫 Apenas o CEO pode usar este painel.", ephemeral=True)
        admin_cog = interaction.client.get_cog("Admin")
        await admin_cog.dashboard.callback(admin_cog, interaction)

    @discord.ui.button(label="Produtos", emoji="👕", style=discord.ButtonStyle.primary, custom_id="painel_ceo:produtos")
    async def produtos(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message("🚫 Apenas o CEO pode usar este painel.", ephemeral=True)
        produtos = db.listar_produtos(apenas_visiveis=False)
        if not produtos:
            texto = "Nenhum produto cadastrado."
        else:
            texto = "\n".join(
                f"`{p['id']}` {p['nome']} — venda R$ {p['preco_venda']:.2f} / custo R$ {p['preco_custo']:.2f} "
                f"{'🙈 oculto' if p['oculto'] else ''} {'⭐' if p['destaque'] else ''}"
                for p in produtos
            )
        texto += "\n\nPara cadastrar/editar produtos use `/produto adicionar`, `/produto editar` ou `/produto importar` (planilha CSV) — o Discord não permite formulários com tantos campos num botão."
        await interaction.response.send_message(texto[:1900], ephemeral=True)

    @discord.ui.button(label="Estoque", emoji="📦", style=discord.ButtonStyle.primary, custom_id="painel_ceo:estoque")
    async def estoque(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message("🚫 Apenas o CEO pode usar este painel.", ephemeral=True)
        admin_cog = interaction.client.get_cog("Admin")
        await admin_cog.estoque_alerta.callback(admin_cog, interaction)

    @discord.ui.button(label="Pedidos", emoji="📋", style=discord.ButtonStyle.secondary, custom_id="painel_ceo:pedidos")
    async def pedidos(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message("🚫 Apenas o CEO pode usar este painel.", ephemeral=True)
        pedidos = db.buscar_pedidos()
        if not pedidos:
            return await interaction.response.send_message("Nenhum pedido encontrado.", ephemeral=True)
        texto = "\n".join(
            f"{p['id']} — {embeds.status_label(p['status'])} — R$ {p['valor_total']:.2f}" for p in pedidos[:25]
        )
        await interaction.response.send_message(f"📋 Últimos pedidos:\n{texto}", ephemeral=True)

    @discord.ui.button(label="Financeiro", emoji="💵", style=discord.ButtonStyle.secondary, custom_id="painel_ceo:financeiro")
    async def financeiro(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message("🚫 Apenas o CEO pode usar este painel.", ephemeral=True)
        admin_cog = interaction.client.get_cog("Admin")
        pedidos = admin_cog._pedidos_por_periodo("total")
        faturamento = sum(p["valor_total"] for p in pedidos)
        custos = sum((db.obter_produto(p["produto_id"]) or {}).get("preco_custo", 0) * p["quantidade"] for p in pedidos)
        lucro = faturamento - custos
        await interaction.response.send_message(
            f"💰 Faturamento: R$ {faturamento:.2f}\n💵 Custos: R$ {custos:.2f}\n📈 Lucro: R$ {lucro:.2f}",
            ephemeral=True,
        )

    @discord.ui.button(label="Cupons", emoji="🎟️", style=discord.ButtonStyle.secondary, custom_id="painel_ceo:cupons")
    async def cupons(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message("🚫 Apenas o CEO pode usar este painel.", ephemeral=True)
        cupons = db.listar_cupons()
        if not cupons:
            texto = "Nenhum cupom cadastrado."
        else:
            texto = "\n".join(
                f"{c['codigo']} — {c['desconto_percentual']}% — usos {c['usos']}/{c['limite_usos'] or '∞'}" for c in cupons
            )
        texto += "\n\nPara criar/editar use `/cupom-admin criar` ou `/cupom-admin editar`."
        await interaction.response.send_message(texto, ephemeral=True)

    @discord.ui.button(label="Frete", emoji="🚚", style=discord.ButtonStyle.secondary, custom_id="painel_ceo:frete")
    async def frete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message("🚫 Apenas o CEO pode usar este painel.", ephemeral=True)
        regioes = db.listar_regioes_frete()
        if not regioes:
            texto = "Nenhuma região configurada."
        else:
            texto = "\n".join(f"{r['nome_regiao']}: R$ {r['valor']:.2f}" for r in regioes)
        texto += "\n\nPara configurar use `/frete configurar`."
        await interaction.response.send_message(texto, ephemeral=True)

    @discord.ui.button(label="Tickets", emoji="🎫", style=discord.ButtonStyle.secondary, custom_id="painel_ceo:tickets")
    async def tickets(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message("🚫 Apenas o CEO pode usar este painel.", ephemeral=True)
        await interaction.response.send_message(
            "🎫 Os botões de **Assumir / Transferir / Fechar** ficam dentro de cada canal de ticket.",
            ephemeral=True,
        )

    @discord.ui.button(label="Clientes", emoji="👥", style=discord.ButtonStyle.secondary, custom_id="painel_ceo:clientes")
    async def clientes(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message("🚫 Apenas o CEO pode usar este painel.", ephemeral=True)
        await interaction.response.send_modal(ClienteIdModal())

    @discord.ui.button(label="Configurações", emoji="⚙️", style=discord.ButtonStyle.danger, custom_id="painel_ceo:config")
    async def configuracoes(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message("🚫 Apenas o CEO pode usar este painel.", ephemeral=True)
        import config
        await interaction.response.send_message(
            f"⚙️ Chave PIX: `{config.PIX_KEY}`\n"
            f"Cargo CEO: <@&{config.CEO_ROLE_ID}>\nCargo Atendente: <@&{config.ATENDENTE_ROLE_ID}>\n"
            f"Estoque baixo a partir de: {config.ESTOQUE_BAIXO_LIMITE} unidade(s)\n\n"
            "Esses valores são alterados nas Variables do Railway, não pelo bot.",
            ephemeral=True,
        )


# ------------------------------------------------------------------
# Cog: comandos para fixar os painéis num canal
# ------------------------------------------------------------------
class Paineis(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(PainelClienteView())
        self.bot.add_view(PainelAtendenteView())
        self.bot.add_view(PainelCEOView())

    @app_commands.command(name="painel-cliente", description="Fixar o painel de autoatendimento do cliente neste canal (CEO)")
    async def painel_cliente(self, interaction: discord.Interaction):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message("🚫 Apenas o CEO pode usar este comando.", ephemeral=True)
        embed = discord.Embed(title="🎨 Painel do Cliente", description="Escolha uma opção abaixo:", color=discord.Color.blurple())
        await interaction.channel.send(embed=embed, view=PainelClienteView())
        await interaction.response.send_message("✅ Painel do cliente fixado neste canal.", ephemeral=True)

    @app_commands.command(name="painel-atendente", description="Fixar o painel do atendente neste canal (CEO)")
    async def painel_atendente(self, interaction: discord.Interaction):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message("🚫 Apenas o CEO pode usar este comando.", ephemeral=True)
        embed = discord.Embed(title="🎧 Painel do Atendente", description="Escolha uma opção abaixo:", color=discord.Color.green())
        await interaction.channel.send(embed=embed, view=PainelAtendenteView())
        await interaction.response.send_message("✅ Painel do atendente fixado neste canal.", ephemeral=True)

    @app_commands.command(name="painel-ceo", description="Fixar o painel do CEO neste canal (CEO)")
    async def painel_ceo(self, interaction: discord.Interaction):
        if not is_ceo(interaction.user):
            return await interaction.response.send_message("🚫 Apenas o CEO pode usar este comando.", ephemeral=True)
        embed = discord.Embed(title="👑 Painel do CEO", description="Escolha uma opção abaixo:", color=discord.Color.gold())
        await interaction.channel.send(embed=embed, view=PainelCEOView())
        await interaction.response.send_message("✅ Painel do CEO fixado neste canal.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Paineis(bot))
