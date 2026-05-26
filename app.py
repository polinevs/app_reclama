import os
import uuid
from datetime import datetime
from io import BytesIO
from urllib.parse import urlencode

import streamlit as st
import pandas as pd
import plotly.express as px
import qrcode

from database import (
    conectar,
    criar_tabelas,
    criar_usuario_admin_padrao,
    autenticar_usuario,
    inserir_cliente,
    listar_clientes,
    inserir_lote,
    listar_lotes,
    inserir_reclamacao,
    listar_reclamacoes,
    buscar_reclamacao_por_id,
    atualizar_status_reclamacao,
    obter_indicadores_dashboard
)


# =========================================================
# CONFIGURAÇÃO INICIAL
# =========================================================

st.set_page_config(
    page_title="SGR Frutas",
    page_icon="🍑",
    layout="wide"
)

UPLOAD_DIR = "uploads/evidencias"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# =========================================================
# INICIALIZAÇÃO DO BANCO
# =========================================================

criar_tabelas()
criar_usuario_admin_padrao()


def criar_tabela_evidencias():
    """
    Cria a tabela de evidências caso ainda não exista.
    Esta função fica aqui para você não precisar alterar agora o database.py.
    Mais tarde, podemos mover essa função para o database.py.
    """
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS evidencias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reclamacao_id INTEGER NOT NULL,
        nome_arquivo TEXT NOT NULL,
        caminho_arquivo TEXT NOT NULL,
        tipo_arquivo TEXT,
        data_upload TEXT NOT NULL,
        FOREIGN KEY(reclamacao_id) REFERENCES reclamacoes(id)
    )
    """)

    conn.commit()
    conn.close()


criar_tabela_evidencias()


# =========================================================
# SESSION STATE
# =========================================================

if "usuario" not in st.session_state:
    st.session_state.usuario = None


# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================

def obter_parametro_url(nome, valor_padrao=""):
    """
    Lê parâmetros da URL.

    Exemplos:
    ?portal=cliente
    ?portal=cliente&lote=LOTE2026-001
    """
    try:
        valor = st.query_params.get(nome, valor_padrao)
        if isinstance(valor, list):
            return valor[0] if valor else valor_padrao
        return valor
    except Exception:
        return valor_padrao


def salvar_evidencia(reclamacao_id, arquivo):
    """
    Salva uma imagem/documento enviado pelo cliente e registra no banco.
    """
    if arquivo is None:
        return

    extensao = arquivo.name.split(".")[-1].lower()
    nome_unico = f"REC_{reclamacao_id}_{uuid.uuid4().hex}.{extensao}"
    caminho_arquivo = os.path.join(UPLOAD_DIR, nome_unico)

    with open(caminho_arquivo, "wb") as f:
        f.write(arquivo.getbuffer())

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO evidencias (
        reclamacao_id, nome_arquivo, caminho_arquivo, tipo_arquivo, data_upload
    )
    VALUES (?, ?, ?, ?, ?)
    """, (
        reclamacao_id,
        arquivo.name,
        caminho_arquivo,
        arquivo.type,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()


def buscar_id_reclamacao_por_codigo(codigo_reclamacao):
    """
    Busca o ID interno da reclamação a partir do código gerado.
    """
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT id
    FROM reclamacoes
    WHERE codigo_reclamacao = ?
    """, (codigo_reclamacao,))

    resultado = cursor.fetchone()
    conn.close()

    if resultado:
        return resultado[0]

    return None


def listar_evidencias_reclamacao(reclamacao_id):
    """
    Lista os arquivos enviados em uma reclamação.
    """
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT id, nome_arquivo, caminho_arquivo, tipo_arquivo, data_upload
    FROM evidencias
    WHERE reclamacao_id = ?
    ORDER BY data_upload DESC
    """, (reclamacao_id,))

    dados = cursor.fetchall()
    conn.close()

    return dados


