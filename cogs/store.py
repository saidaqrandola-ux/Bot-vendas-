import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from utils import embeds, pix
from utils.permissions import is_atendente
from cogs.tickets import criar_canal_ticket

COMPROVANTE_EXTENSOES = (".png", ".jpg", ".jpeg", ".pdf")


# ------------------------------------------------------------------
# Passo 1 - Produto
# ------------------------------------------------------------------
class ProdutoSelect(discord.ui.Select):
    def __init__(self, produtos):
        options = [
            discord.SelectOption(
                label=p["nome"][:100],
                description=f"R$ {p['preco_venda']:.2f}",
                value=str(p["id"]),
            )
            for p in produtos
        ]
        super().__init__(placeholder="Escolha um produto...", options=options)

    async def callback(self, interaction: discord.Interaction):
        produto_id = int(self.values[0])
        produto = db.obter_produto(produto_id)
        disponiveis = db.tamanhos_disponiveis(produto_id)
        if not disponiveis:
            return await interaction.response.edit_message(
                content="🔴 Este produto está **ESGOTADO** no momento.", embed=None, view=None
            )
        carrinho = {"produto_id": produto_id, "produto_nome": produto["nome"], "preco_unitario": produto["preco_venda"]}
        await interaction.response.edit_message(
            content=f"👕 **{produto['nome']}** selecionado. Agora escolha o tamanho:",
            view=TamanhoView(disponiveis, carrinho, produto),
        )


class ProdutoView(discord.ui.View):
    def __init__(self, produtos):
        super().__init__(timeout=300)
        self.add_item(ProdutoSelect(produtos))


# ------------------------------------------------------------------
# Passo 2 - Tamanho
# ------------------------------------------------------------------
class TamanhoSelect(discord.ui.Select):
    def __init__(self, disponiveis, carrinho, produto):
        self.carrinho = carrinho
        self.produto = produto
        options = [
            discord.SelectOption(label=tamanho, description=f"{qtd} em estoque", value=tamanho)
            for tamanho, qtd in disponiveis.items()
        ]
        super().__init__(placeholder="Escolha o tamanho...", options=options)

    async def callback(self, interaction: discord.Interaction):
        tamanho = self.values[0]
        self.carrinho["tamanho"] = tamanho
        self.carrinho["estoque_disponivel"] = db.obter_estoque(self.produto["id"]).get(tamanho, 0)
        await interaction.response.send_modal(QuantidadeModal(self.carrinho, self.produto))


class TamanhoView(discord.ui.View):
    def __init__(self, disponiveis, carrinho, produto):
        super().__init__(timeout=300)
        self.add_item(TamanhoSelect(disponiveis, carrinho, produto))


# ------------------------------------------------------------------
# Passo 3 - Quantidade
# ------------------------------------------------------------------
class QuantidadeModal(discord.ui.Modal, title="Quantidade"):
    quantidade = discord.ui.TextInput(label="Quantas unidades?", placeholder="Ex: 1", max_length=3)

    def __init__(self, carrinho, produto):
        super().__init__()
        self.carrinho = carrinho
        self.produto = produto

    async def on_submit(self, interaction: discord.Interaction):
        try:
            qtd = int(self.quantidade.value)
            assert qtd > 0
        except (ValueError, AssertionError):
            return await interaction.response.send_message("⚠️ Informe um número inteiro maior que zero.", ephemeral=True)

        if qtd > self.carrinho["estoque_disponivel"]:
            return await interaction.response.send_message(
                f"⚠️ Só temos {self.carrinho['estoque_disponivel']} unidade(s) desse tamanho em estoque.",
                ephemeral=True,
            )

        self.carrinho["quantidade"] = qtd

        if self.produto["permite_personalizacao"]:
            await interaction.response.send_modal(PersonalizacaoModal(self.carrinho))
        else:
            self.carrinho["personalizacao_nome"] = None
            self.carrinho["personalizacao_numero"] = None
            await mostrar_resumo(interaction, self.carrinho)


# ------------------------------------------------------------------
# Passo 4 - Personalização
# ------------------------------------------------------------------
class PersonalizacaoModal(discord.ui.Modal, title="Personalização"):
    nome = discord.ui.TextInput(label="Nome para a camisa", required=False, max_length=30)
    numero = discord.ui.TextInput(label="Número para a camisa", required=False, max_length=3)

    def __init__(self, carrinho):
        super().__init__()
        self.carrinho = carrinho

    async def on_submit(self, interaction: discord.Interaction):
        self.carrinho["personalizacao_nome"] = self.nome.value or None
        self.carrinho["personalizacao_numero"] = self.numero.value or None
        await mostrar_resumo(interaction, self.carrinho)


