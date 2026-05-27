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
        st.info("No se ha enviado ninguna evidencia para esta reclamación.")
        return

    st.subheader("📷 Evidencias enviadas")

    for evidencia in evidencias:
        _, nome_arquivo, caminho_arquivo, tipo_arquivo, data_upload = evidencia

        st.write(f"**Archivo:** {nome_arquivo}")
        st.caption(f"Enviado el: {data_upload}")

        if os.path.exists(caminho_arquivo):
            if tipo_arquivo and tipo_arquivo.startswith("image"):
                st.image(caminho_arquivo, use_container_width=True)
            else:
                with open(caminho_arquivo, "rb") as f:
                    st.download_button(
                        label=f"Descargar {nome_arquivo}",
                        data=f,
                        file_name=nome_arquivo,
                        mime=tipo_arquivo or "application/octet-stream"
                    )
        else:
            st.warning("Archivo no encontrado en la carpeta de uploads.")

        st.divider()


# =========================================================
# TELA DE LOGIN INTERNO
# =========================================================

def tela_login():
    st.title("🍑 SGR Frutas")
    st.subheader("Sistema interno de gestión de reclamaciones")

    st.info("Esta área es exclusiva para la empresa. El cliente debe acceder al portal público mediante QR Code.")

    with st.form("form_login"):
        email = st.text_input("E-mail")
        senha = st.text_input("Contraseña", type="password")
        entrar = st.form_submit_button("Entrar")

    if entrar:
        usuario = autenticar_usuario(email, senha)

        if usuario:
            st.session_state.usuario = usuario
            st.success("Inicio de sesión realizado correctamente.")
            st.rerun()
        else:
            st.error("E-mail o contraseña incorrectos.")

    st.caption("Usuario inicial: admin@admin.com | Contraseña: admin123")


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
    st.sidebar.write(f"Usuario: **{usuario['nome']}**")
    st.sidebar.write(f"Perfil: **{usuario['perfil']}**")

    opcoes = [
        "Panel de control",
        "Nueva reclamación interna",
        "Reclamaciones",
        "Clientes",
        "Lotes"
    ]

    pagina = st.sidebar.radio("Menu", opcoes)

    st.sidebar.divider()
    st.sidebar.caption("Portal del cliente:")
    st.sidebar.code("?portal=cliente")

    if st.sidebar.button("Salir"):
        st.session_state.usuario = None
        st.rerun()

    return pagina


# =========================================================
# DASHBOARD
# =========================================================

def pagina_dashboard():
    st.title("📊 Panel de control")

    indicadores = obter_indicadores_dashboard()

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total de reclamaciones", indicadores["total"])
    col2.metric("Abiertas", indicadores["abertas"])
    col3.metric("Resueltas", indicadores["resolvidas"])
    col4.metric("Alta gravedad", indicadores["alta"])

    dados = listar_reclamacoes()

    if not dados:
        st.info("Todavía no hay reclamaciones registradas.")
        return

    df = pd.DataFrame(dados, columns=[
        "ID",
        "Código",
        "Cliente",
        "Producto",
        "Variedad",
        "Tipo",
        "Categoría",
        "Gravedad",
        "Estado",
        "Departamento",
        "Fecha de apertura",
        "Plazo de respuesta"
    ])

    st.divider()

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Reclamaciones por tipo")
        grafico_tipo = df["Tipo"].value_counts().reset_index()
        grafico_tipo.columns = ["Tipo", "Cantidad"]
        fig = px.bar(grafico_tipo, x="Tipo", y="Cantidad")
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.subheader("Reclamaciones por gravedad")
        grafico_gravidade = df["Gravedad"].value_counts().reset_index()
        grafico_gravidade.columns = ["Gravedad", "Cantidad"]
        fig = px.pie(grafico_gravidade, values="Cantidad", names="Gravedad")
        st.plotly_chart(fig, use_container_width=True)

    col_c, col_d = st.columns(2)

    with col_c:
        st.subheader("Reclamaciones por producto")
        grafico_produto = df["Producto"].value_counts().reset_index()
        grafico_produto.columns = ["Producto", "Cantidad"]
        fig = px.bar(grafico_produto, x="Producto", y="Cantidad")
        st.plotly_chart(fig, use_container_width=True)

    with col_d:
        st.subheader("Reclamaciones por departamento")
        grafico_setor = df["Departamento"].value_counts().reset_index()
        grafico_setor.columns = ["Departamento", "Cantidad"]
        fig = px.bar(grafico_setor, x="Departamento", y="Cantidad")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Últimas reclamaciones")
    st.dataframe(df.head(10), use_container_width=True)