def mostrar_evidencias(reclamacao_id):
    """
    Mostra fotos/documentos da reclamação na tela interna.
    """
    evidencias = listar_evidencias_reclamacao(reclamacao_id)

    if not evidencias:
        st.info("Nenhuma evidência enviada para esta reclamação.")
        return

    st.subheader("📷 Evidências enviadas")

    for evidencia in evidencias:
        _, nome_arquivo, caminho_arquivo, tipo_arquivo, data_upload = evidencia

        st.write(f"**Arquivo:** {nome_arquivo}")
        st.caption(f"Enviado em: {data_upload}")

        if os.path.exists(caminho_arquivo):
            if tipo_arquivo and tipo_arquivo.startswith("image"):
                st.image(caminho_arquivo, use_container_width=True)
            else:
                with open(caminho_arquivo, "rb") as f:
                    st.download_button(
                        label=f"Baixar {nome_arquivo}",
                        data=f,
                        file_name=nome_arquivo,
                        mime=tipo_arquivo or "application/octet-stream"
                    )
        else:
            st.warning("Arquivo não encontrado na pasta de uploads.")

        st.divider()


# =========================================================
# TELA DE LOGIN INTERNO
# =========================================================

def tela_login():
    st.title("🍑 SGR Frutas")
    st.subheader("Sistema interno de gestão de reclamações")

    st.info("Esta área é exclusiva para a empresa. O cliente deve acessar o portal público via QR Code.")

    with st.form("form_login"):
        email = st.text_input("E-mail")
        senha = st.text_input("Senha", type="password")
        entrar = st.form_submit_button("Entrar")

    if entrar:
        usuario = autenticar_usuario(email, senha)

        if usuario:
            st.session_state.usuario = usuario
            st.success("Login realizado com sucesso.")
            st.rerun()
        else:
            st.error("E-mail ou senha incorretos.")

    st.caption("Usuário inicial: admin@admin.com | Senha: admin123")


# =========================================================
# PORTAL PÚBLICO DO CLIENTE
# =========================================================