# ------------------------------------------------------------------
# Passo 5 - Resumo do pedido
# ------------------------------------------------------------------
def calcular_total(carrinho):
    subtotal = carrinho["preco_unitario"] * carrinho["quantidade"]
    desconto = carrinho.get("desconto", 0)
    frete = carrinho.get("frete", 0)
    return round(subtotal - desconto + frete, 2)


async def mostrar_resumo(interaction: discord.Interaction, carrinho: dict):
    carrinho["valor_total"] = calcular_total(carrinho)
    embed = embeds.embed_resumo_pedido(
        {
            "id": "(pré-visualização)",
            "produto_nome": carrinho["produto_nome"],
            "tamanho": carrinho["tamanho"],
            "quantidade": carrinho["quantidade"],
            "personalizacao_nome": carrinho.get("personalizacao_nome"),
            "personalizacao_numero": carrinho.get("personalizacao_numero"),
            "cupom_codigo": carrinho.get("cupom_codigo"),
            "desconto": carrinho.get("desconto", 0),
            "frete": carrinho.get("frete", 0),
            "valor_total": carrinho["valor_total"],
            "status": "aguardando_pagamento",
        }
    )
    view = ResumoView(carrinho)
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class CupomModal(discord.ui.Modal, title="Aplicar cupom"):
    codigo = discord.ui.TextInput(label="Código do cupom", max_length=30)

    def __init__(self, carrinho):
        super().__init__()
        self.carrinho = carrinho

    async def on_submit(self, interaction: discord.Interaction):
        cupom = db.obter_cupom(self.codigo.value)
        subtotal = self.carrinho["preco_unitario"] * self.carrinho["quantidade"]
        if not cupom:
            return await interaction.response.send_message("⚠️ Cupom não encontrado.", ephemeral=True)
        if cupom["limite_usos"] and cupom["usos"] >= cupom["limite_usos"]:
            return await interaction.response.send_message("⚠️ Este cupom já atingiu o limite de usos.", ephemeral=True)
        if subtotal < cupom["valor_minimo"]:
            return await interaction.response.send_message(
                f"⚠️ Esse cupom exige um pedido mínimo de R$ {cupom['valor_minimo']:.2f}.", ephemeral=True
            )
        self.carrinho["cupom_codigo"] = cupom["codigo"]
        self.carrinho["desconto"] = round(subtotal * (cupom["desconto_percentual"] / 100), 2)
        await interaction.response.defer(ephemeral=True)
        await mostrar_resumo(interaction, self.carrinho)


class ResumoView(discord.ui.View):
    def __init__(self, carrinho):
        super().__init__(timeout=300)
        self.carrinho = carrinho

    @discord.ui.button(label="Continuar", emoji="✅", style=discord.ButtonStyle.success)
    async def continuar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(FormularioModal1(self.carrinho))

    @discord.ui.button(label="Aplicar cupom", emoji="🎟️", style=discord.ButtonStyle.secondary)
    async def cupom(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CupomModal(self.carrinho))

    @discord.ui.button(label="Alterar pedido", emoji="✏️", style=discord.ButtonStyle.secondary)
    async def alterar(self, interaction: discord.Interaction, button: discord.ui.Button):
        produtos = db.listar_produtos()
        await interaction.response.edit_message(content="🛒 Vamos recomeçar. Escolha o produto:", embed=None, view=ProdutoView(produtos))

    @discord.ui.button(label="Cancelar", emoji="❌", style=discord.ButtonStyle.danger)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Pedido cancelado.", embed=None, view=None)


# ------------------------------------------------------------------
# Passo 6 - Formulário obrigatório (3 modais encadeados, limite de 5 campos por modal)
# ------------------------------------------------------------------
class FormularioModal1(discord.ui.Modal, title="Seus dados (1/3)"):
    nome_completo = discord.ui.TextInput(label="Nome completo", max_length=100)
    endereco = discord.ui.TextInput(label="Endereço", max_length=100)
    numero = discord.ui.TextInput(label="Número", max_length=10)
    complemento = discord.ui.TextInput(label="Complemento / apartamento", required=False, max_length=50)
    cidade = discord.ui.TextInput(label="Cidade", max_length=60)

    def __init__(self, carrinho):
        super().__init__()
        self.carrinho = carrinho
        for campo in ("nome_completo", "endereco", "numero", "complemento", "cidade"):
            valor = carrinho.get(campo)
            if valor:
                getattr(self, campo).default = valor

    async def on_submit(self, interaction: discord.Interaction):
        self.carrinho["nome_completo"] = self.nome_completo.value
        self.carrinho["endereco"] = self.endereco.value
        self.carrinho["numero"] = self.numero.value
        self.carrinho["complemento"] = self.complemento.value
        self.carrinho["cidade"] = self.cidade.value
        await interaction.response.send_modal(FormularioModal2(self.carrinho))