# =========================================================
# NOVA RECLAMAÇÃO INTERNA
# =========================================================

def pagina_nova_reclamacao():
    st.title("📥 Nueva reclamación interna")
    st.info("Utiliza esta pantalla cuando la reclamación sea registrada por la propia empresa. El cliente debe usar el portal público mediante QR Code.")

    clientes = listar_clientes()
    lotes = listar_lotes()

    if not clientes:
        st.warning("Registra al menos un cliente antes de crear una reclamación interna.")
        return

    clientes_dict = {
        f"{cliente[1]} - {cliente[3] or 'Sin contacto'}": cliente
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
        st.subheader("Datos del cliente")

        cliente_selecionado = st.selectbox("Cliente", list(clientes_dict.keys()))
        cliente = clientes_dict[cliente_selecionado]

        cliente_id = cliente[0]
        nome_cliente = cliente[1]
        email_cliente = cliente[4]
        telefone_cliente = cliente[5]

        col1, col2 = st.columns(2)

        with col1:
            numero_pedido = st.text_input("Número de pedido")
            numero_albaran = st.text_input("Número de albarán")

        with col2:
            data_entrega = st.date_input("Fecha de entrega")
            quantidade_afetada = st.text_input("Cantidad afectada")

        st.subheader("Datos del producto")

        usar_lote = st.checkbox("Seleccionar lote registrado")

        codigo_lote = ""
        variedade = ""

        if usar_lote and lotes:
            lote_selecionado = st.selectbox("Lote", list(lotes_dict.keys()))
            lote = lotes_dict[lote_selecionado]

            codigo_lote = lote[1]
            produto = lote[2]
            variedade = lote[3]

            st.info(f"Lote seleccionado: {codigo_lote} | Produto: {produto} | Variedade: {variedade}")
        else:
            produto = st.selectbox("Producto", produtos)
            variedade = st.text_input("Variedad")
            codigo_lote = st.text_input("Código del lote")

        st.subheader("Datos de la reclamación")

        tipo_reclamacao = st.selectbox("Tipo de reclamación", tipos_reclamacao)
        descricao = st.text_area("Descripción del problema")
        solucao_desejada = st.selectbox("Solución deseada", solucoes)

        arquivos = st.file_uploader(
            "Añadir fotos/documentos",
            type=["jpg", "jpeg", "png", "webp", "pdf"],
            accept_multiple_files=True
        )

        enviar = st.form_submit_button("Registrar reclamación")

    if enviar:
        if not descricao:
            st.error("Describe el problema antes de registrar la reclamación.")
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

        st.success(f"Reclamación registrada correctamente. Código: {codigo}")

        if arquivos:
            st.success(f"{len(arquivos)} archivo(s) guardado(s) como evidencia.")


# =========================================================
# LISTA E DETALHE DE RECLAMAÇÕES
# =========================================================

def pagina_reclamacoes():
    st.title("📋 Reclamaciones")

    dados = listar_reclamacoes()

    if not dados:
        st.info("Ninguna reclamación registrada.")
        return

    df = pd.DataFrame(dados, columns=[
        "ID",
        "Código",
        "Cliente",
        "Producto",
        "Variedad",
        "Tipo",
        "Categoría",
        "Gravedad",
        "Estado",
        "Departamento",
        "Fecha de apertura",
        "Plazo de respuesta"
    ])

    col1, col2, col3 = st.columns(3)

    with col1:
        filtro_status = st.selectbox("Filtrar por estado", ["Todos"] + sorted(df["Estado"].dropna().unique().tolist()))

    with col2:
        filtro_gravidade = st.selectbox("Filtrar por gravedad", ["Todas"] + sorted(df["Gravedad"].dropna().unique().tolist()))

    with col3:
        filtro_setor = st.selectbox("Filtrar por departamento", ["Todos"] + sorted(df["Departamento"].dropna().unique().tolist()))

    df_filtrado = df.copy()

    if filtro_status != "Todos":
        df_filtrado = df_filtrado[df_filtrado["Estado"] == filtro_status]

    if filtro_gravidade != "Todas":
        df_filtrado = df_filtrado[df_filtrado["Gravedad"] == filtro_gravidade]

    if filtro_setor != "Todos":
        df_filtrado = df_filtrado[df_filtrado["Departamento"] == filtro_setor]

    st.dataframe(df_filtrado, use_container_width=True)

    st.divider()
    st.subheader("🔎 Detalle y actualización de la reclamación")

    ids = df_filtrado["ID"].tolist()

    if not ids:
        st.warning("No se encontró ninguna reclamación con los filtros seleccionados.")
        return

    reclamacao_id = st.selectbox("Selecciona el ID de la reclamación", ids)

    reclamacao = buscar_reclamacao_por_id(reclamacao_id)

    if reclamacao:
        col_a, col_b = st.columns([1.2, 1])

        with col_a:
            st.markdown(f"### {reclamacao[1]}")
            st.write(f"**Cliente:** {reclamacao[3]}")
            st.write(f"**E-mail:** {reclamacao[4]}")
            st.write(f"**Teléfono:** {reclamacao[5]}")
            st.write(f"**Pedido:** {reclamacao[6]}")
            st.write(f"**Albarán:** {reclamacao[7]}")
            st.write(f"**Lote:** {reclamacao[8]}")
            st.write(f"**Produto:** {reclamacao[9]}")
            st.write(f"**Variedade:** {reclamacao[10]}")
            st.write(f"**Fecha de entrega:** {reclamacao[11]}")

        with col_b:
            st.write(f"**Tipo:** {reclamacao[12]}")
            st.write(f"**Categoría:** {reclamacao[13]}")
            st.write(f"**Gravedad:** {reclamacao[14]}")
            st.write(f"**Estado actual:** {reclamacao[18]}")
            st.write(f"**Departamento responsable:** {reclamacao[19]}")
            st.write(f"**Plazo de respuesta:** {reclamacao[20]}")
            st.write(f"**Fecha de apertura:** {reclamacao[21]}")

        st.subheader("Descripción del problema")
        st.write(reclamacao[15])

        st.subheader("Solución deseada")
        st.write(reclamacao[17])

        st.divider()

        mostrar_evidencias(reclamacao_id)

        st.divider()
        st.subheader("Actualizar estado")

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

        novo_status = st.selectbox("Nuevo estado", status_opcoes)
        comentario = st.text_area("Comentario de la modificación")

        if st.button("Actualizar estado"):
            usuario = st.session_state.usuario["nome"]

            sucesso = atualizar_status_reclamacao(
                reclamacao_id=reclamacao_id,
                novo_status=novo_status,
                comentario=comentario,
                usuario=usuario
            )

            if sucesso:
                st.success("Estado actualizado correctamente.")
                st.rerun()
            else:
                st.error("Error al actualizar el estado.")


# =========================================================
# CLIENTES
# =========================================================

def pagina_clientes():
    st.title("👥 Clientes")

    with st.expander("Registrar nuevo cliente", expanded=True):
        with st.form("form_cliente"):
            nome_empresa = st.text_input("Nombre de la empresa")
            cif_nif = st.text_input("CIF/NIF")
            nome_contato = st.text_input("Nombre de contacto")
            email = st.text_input("E-mail")
            telefone = st.text_input("Teléfono")
            cidade = st.text_input("Cidade")
            pais = st.text_input("País", value="España")

            salvar = st.form_submit_button("Guardar cliente")

        if salvar:
            if not nome_empresa:
                st.error("Introduce el nombre de la empresa.")
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
                st.success("Cliente registrado correctamente.")
                st.rerun()

    st.subheader("Clientes registrados")

    dados = listar_clientes()

    if dados:
        df = pd.DataFrame(dados, columns=[
            "ID",
            "Empresa",
            "CIF/NIF",
            "Contacto",
            "E-mail",
            "Teléfono",
            "Cidade",
            "País"
        ])

        st.dataframe(df, use_container_width=True)
    else:
        st.info("Ningún cliente registrado.")



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

    return "https://reclamacionesbajocinca.streamlit.app/"


def gerar_url_portal_cliente(base_url, codigo_lote):
    """
    Gera a URL que será gravada no QR Code.
    Exemplo:
    http://localhost:8501/?portal=cliente&lote=LOTE2026-001
    """
    base_url = (base_url or "").strip().rstrip("/")

    if not base_url:
        base_url = "https://reclamacionesbajocinca.streamlit.app/"

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
        "URL base del sistema",
        value=obter_url_base_padrao(),
        key=f"{key_prefix}_base_url",
        help="En producción, cambia esta URL por la URL real de Streamlit Cloud. Ejemplo: https://tu-app.streamlit.app"
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
        st.write("**Enlace guardado en el QR Code:**")
        st.code(url_qr)
        st.download_button(
            label="⬇️ Descargar QR Code PNG",
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

    with st.expander("Registrar nuevo lote", expanded=True):
        with st.form("form_lote"):
            codigo_lote = st.text_input("Código del lote")
            produto = st.selectbox("Producto", produtos)
            variedade = st.text_input("Variedad")
            finca = st.text_input("Finca")
            data_colheita = st.date_input("Fecha de cosecha")
            data_confeccao = st.date_input("Data de confección")
            camara_fria = st.text_input("Cámara frigorífica")
            temperatura_saida = st.text_input("Temperatura de salida")
            observacoes = st.text_area("Observaciones")

            salvar = st.form_submit_button("Guardar lote y generar QR Code")

        if salvar:
            if not codigo_lote:
                st.error("Introduce el código del lote.")
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
                    st.success("Lote registrado correctamente. El QR Code ya está disponible abajo.")

                except Exception as e:
                    st.error(f"Error al registrar el lote: {e}")

    if st.session_state.ultimo_lote_qr:
        st.divider()
        bloco_qrcode_lote(
            titulo="✅ QR Code del último lote registrado",
            codigo_lote=st.session_state.ultimo_lote_qr,
            key_prefix="ultimo_lote"
        )

    st.divider()
    st.subheader("Lotes registrados")

    dados = listar_lotes()

    if dados:
        df = pd.DataFrame(dados, columns=[
            "ID",
            "Código del lote",
            "Producto",
            "Variedad",
            "Finca",
            "Fecha de cosecha",
            "Data confección",
            "Cámara frigorífica"
        ])

        st.dataframe(df, use_container_width=True)

        st.divider()
        st.subheader("🔳 Generar QR Code de un lote ya registrado")

        opcoes_lotes = {
            f"{linha[1]} - {linha[2]} - {linha[3] or ''}": linha[1]
            for linha in dados
        }

        lote_escolhido_label = st.selectbox(
            "Selecciona un lote",
            list(opcoes_lotes.keys()),
            key="select_lote_qr"
        )

        codigo_lote_escolhido = opcoes_lotes[lote_escolhido_label]

        bloco_qrcode_lote(
            titulo="QR Code del lote seleccionado",
            codigo_lote=codigo_lote_escolhido,
            key_prefix="lote_selecionado"
        )

    else:
        st.info("Ningún lote registrado.")

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

        if pagina == "Panel de control":
            pagina_dashboard()
        elif pagina == "Nueva reclamación interna":
            pagina_nova_reclamacao()
        elif pagina == "Reclamaciones":
            pagina_reclamacoes()
        elif pagina == "Clientes":
            pagina_clientes()
        elif pagina == "Lotes":
            pagina_lotes()


if __name__ == "__main__":
    main()