def portal_cliente():
    """
    Portal público acessado pelo cliente via QR Code.

    Link geral:
    http://localhost:8501/?portal=cliente

    Link com lote:
    http://localhost:8501/?portal=cliente&lote=LOTE2026-001
    """

    lote_url = obter_parametro_url("lote", "")

    st.markdown(
        """
        <style>
        .block-container {
            max-width: 850px;
            padding-top: 2rem;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    st.title("🍑 Portal de Reclamaciones")
    st.subheader("Registra una incidencia con tu producto")

    st.info(
        "Completa este formulario si has recibido fruta con problemas de calidad, "
        "retraso en la entrega, carga incompleta o cualquier otra incidencia."
    )

    produtos = [
        "Melocotón",
        "Nectarina",
        "Paraguayo",
        "Cereza",
        "Albaricoque",
        "Pera",
        "Manzana",
        "Higo",
        "Granada",
        "Uva",
        "Otro"
    ]

    tipos_reclamacao = [
        "Fruta podrida",
        "Fruta blanda",
        "Falta de color",
        "Calibre irregular",
        "Daño mecánico",
        "Retraso en entrega",
        "Carga incompleta",
        "Rotura cadena de frío",
        "Error de facturación",
        "Error de etiquetado",
        "Mal servicio",
        "Publicidad engañosa",
        "Otro"
    ]

    solucoes = [
        "Reposición",
        "Reembolso parcial",
        "Reembolso total",
        "Abono comercial",
        "Descuento próxima compra",
        "Corrección administrativa",
        "Contacto con atención al cliente"
    ]

    with st.form("form_portal_cliente", clear_on_submit=False):
        st.subheader("1. Datos del cliente")

        nome_cliente = st.text_input("Nombre de la empresa o cliente *")
        email_cliente = st.text_input("E-mail *")
        telefone_cliente = st.text_input("Teléfono")

        st.subheader("2. Datos del pedido")

        col1, col2 = st.columns(2)

        with col1:
            numero_pedido = st.text_input("Número de pedido")
            numero_albaran = st.text_input("Número de albarán")

        with col2:
            data_entrega = st.date_input("Fecha de entrega")
            quantidade_afetada = st.text_input("Cantidad afectada")

        st.subheader("3. Datos del producto")

        produto = st.selectbox("Producto *", produtos)
        variedade = st.text_input("Variedad")
        codigo_lote = st.text_input("Código de lote", value=lote_url)

        st.subheader("4. Incidencia")

        tipo_reclamacao = st.selectbox("Tipo de incidencia *", tipos_reclamacao)
        descricao = st.text_area("Describe el problema *")
        solucao_desejada = st.selectbox("Solución deseada", solucoes)

        st.subheader("5. Fotos o documentos")

        arquivos = st.file_uploader(
            "Sube fotos del producto, etiqueta, caja o albarán",
            type=["jpg", "jpeg", "png", "webp", "pdf"],
            accept_multiple_files=True
        )

        aceitar = st.checkbox(
            "Confirmo que los datos introducidos son correctos y autorizo el uso de esta información para gestionar la reclamación."
        )

        enviar = st.form_submit_button("Enviar reclamación")

    if enviar:
        if not nome_cliente:
            st.error("Introduce el nombre de la empresa o cliente.")
            return

        if not email_cliente:
            st.error("Introduce un e-mail de contacto.")
            return

        if not descricao:
            st.error("Describe el problema antes de enviar la reclamación.")
            return

        if not aceitar:
            st.error("Debes confirmar la autorización para enviar la reclamación.")
            return

        codigo = inserir_reclamacao(
            cliente_id=None,
            nome_cliente=nome_cliente,
            email_cliente=email_cliente,
            telefone_cliente=telefone_cliente,
            numero_pedido=numero_pedido,
            numero_albaran=numero_albaran,
            codigo_lote=codigo_lote,
            produto=produto,
            variedade=variedade,
            data_entrega=data_entrega,
            tipo_reclamacao=tipo_reclamacao,
            descricao=descricao,
            quantidade_afetada=quantidade_afetada,
            solucao_desejada=solucao_desejada
        )

        reclamacao_id = buscar_id_reclamacao_por_codigo(codigo)

        if reclamacao_id and arquivos:
            for arquivo in arquivos:
                salvar_evidencia(reclamacao_id, arquivo)

        st.success("Reclamación enviada correctamente.")
        st.markdown(f"### Número de seguimiento: `{codigo}`")
        st.info(
            "Guarda este número. La empresa lo utilizará para hacer seguimiento de tu incidencia."
        )

        if arquivos:
            st.success(f"Se han recibido {len(arquivos)} archivo(s) como evidencia.")

    st.divider()
    st.caption("Portal de reclamaciones para clientes del sector frutícola.")


# =========================================================
# MENU INTERNO DA EMPRESA
# =========================================================

def menu_lateral():
    usuario = st.session_state.usuario

    st.sidebar.title("🍑 SGR Frutas")
    st.sidebar.write(f"Usuário: **{usuario['nome']}**")
    st.sidebar.write(f"Perfil: **{usuario['perfil']}**")

    opcoes = [
        "Dashboard",
        "Nova Reclamação Interna",
        "Reclamações",
        "Clientes",
        "Lotes"
    ]

    pagina = st.sidebar.radio("Menu", opcoes)

    st.sidebar.divider()
    st.sidebar.caption("Portal cliente:")
    st.sidebar.code("?portal=cliente")

    if st.sidebar.button("Sair"):
        st.session_state.usuario = None
        st.rerun()

    return pagina


# =========================================================
# DASHBOARD
# =========================================================

def pagina_dashboard():
    st.title("📊 Dashboard")

    indicadores = obter_indicadores_dashboard()

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total de reclamações", indicadores["total"])
    col2.metric("Abertas", indicadores["abertas"])
    col3.metric("Resolvidas", indicadores["resolvidas"])
    col4.metric("Alta gravidade", indicadores["alta"])

    dados = listar_reclamacoes()

    if not dados:
        st.info("Ainda não há reclamações cadastradas.")
        return

    df = pd.DataFrame(dados, columns=[
        "ID",
        "Código",
        "Cliente",
        "Produto",
        "Variedade",
        "Tipo",
        "Categoria",
        "Gravidade",
        "Status",
        "Setor",
        "Data abertura",
        "Prazo resposta"
    ])

    st.divider()

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Reclamações por tipo")
        grafico_tipo = df["Tipo"].value_counts().reset_index()
        grafico_tipo.columns = ["Tipo", "Quantidade"]
        fig = px.bar(grafico_tipo, x="Tipo", y="Quantidade")
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.subheader("Reclamações por gravidade")
        grafico_gravidade = df["Gravidade"].value_counts().reset_index()
        grafico_gravidade.columns = ["Gravidade", "Quantidade"]
        fig = px.pie(grafico_gravidade, values="Quantidade", names="Gravidade")
        st.plotly_chart(fig, use_container_width=True)

    col_c, col_d = st.columns(2)

    with col_c:
        st.subheader("Reclamações por produto")
        grafico_produto = df["Produto"].value_counts().reset_index()
        grafico_produto.columns = ["Produto", "Quantidade"]
        fig = px.bar(grafico_produto, x="Produto", y="Quantidade")
        st.plotly_chart(fig, use_container_width=True)

    with col_d:
        st.subheader("Reclamações por setor")
        grafico_setor = df["Setor"].value_counts().reset_index()
        grafico_setor.columns = ["Setor", "Quantidade"]
        fig = px.bar(grafico_setor, x="Setor", y="Quantidade")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Últimas reclamações")
    st.dataframe(df.head(10), use_container_width=True)


# =========================================================
# NOVA RECLAMAÇÃO INTERNA
# =========================================================

def pagina_nova_reclamacao():
    st.title("📥 Nova Reclamação Interna")
    st.info("Use esta tela quando a reclamação for registrada pela própria empresa. O cliente deve usar o portal público via QR Code.")

    clientes = listar_clientes()
    lotes = listar_lotes()

    if not clientes:
        st.warning("Cadastre pelo menos um cliente antes de criar uma reclamação interna.")
        return

    clientes_dict = {
        f"{cliente[1]} - {cliente[3] or 'Sem contato'}": cliente
        for cliente in clientes
    }

    lotes_dict = {
        f"{lote[1]} - {lote[2]} - {lote[3] or ''}": lote
        for lote in lotes
    }

    produtos = [
        "Melocotón",
        "Nectarina",
        "Paraguayo",
        "Cereza",
        "Albaricoque",
        "Pera",
        "Manzana",
        "Higo",
        "Granada",
        "Uva",
        "Outro"
    ]

    tipos_reclamacao = [
        "Fruta podrida",
        "Fruta blanda",
        "Falta de color",
        "Calibre irregular",
        "Daño mecánico",
        "Retraso en entrega",
        "Carga incompleta",
        "Rotura cadena de frío",
        "Error de facturación",
        "Error de etiquetado",
        "Mal servicio",
        "Publicidad engañosa",
        "Outro"
    ]

    solucoes = [
        "Reposición",
        "Reembolso parcial",
        "Reembolso total",
        "Abono comercial",
        "Descuento próxima compra",
        "Corrección administrativa",
        "Disculpa formal",
        "Sin compensación"
    ]

    with st.form("form_nova_reclamacao"):
        st.subheader("Dados do cliente")

        cliente_selecionado = st.selectbox("Cliente", list(clientes_dict.keys()))
        cliente = clientes_dict[cliente_selecionado]

        cliente_id = cliente[0]
        nome_cliente = cliente[1]
        email_cliente = cliente[4]
        telefone_cliente = cliente[5]

        col1, col2 = st.columns(2)

        with col1:
            numero_pedido = st.text_input("Número do pedido")
            numero_albaran = st.text_input("Número do albarán")

        with col2:
            data_entrega = st.date_input("Data de entrega")
            quantidade_afetada = st.text_input("Quantidade afetada")

        st.subheader("Dados do produto")

        usar_lote = st.checkbox("Selecionar lote cadastrado")

        codigo_lote = ""
        variedade = ""

        if usar_lote and lotes:
            lote_selecionado = st.selectbox("Lote", list(lotes_dict.keys()))
            lote = lotes_dict[lote_selecionado]

            codigo_lote = lote[1]
            produto = lote[2]
            variedade = lote[3]

            st.info(f"Lote selecionado: {codigo_lote} | Produto: {produto} | Variedade: {variedade}")
        else:
            produto = st.selectbox("Produto", produtos)
            variedade = st.text_input("Variedade")
            codigo_lote = st.text_input("Código do lote")

        st.subheader("Dados da reclamação")

        tipo_reclamacao = st.selectbox("Tipo de reclamação", tipos_reclamacao)
        descricao = st.text_area("Descrição do problema")
        solucao_desejada = st.selectbox("Solução desejada", solucoes)

        arquivos = st.file_uploader(
            "Adicionar fotos/documentos",
            type=["jpg", "jpeg", "png", "webp", "pdf"],
            accept_multiple_files=True
        )

        enviar = st.form_submit_button("Registrar reclamação")

    if enviar:
        if not descricao:
            st.error("Descreva o problema antes de registrar a reclamação.")
            return

        codigo = inserir_reclamacao(
            cliente_id=cliente_id,
            nome_cliente=nome_cliente,
            email_cliente=email_cliente,
            telefone_cliente=telefone_cliente,
            numero_pedido=numero_pedido,
            numero_albaran=numero_albaran,
            codigo_lote=codigo_lote,
            produto=produto,
            variedade=variedade,
            data_entrega=data_entrega,
            tipo_reclamacao=tipo_reclamacao,
            descricao=descricao,
            quantidade_afetada=quantidade_afetada,
            solucao_desejada=solucao_desejada
        )

        reclamacao_id = buscar_id_reclamacao_por_codigo(codigo)

        if reclamacao_id and arquivos:
            for arquivo in arquivos:
                salvar_evidencia(reclamacao_id, arquivo)

        st.success(f"Reclamação registrada com sucesso! Código: {codigo}")

        if arquivos:
            st.success(f"{len(arquivos)} arquivo(s) salvo(s) como evidência.")


# =========================================================
# LISTA E DETALHE DE RECLAMAÇÕES
# =========================================================

def pagina_reclamacoes():
    st.title("📋 Reclamações")

    dados = listar_reclamacoes()

    if not dados:
        st.info("Nenhuma reclamação cadastrada.")
        return

    df = pd.DataFrame(dados, columns=[
        "ID",
        "Código",
        "Cliente",
        "Produto",
        "Variedade",
        "Tipo",
        "Categoria",
        "Gravidade",
        "Status",
        "Setor",
        "Data abertura",
        "Prazo resposta"
    ])

    col1, col2, col3 = st.columns(3)

    with col1:
        filtro_status = st.selectbox("Filtrar por status", ["Todos"] + sorted(df["Status"].dropna().unique().tolist()))

    with col2:
        filtro_gravidade = st.selectbox("Filtrar por gravidade", ["Todas"] + sorted(df["Gravidade"].dropna().unique().tolist()))

    with col3:
        filtro_setor = st.selectbox("Filtrar por setor", ["Todos"] + sorted(df["Setor"].dropna().unique().tolist()))

    df_filtrado = df.copy()

    if filtro_status != "Todos":
        df_filtrado = df_filtrado[df_filtrado["Status"] == filtro_status]

    if filtro_gravidade != "Todas":
        df_filtrado = df_filtrado[df_filtrado["Gravidade"] == filtro_gravidade]

    if filtro_setor != "Todos":
        df_filtrado = df_filtrado[df_filtrado["Setor"] == filtro_setor]

    st.dataframe(df_filtrado, use_container_width=True)

    st.divider()
    st.subheader("🔎 Detalhe e atualização da reclamação")

    ids = df_filtrado["ID"].tolist()

    if not ids:
        st.warning("Nenhuma reclamação encontrada com os filtros selecionados.")
        return

    reclamacao_id = st.selectbox("Selecione o ID da reclamação", ids)

    reclamacao = buscar_reclamacao_por_id(reclamacao_id)

    if reclamacao:
        col_a, col_b = st.columns([1.2, 1])

        with col_a:
            st.markdown(f"### {reclamacao[1]}")
            st.write(f"**Cliente:** {reclamacao[3]}")
            st.write(f"**E-mail:** {reclamacao[4]}")
            st.write(f"**Telefone:** {reclamacao[5]}")
            st.write(f"**Pedido:** {reclamacao[6]}")
            st.write(f"**Albarán:** {reclamacao[7]}")
            st.write(f"**Lote:** {reclamacao[8]}")
            st.write(f"**Produto:** {reclamacao[9]}")
            st.write(f"**Variedade:** {reclamacao[10]}")
            st.write(f"**Data de entrega:** {reclamacao[11]}")

        with col_b:
            st.write(f"**Tipo:** {reclamacao[12]}")
            st.write(f"**Categoria:** {reclamacao[13]}")
            st.write(f"**Gravidade:** {reclamacao[14]}")
            st.write(f"**Status atual:** {reclamacao[18]}")
            st.write(f"**Setor responsável:** {reclamacao[19]}")
            st.write(f"**Prazo de resposta:** {reclamacao[20]}")
            st.write(f"**Data abertura:** {reclamacao[21]}")

        st.subheader("Descrição do problema")
        st.write(reclamacao[15])

        st.subheader("Solução desejada")
        st.write(reclamacao[17])

        st.divider()

        mostrar_evidencias(reclamacao_id)

        st.divider()
        st.subheader("Atualizar status")

        status_opcoes = [
            "Nova",
            "Em triagem",
            "Em análise de qualidade",
            "Em análise logística",
            "Em análise administrativa",
            "Aguardando cliente",
            "Solução proposta",
            "Compensação aprovada",
            "Resolvida",
            "Fechada",
            "Cancelada",
            "Improcedente"
        ]

        novo_status = st.selectbox("Novo status", status_opcoes)
        comentario = st.text_area("Comentário da alteração")

        if st.button("Atualizar status"):
            usuario = st.session_state.usuario["nome"]

            sucesso = atualizar_status_reclamacao(
                reclamacao_id=reclamacao_id,
                novo_status=novo_status,
                comentario=comentario,
                usuario=usuario
            )

            if sucesso:
                st.success("Status atualizado com sucesso.")
                st.rerun()
            else:
                st.error("Erro ao atualizar status.")


# =========================================================
# CLIENTES
# =========================================================

def pagina_clientes():
    st.title("👥 Clientes")

    with st.expander("Cadastrar novo cliente", expanded=True):
        with st.form("form_cliente"):
            nome_empresa = st.text_input("Nome da empresa")
            cif_nif = st.text_input("CIF/NIF")
            nome_contato = st.text_input("Nome do contato")
            email = st.text_input("E-mail")
            telefone = st.text_input("Telefone")
            cidade = st.text_input("Cidade")
            pais = st.text_input("País", value="España")

            salvar = st.form_submit_button("Salvar cliente")

        if salvar:
            if not nome_empresa:
                st.error("Informe o nome da empresa.")
            else:
                inserir_cliente(
                    nome_empresa,
                    cif_nif,
                    nome_contato,
                    email,
                    telefone,
                    cidade,
                    pais
                )
                st.success("Cliente cadastrado com sucesso.")
                st.rerun()

    st.subheader("Clientes cadastrados")

    dados = listar_clientes()

    if dados:
        df = pd.DataFrame(dados, columns=[
            "ID",
            "Empresa",
            "CIF/NIF",
            "Contato",
            "E-mail",
            "Telefone",
            "Cidade",
            "País"
        ])

        st.dataframe(df, use_container_width=True)
    else:
        st.info("Nenhum cliente cadastrado.")



# =========================================================
# QR CODE
# =========================================================


def obter_url_base_padrao():
    """
    Define a URL base padrão para gerar QR Codes.

    Em produção, recomenda-se configurar no Streamlit Cloud:
    APP_BASE_URL = "https://seu-app.streamlit.app"

    Também aceita variável de ambiente APP_BASE_URL.
    """
    try:
        url_secrets = st.secrets.get("APP_BASE_URL", "")
        if url_secrets:
            return str(url_secrets).strip().rstrip("/")
    except Exception:
        pass

    url_env = os.getenv("APP_BASE_URL", "")
    if url_env:
        return url_env.strip().rstrip("/")

    return "http://localhost:8501"


def gerar_url_portal_cliente(base_url, codigo_lote):
    """
    Gera a URL que será gravada no QR Code.
    Exemplo:
    http://localhost:8501/?portal=cliente&lote=LOTE2026-001
    """
    base_url = (base_url or "").strip().rstrip("/")

    if not base_url:
        base_url = "http://localhost:8501"

    parametros = urlencode({
        "portal": "cliente",
        "lote": codigo_lote
    })

    return f"{base_url}/?{parametros}"


def gerar_qrcode_png_bytes(url):
    """
    Gera um QR Code em memória e devolve em bytes para download.
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4
    )

    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return buffer.getvalue()