class FormularioModal2(discord.ui.Modal, title="Seus dados (2/3)"):
    estado = discord.ui.TextInput(label="Estado / Província", max_length=40)
    pais = discord.ui.TextInput(label="País", max_length=40)
    cep = discord.ui.TextInput(label="CEP", max_length=15)
    telefone = discord.ui.TextInput(label="Número de telefone", max_length=20)
    cpf = discord.ui.TextInput(label="CPF", max_length=20)

    def __init__(self, carrinho):
        super().__init__()
        self.carrinho = carrinho
        for campo in ("estado", "pais", "cep", "telefone", "cpf"):
            valor = carrinho.get(campo)
            if valor:
                getattr(self, campo).default = valor

    async def on_submit(self, interaction: discord.Interaction):
        self.carrinho["estado"] = self.estado.value
        self.carrinho["pais"] = self.pais.value
        self.carrinho["cep"] = self.cep.value
        self.carrinho["telefone"] = self.telefone.value
        self.carrinho["cpf"] = self.cpf.value
        await interaction.response.send_modal(FormularioModal3(self.carrinho))


class FormularioModal3(discord.ui.Modal, title="Seus dados (3/3)"):
    email = discord.ui.TextInput(label="E-mail", max_length=100)

    def __init__(self, carrinho):
        super().__init__()
        self.carrinho = carrinho
        if carrinho.get("email"):
            self.email.default = carrinho["email"]

    async def on_submit(self, interaction: discord.Interaction):
        self.carrinho["email"] = self.email.value

        if self.carrinho.get("_editar_pedido_id"):
            campos = {
                k: self.carrinho[k]
                for k in (
                    "nome_completo", "endereco", "numero", "complemento", "cidade",
                    "estado", "pais", "cep", "telefone", "cpf", "email",
                )
            }
            db.atualizar_pedido(self.carrinho["_editar_pedido_id"], **campos)
            return await interaction.response.send_message(
                f"✅ Dados do pedido {self.carrinho['_editar_pedido_id']} atualizados.", ephemeral=True
            )

        # frete automático se houver região configurada para o estado informado
        frete_regiao = db.valor_frete_para_estado(self.carrinho.get("estado", ""))
        if frete_regiao is not None:
            self.carrinho["frete"] = frete_regiao
            self.carrinho["valor_total"] = calcular_total(self.carrinho)
        await interaction.response.send_message(
            embed=embeds.embed_confirmacao_dados(self.carrinho),
            view=ConfirmacaoView(self.carrinho),
            ephemeral=True,
        )
        # ------------------------------------------------------------------
