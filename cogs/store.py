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