def bloco_qrcode_lote(titulo, codigo_lote, key_prefix):
    """
    Bloco visual reutilizável para mostrar e baixar o QR Code de um lote.
    """
    st.subheader(titulo)

    base_url = st.text_input(
        "URL base do sistema",
        value=obter_url_base_padrao(),
        key=f"{key_prefix}_base_url",
        help="Em produção, troque pela URL real do Streamlit Cloud. Exemplo: https://seu-app.streamlit.app"
    )

    if "localhost" in base_url or "127.0.0.1" in base_url:
        st.warning(
            "Atenção: este QR Code está usando localhost. "
            "Se a aplicação já está publicada, troque pela URL real do Streamlit Cloud antes de baixar o QR."
        )

    url_qr = gerar_url_portal_cliente(base_url, codigo_lote)
    qr_bytes = gerar_qrcode_png_bytes(url_qr)

    col_qr, col_info = st.columns([1, 2])

    with col_qr:
        st.image(qr_bytes, caption=f"Lote: {codigo_lote}", width=220)

    with col_info:
        st.write("**Link gravado no QR Code:**")
        st.code(url_qr)
        st.download_button(
            label="⬇️ Baixar QR Code PNG",
            data=qr_bytes,
            file_name=f"qrcode_lote_{codigo_lote}.png",
            mime="image/png",
            key=f"{key_prefix}_download"
        )