# Passo 7 - Confirmação dos dados
# ------------------------------------------------------------------
class ConfirmacaoView(discord.ui.View):
    def __init__(self, carrinho):
        super().__init__(timeout=300)
        self.carrinho = carrinho

    @discord.ui.button(label="Confirmar dados", emoji="✅", style=discord.ButtonStyle.success)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        await finalizar_pedido(interaction, self.carrinho)

    @discord.ui.button(label="Corrigir dados", emoji="✏️", style=discord.ButtonStyle.secondary)
    async def corrigir(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(FormularioModal1(self.carrinho))


# ------------------------------------------------------------------
# Passo 8 - Criação do pedido + PIX
# ------------------------------------------------------------------
class PagamentoView(discord.ui.View):
    """View persistente anexada à mensagem de pagamento dentro do canal de ticket do pedido."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Copiar PIX", emoji="📋", style=discord.ButtonStyle.primary, custom_id="pix:copiar")
    async def copiar(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = db.obter_ticket(interaction.channel_id)
        if not ticket:
            return await interaction.response.send_message("Pedido não encontrado para este canal.", ephemeral=True)
        pedido = db.obter_pedido(ticket["pedido_id"])
        payload = pix.gerar_payload_pix(pedido["valor_total"], pedido["id"])
        await interaction.response.send_message(f"📋 Copia e Cola PIX:\n```{payload}```", ephemeral=True)

    @discord.ui.button(label="Ver QR Code", emoji="📱", style=discord.ButtonStyle.primary, custom_id="pix:qrcode")
    async def qrcode(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = db.obter_ticket(interaction.channel_id)
        if not ticket:
            return await interaction.response.send_message("Pedido não encontrado para este canal.", ephemeral=True)
        pedido = db.obter_pedido(ticket["pedido_id"])
        payload = pix.gerar_payload_pix(pedido["valor_total"], pedido["id"])
        buffer = pix.gerar_qrcode_bytes(payload)
        await interaction.response.send_message(
            file=discord.File(buffer, filename="pix_qrcode.png"), ephemeral=True
        )

    @discord.ui.button(label="Já fiz o pagamento", emoji="✅", style=discord.ButtonStyle.success, custom_id="pix:pago")
    async def pago(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = db.obter_ticket(interaction.channel_id)
        if not ticket:
            return await interaction.response.send_message("Pedido não encontrado para este canal.", ephemeral=True)
        pedido = db.obter_pedido(ticket["pedido_id"])
        if pedido["status"] != "aguardando_pagamento":
            return await interaction.response.send_message(
                f"Este pedido já está com status: {embeds.status_label(pedido['status'])}", ephemeral=True
            )
        await interaction.response.send_message(
            "📸 Envie o comprovante do pagamento aqui neste canal (PNG, JPG, JPEG ou PDF)."
        )


async def finalizar_pedido(interaction: discord.Interaction, carrinho: dict):
    guild = interaction.guild
    dados_pedido = {
        "cliente_id": interaction.user.id,
        "cliente_tag": str(interaction.user),
        "produto_id": carrinho["produto_id"],
        "produto_nome": carrinho["produto_nome"],
        "tamanho": carrinho["tamanho"],
        "quantidade": carrinho["quantidade"],
        "personalizacao_nome": carrinho.get("personalizacao_nome"),
        "personalizacao_numero": carrinho.get("personalizacao_numero"),
        "nome_completo": carrinho["nome_completo"],
        "endereco": carrinho["endereco"],
        "numero": carrinho["numero"],
        "complemento": carrinho.get("complemento"),
        "cidade": carrinho["cidade"],
        "estado": carrinho["estado"],
        "pais": carrinho["pais"],
        "cep": carrinho["cep"],
        "telefone": carrinho["telefone"],
        "cpf": carrinho["cpf"],
        "email": carrinho["email"],
        "cupom_codigo": carrinho.get("cupom_codigo"),
        "desconto": carrinho.get("desconto", 0),
        "frete": carrinho.get("frete", 0),
        "valor_total": calcular_total(carrinho),
    }

    # revalida estoque no momento exato da criação do pedido
    estoque_atual = db.obter_estoque(carrinho["produto_id"]).get(carrinho["tamanho"], 0)
    if carrinho["quantidade"] > estoque_atual:
        return await interaction.followup.send(
            "⚠️ O estoque mudou enquanto você preenchia os dados e não há mais unidades suficientes. "
            "Use /comprar novamente.",
            ephemeral=True,
        )

    pedido_id = db.criar_pedido(dados_pedido)
    db.ajustar_estoque(carrinho["produto_id"], carrinho["tamanho"], -carrinho["quantidade"])
    if carrinho.get("cupom_codigo"):
        db.incrementar_uso_cupom(carrinho["cupom_codigo"])

    canal = await criar_canal_ticket(guild, interaction.user, "Comprar", pedido_id)
    db.atualizar_ticket(canal.id, pedido_id=pedido_id)
    db.atualizar_pedido(pedido_id, ticket_channel_id=canal.id)

    pedido = db.obter_pedido(pedido_id)
    await canal.send(
        content=f"{interaction.user.mention} seu pedido foi criado com sucesso!",
        embed=embeds.embed_resumo_pedido(pedido),
    )
    payload = pix.gerar_payload_pix(pedido["valor_total"], pedido_id)
    buffer = pix.gerar_qrcode_bytes(payload)
    await canal.send(
        embed=embeds.embed_pagamento_pix(pedido["valor_total"], config.PIX_KEY),
        file=discord.File(buffer, filename="pix_qrcode.png"),
        view=PagamentoView(),
    )

    await interaction.followup.send(f"✅ Pedido **{pedido_id}** criado! Continue por aqui: {canal.mention}", ephemeral=True)

    # estoque baixo?
    novo_estoque = db.obter_estoque(carrinho["produto_id"]).get(carrinho["tamanho"], 0)
    from cogs import notifications
    await notifications.notificar_novo_pedido(guild, pedido)
    if novo_estoque == 0:
        await notifications.notificar_produto_esgotado(guild, carrinho["produto_nome"], carrinho["tamanho"])
    elif novo_estoque <= config.ESTOQUE_BAIXO_LIMITE:
        await notifications.notificar_estoque_baixo(guild, carrinho["produto_nome"], carrinho["tamanho"], novo_estoque)


# ------------------------------------------------------------------
# Cog
# ------------------------------------------------------------------
class Store(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(PagamentoView())

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        ticket = db.obter_ticket(message.channel.id)
        if not ticket or not ticket.get("pedido_id"):
            return
        pedido = db.obter_pedido(ticket["pedido_id"])
        if not pedido or pedido["status"] != "aguardando_pagamento" or message.author.id != pedido["cliente_id"]:
            return
        anexo_valido = next(
            (a for a in message.attachments if a.filename.lower().endswith(COMPROVANTE_EXTENSOES)), None
        )
        if not anexo_valido:
            return

        db.atualizar_pedido(pedido["id"], status="comprovante_enviado", comprovante_url=anexo_valido.url)
        await message.reply("📸 Comprovante recebido! Aguarde a análise da nossa equipe. ⏳")

        from cogs import notifications
        await notifications.notificar_comprovante_enviado(message.guild, pedido, anexo_valido)

    @app_commands.command(name="comprar", description="Iniciar uma compra")
    async def comprar(self, interaction: discord.Interaction):
        produtos = db.listar_produtos()
        if not produtos:
            return await interaction.response.send_message("Nenhum produto disponível no momento.", ephemeral=True)
        await interaction.response.send_message("🛒 Escolha o produto:", view=ProdutoView(produtos), ephemeral=True)

    @app_commands.command(name="catalogo", description="Ver o catálogo de produtos")
    async def catalogo(self, interaction: discord.Interaction):
        produtos = db.listar_produtos()
        if not produtos:
            return await interaction.response.send_message("Catálogo vazio no momento.", ephemeral=True)
        embed = discord.Embed(title="👕 Catálogo", color=discord.Color.blurple())
        for p in produtos:
            disponiveis = db.tamanhos_disponiveis(p["id"])
            tamanhos_txt = ", ".join(disponiveis.keys()) if disponiveis else "🔴 ESGOTADO"
            marca = "⭐ " if p["destaque"] else ""
            embed.add_field(
                name=f"{marca}{p['nome']} — R$ {p['preco_venda']:.2f}",
                value=f"Tamanhos: {tamanhos_txt}\n{p['descricao']}",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="tamanhos", description="Ver tamanhos disponíveis de um produto")
    async def tamanhos(self, interaction: discord.Interaction, produto: str):
        produtos = [p for p in db.listar_produtos() if produto.lower() in p["nome"].lower()]
        if not produtos:
            return await interaction.response.send_message("Produto não encontrado.", ephemeral=True)
        p = produtos[0]
        disponiveis = db.tamanhos_disponiveis(p["id"])
        texto = "\n".join(f"{t}: {q} disponíveis" for t, q in disponiveis.items()) or "🔴 ESGOTADO"
        await interaction.response.send_message(f"📏 **{p['nome']}**\n{texto}", ephemeral=True)

    @app_commands.command(name="meupedido", description="Ver detalhes do seu pedido mais recente")
    async def meupedido(self, interaction: discord.Interaction):
        pedidos = db.pedidos_do_cliente(interaction.user.id)
        if not pedidos:
            return await interaction.response.send_message("Você ainda não fez nenhum pedido.", ephemeral=True)
        await interaction.response.send_message(embed=embeds.embed_resumo_pedido(pedidos[0]), ephemeral=True)

    @app_commands.command(name="meuspedidos", description="Ver todos os seus pedidos")
    async def meuspedidos(self, interaction: discord.Interaction):
        pedidos = db.pedidos_do_cliente(interaction.user.id)
        if not pedidos:
            return await interaction.response.send_message("Você ainda não fez nenhum pedido.", ephemeral=True)
        embed = discord.Embed(title="📦 Seus pedidos", color=discord.Color.blurple())
        for p in pedidos[:20]:
            embed.add_field(
                name=f"{p['id']} — {p['produto_nome']}",
                value=f"{embeds.status_label(p['status'])} | R$ {p['valor_total']:.2f}",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="rastreio", description="Ver o rastreamento do seu pedido")
    async def rastreio(self, interaction: discord.Interaction, pedido_id: str):
        pedido = db.obter_pedido(pedido_id.upper())
        if not pedido or pedido["cliente_id"] != interaction.user.id:
            return await interaction.response.send_message("Pedido não encontrado.", ephemeral=True)
        rastreio = pedido.get("rastreio") or "Ainda sem código de rastreio."
        await interaction.response.send_message(
            f"🚚 **{pedido['id']}** — {embeds.status_label(pedido['status'])}\n📮 Rastreio: {rastreio}",
            ephemeral=True,
        )

    @app_commands.command(name="calcularfrete", description="Calcular o frete para o seu estado")
    async def calcularfrete(self, interaction: discord.Interaction, estado: str):
        valor = db.valor_frete_para_estado(estado)
        if valor is None:
            return await interaction.response.send_message(
                "Não temos frete configurado para esse estado ainda. Fale com o suporte.", ephemeral=True
            )
        await interaction.response.send_message(f"🚚 Frete para {estado.upper()}: R$ {valor:.2f}", ephemeral=True)

    @app_commands.command(name="cupom-consultar", description="Consultar se um cupom é válido")
    async def cupom(self, interaction: discord.Interaction, codigo: str):
        cupom = db.obter_cupom(codigo)
        if not cupom:
            return await interaction.response.send_message("Cupom não encontrado.", ephemeral=True)
        usos_restantes = "ilimitado" if not cupom["limite_usos"] else max(0, cupom["limite_usos"] - cupom["usos"])
        await interaction.response.send_message(
            f"🎟️ **{cupom['codigo']}** — {cupom['desconto_percentual']}% de desconto\n"
            f"Pedido mínimo: R$ {cupom['valor_minimo']:.2f} | Validade: {cupom['validade'] or '-'} | Usos restantes: {usos_restantes}",
            ephemeral=True,
        )

    @app_commands.command(name="perfil", description="Ver seu perfil de cliente")
    async def perfil(self, interaction: discord.Interaction):
        pedidos = db.pedidos_do_cliente(interaction.user.id)
        total_gasto = sum(p["valor_total"] for p in pedidos if p["status"] not in ("cancelado", "recusado"))
        embed = discord.Embed(title=f"👤 Perfil de {interaction.user.display_name}", color=discord.Color.blurple())
        embed.add_field(name="Pedidos feitos", value=str(len(pedidos)))
        embed.add_field(name="Total gasto", value=f"R$ {total_gasto:.2f}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="editar-dados", description="Corrigir os dados de um pedido ainda não pago")
    async def editar_dados(self, interaction: discord.Interaction, pedido_id: str):
        pedido = db.obter_pedido(pedido_id.upper())
        if not pedido or pedido["cliente_id"] != interaction.user.id:
            return await interaction.response.send_message("Pedido não encontrado.", ephemeral=True)
        if pedido["status"] != "aguardando_pagamento":
            return await interaction.response.send_message(
                "Esse pedido já avançou e não pode mais ter os dados editados por aqui. Abra um ticket em /suporte.",
                ephemeral=True,
            )
        dados = dict(pedido)
        dados["_editar_pedido_id"] = pedido["id"]
        await interaction.response.send_modal(FormularioModal1(dados))

    @app_commands.command(name="cancelar", description="Cancelar um pedido ainda não pago")
    async def cancelar(self, interaction: discord.Interaction, pedido_id: str):
        pedido = db.obter_pedido(pedido_id.upper())
        if not pedido or pedido["cliente_id"] != interaction.user.id:
            return await interaction.response.send_message("Pedido não encontrado.", ephemeral=True)
        if pedido["status"] not in ("aguardando_pagamento", "comprovante_enviado"):
            return await interaction.response.send_message(
                "Esse pedido já está em um estágio que não permite cancelamento automático. Abra um ticket.",
                ephemeral=True,
            )
        db.atualizar_pedido(pedido["id"], status="cancelado")
        db.ajustar_estoque(pedido["produto_id"], pedido["tamanho"], pedido["quantidade"])
        await interaction.response.send_message(f"❌ Pedido {pedido['id']} cancelado e estoque devolvido.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Store(bot))