# =========================================================
# LOTES
# =========================================================

def pagina_lotes():
    st.title("📦 Lotes")

    produtos = [
        "Melocotón",
        "Nectarina",
        "Paraguayo",
        "Cereza",
        "Albaricoque",
        "Pera",
        "Manzana",
        "Higo",
        "Granada",
        "Uva",
        "Outro"
    ]

    if "ultimo_lote_qr" not in st.session_state:
        st.session_state.ultimo_lote_qr = ""

    with st.expander("Cadastrar novo lote", expanded=True):
        with st.form("form_lote"):
            codigo_lote = st.text_input("Código do lote")
            produto = st.selectbox("Produto", produtos)
            variedade = st.text_input("Variedade")
            finca = st.text_input("Finca")
            data_colheita = st.date_input("Data de colheita")
            data_confeccao = st.date_input("Data de confección")
            camara_fria = st.text_input("Câmara fria")
            temperatura_saida = st.text_input("Temperatura de saída")
            observacoes = st.text_area("Observações")

            salvar = st.form_submit_button("Salvar lote e gerar QR Code")

        if salvar:
            if not codigo_lote:
                st.error("Informe o código do lote.")
            else:
                try:
                    inserir_lote(
                        codigo_lote,
                        produto,
                        variedade,
                        finca,
                        data_colheita,
                        data_confeccao,
                        camara_fria,
                        temperatura_saida,
                        observacoes
                    )

                    st.session_state.ultimo_lote_qr = codigo_lote
                    st.success("Lote cadastrado com sucesso. O QR Code já está disponível abaixo.")

                except Exception as e:
                    st.error(f"Erro ao cadastrar lote: {e}")

    if st.session_state.ultimo_lote_qr:
        st.divider()
        bloco_qrcode_lote(
            titulo="✅ QR Code do último lote cadastrado",
            codigo_lote=st.session_state.ultimo_lote_qr,
            key_prefix="ultimo_lote"
        )

    st.divider()
    st.subheader("Lotes cadastrados")

    dados = listar_lotes()

    if dados:
        df = pd.DataFrame(dados, columns=[
            "ID",
            "Código do lote",
            "Produto",
            "Variedade",
            "Finca",
            "Data colheita",
            "Data confección",
            "Câmara fria"
        ])

        st.dataframe(df, use_container_width=True)

        st.divider()
        st.subheader("🔳 Gerar QR Code de um lote já cadastrado")

        opcoes_lotes = {
            f"{linha[1]} - {linha[2]} - {linha[3] or ''}": linha[1]
            for linha in dados
        }

        lote_escolhido_label = st.selectbox(
            "Selecione um lote",
            list(opcoes_lotes.keys()),
            key="select_lote_qr"
        )

        codigo_lote_escolhido = opcoes_lotes[lote_escolhido_label]

        bloco_qrcode_lote(
            titulo="QR Code do lote selecionado",
            codigo_lote=codigo_lote_escolhido,
            key_prefix="lote_selecionado"
        )

    else:
        st.info("Nenhum lote cadastrado.")

# =========================================================
# MAIN
# =========================================================

def main():
    portal = obter_parametro_url("portal", "")

    # Portal público do cliente via QR Code
    if portal == "cliente":
        portal_cliente()
        return

    # Sistema interno da empresa
    if st.session_state.usuario is None:
        tela_login()
    else:
        pagina = menu_lateral()

        if pagina == "Dashboard":
            pagina_dashboard()
        elif pagina == "Nova Reclamação Interna":
            pagina_nova_reclamacao()
        elif pagina == "Reclamações":
            pagina_reclamacoes()
        elif pagina == "Clientes":
            pagina_clientes()
        elif pagina == "Lotes":
            pagina_lotes()


if __name__ == "__main__":
    main()

