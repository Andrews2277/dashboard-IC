import io
import base64
import pandas as pd
import dash
from dash import dcc, html, Input, Output, State, dash_table
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import nltk
from nltk.corpus import stopwords
from wordcloud import WordCloud
from matplotlib.colors import LinearSegmentedColormap

nltk.download('stopwords', quiet=True)
_STOPWORDS_PT = set(stopwords.words('portuguese'))

pio.templates["plotly"].layout.update(hoverlabel=dict(namelength=-1))

# ── Carregamento e merge (uma vez na inicialização) ───────────────────────────

print("Carregando dados...")

fato = pd.read_csv("Fatos_Respostas.csv")
perguntas = pd.read_csv("Dimensao_Perguntas.csv")
respondentes = pd.read_excel("Dimensao_Respondentes.xlsx")
escolas = pd.read_csv("Dimensao_Escolas.csv")

_factor = pd.ExcelFile("DADOS_LIMPOS_FACTOR.xlsx")
_ef_prof = _factor.parse("DADOS_PROFISSIONAIS")[["ID_Respondente", "EFICACIA_PROFISSIONAIS"]]
_ef_aluno = _factor.parse("DADOS_ALUNO")[["ID_Respondente", "EFICACIA_ALUNO"]]
_ef_pais = _factor.parse("DADOS_PAIS")[["ID_Respondente", "EFICACIA_PAIS"]]

respondentes = (
    respondentes
    .merge(_ef_prof, on="ID_Respondente", how="left")
    .merge(_ef_aluno, on="ID_Respondente", how="left")
    .merge(_ef_pais, on="ID_Respondente", how="left")
)

fato["CO_ENTIDADE"] = pd.to_numeric(fato["CO_ENTIDADE"], errors="coerce").astype("Int64")
escolas["CO_ENTIDADE"] = pd.to_numeric(escolas["CO_ENTIDADE"], errors="coerce").astype("Int64")

df = (
    fato
    .merge(
        perguntas[["ID_Pergunta", "Categoria", "Perfil_Alvo", "Afirmativa_Unificada", "Métrica", "Pergunta_Padronizada"]],
        on="ID_Pergunta",
    )
    .merge(
        respondentes[["ID_Respondente", "Perfil", "CO_ENTIDADE", "Cidade da Escola", "Nome da Escola",
                       "Gênero", "Função na Escola", "Carga Horária Semanal", "Vínculo de Trabalho",
                       "Estudou na Escola", "Número de Escolas (Trabalho)",
                       "Modalidade de Ensino (Aluno)", "Familiar Estudou na Escola", "Idade",
                       "Auxilio Todo Jovem na Escola (Aluno)",
                       "Grau de Parentesco", "Responsável Estudou na Escola",
                       "EFICACIA_PROFISSIONAIS", "EFICACIA_ALUNO", "EFICACIA_PAIS"]],
        on="ID_Respondente",
        suffixes=("_fato", "_resp"),
    )
    .merge(
        escolas[["CO_ENTIDADE", "CO_ORGAO_REGIONAL", "as12"]],
        left_on="CO_ENTIDADE_resp",
        right_on="CO_ENTIDADE",
        how="left",
    )
    .drop(columns=["CO_ENTIDADE"])
)

print(f"DataFrame pronto: {len(df):,} linhas")

# Ordem fixa de categorias (pelo índice original)
ORDEM_CATEGORIAS = sorted(df["Categoria"].dropna().unique())

# Rótulos curtos para exibição no gráfico
LABEL_CATEGORIA = {c: (c[:40] + "…" if len(c) > 40 else c) for c in ORDEM_CATEGORIAS}

PERFIL_COLORS = {
    "Aluno":       "#009B4E",
    "Estudante":   "#009B4E",
    "Responsável": "#F5C518",
    "Profissional":"#D01020",
}

CRE_LABEL = {1.0: "1ª CRE – Porto Alegre", 3.0: "3ª CRE – Estrela", 28.0: "28ª CRE – Gravataí"}
df["CRE"] = df["CO_ORGAO_REGIONAL"].map(CRE_LABEL).fillna("Não informado")

municipios = sorted(df["Cidade da Escola"].dropna().unique())

# ── Pré-cômputo Equipe Diretiva ───────────────────────────────────────────────
FUNC_DIRETIVA = "Equipe Diretiva (Direção, Vice-Direção, Coordenação, Orientação e Supervisão)"

_resp_diretiva = (
    df[df["Função na Escola"] == FUNC_DIRETIVA]
    .drop_duplicates("ID_Respondente")
)
N_DIRETIVA = len(_resp_diretiva)
MEDIA_CH_DIRETIVA = _resp_diretiva["Carga Horária Semanal"].mean()
PCT_EFETIVO_DIRETIVA = (_resp_diretiva["Vínculo de Trabalho"] == "Efetivo").mean() * 100

_LIKERT_ORDEM = ["Discordo totalmente", "Discordo", "Concordo", "Concordo totalmente"]
_LIKERT_CORES = {
    "Discordo totalmente": "#D01020",
    "Discordo":            "#FF8C8C",
    "Concordo":            "#7BC67E",
    "Concordo totalmente": "#009B4E",
}


def _wrap_label(text, width=15):
    words = text.split()
    lines, line = [], ""
    for w in words:
        if len(line) + len(w) + 1 <= width:
            line = (line + " " + w).strip()
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return "<br>".join(lines)


def _build_likert_diretiva(dff=None):
    if dff is None:
        dff = df
    mask = (
        (dff["Categoria"] == "Escala Likert (direção)") &
        (dff["Métrica"] == "Opinião") &
        (dff["Função na Escola"] == FUNC_DIRETIVA) &
        (dff["Resposta_Texto"].isin(_LIKERT_ORDEM))
    )
    counts = (
        dff[mask]
        .groupby(["Pergunta_Padronizada", "Resposta_Texto"])
        .size()
        .reset_index(name="N")
    )
    _empty = go.Figure()
    _empty.update_layout(
        paper_bgcolor="white", plot_bgcolor="white",
        annotations=[dict(text="Sem dados para os filtros selecionados",
                          showarrow=False, font=dict(size=14),
                          xref="paper", yref="paper", x=0.5, y=0.5)],
        height=750,
    )
    if counts.empty:
        return _empty
    totais = counts.groupby("Pergunta_Padronizada")["N"].sum()
    counts["Pct"] = counts.apply(
        lambda r: r["N"] / totais[r["Pergunta_Padronizada"]] * 100, axis=1
    )
    counts["Pergunta_Curta"] = counts["Pergunta_Padronizada"].apply(_wrap_label)

    fig = px.bar(
        counts,
        x="Pergunta_Curta",
        y="Pct",
        color="Resposta_Texto",
        barmode="stack",
        color_discrete_map=_LIKERT_CORES,
        category_orders={"Resposta_Texto": _LIKERT_ORDEM},
        title="Escala Likert — Percepção da Equipe Diretiva",
        labels={"Pct": "%", "Pergunta_Curta": "", "Resposta_Texto": ""},
        text_auto=".0f",
        custom_data=["Pergunta_Padronizada"],
    )
    fig.update_traces(
        textposition="inside", textfont_size=13,
        hovertemplate="%{customdata[0]}<br>%{fullData.name}: %{y:.1f}%<extra></extra>",
    )
    fig.update_layout(
        paper_bgcolor="white",
        plot_bgcolor="white",
        yaxis=dict(range=[0, 100], title="%"),
        xaxis=dict(title="", tickangle=0, tickfont=dict(size=14), ticklen=0, automargin=True),
        bargap=0.6,
        font=dict(size=14),
        margin=dict(t=55, b=60, l=10, r=10),
        legend_title="",
    )
    return fig

# ── Pré-cômputo Equipe Docente ────────────────────────────────────────────────
FUNC_DOCENTE = "Professor(a)"
CAT_DOCENTE  = "Relação Ensino-aprendizagem, Currículo e Práticas Pedagógicas"


def _build_docente_selecoes(dff=None):
    if dff is None:
        dff = df
    mask = (
        (dff["Categoria"] == CAT_DOCENTE) &
        (dff["Métrica"] == "Concordância") &
        (dff["Perfil_Alvo"] == "Profissional") &
        (dff["Função na Escola"] == FUNC_DOCENTE) &
        (dff["Resposta_Numerica"] == 1)
    )
    counts = (
        dff[mask]
        .groupby("Pergunta_Padronizada")
        .size()
        .reset_index(name="Seleções")
        .sort_values("Seleções", ascending=False)
    )
    total_resp = dff[
        (dff["Categoria"] == CAT_DOCENTE) &
        (dff["Métrica"] == "Concordância") &
        (dff["Perfil_Alvo"] == "Profissional") &
        (dff["Função na Escola"] == FUNC_DOCENTE)
    ]["ID_Respondente"].nunique()
    counts["Label"] = counts["Seleções"].apply(
        lambda n: f"{n} ({n / total_resp * 100:.1f}%)" if total_resp else str(n)
    )
    counts["Pergunta_Curta"] = counts["Pergunta_Padronizada"].apply(_wrap_label)

    fig = px.bar(
        counts,
        x="Pergunta_Curta",
        y="Seleções",
        title="Número de Seleções por Afirmativa — Professores",
        labels={"Seleções": "Nº de seleções", "Pergunta_Curta": ""},
        color_discrete_sequence=["#D01020"],
        text="Label",
        custom_data=["Pergunta_Padronizada"],
    )
    fig.update_traces(
        textposition="outside", textfont_size=13,
        hovertemplate="%{customdata[0]}<br>Seleções: %{y}<extra></extra>",
    )
    fig.update_layout(
        paper_bgcolor="white",
        plot_bgcolor="white",
        xaxis=dict(title="", tickangle=0, tickfont=dict(size=14), ticklen=0, automargin=True),
        yaxis=dict(title="Nº de seleções"),
        bargap=0.6,
        font=dict(size=14),
        margin=dict(t=55, b=60, l=10, r=10),
    )
    return fig


def _build_docente_importancia(dff=None):
    if dff is None:
        dff = df
    mask = (
        (dff["Categoria"] == CAT_DOCENTE) &
        (dff["Métrica"] == "Importância") &
        (dff["Perfil_Alvo"] == "Profissional") &
        (dff["Função na Escola"] == FUNC_DOCENTE)
    )
    media = (
        dff[mask]
        .groupby("Pergunta_Padronizada")["Importancia_Normalizada"]
        .mean()
        .reset_index(name="Média")
        .sort_values("Média", ascending=True)
    )
    media["Pergunta_Curta"] = media["Pergunta_Padronizada"].apply(
        lambda x: x[:70] + "…" if len(x) > 70 else x
    )

    fig = px.bar(
        media,
        x="Média",
        y="Pergunta_Curta",
        orientation="h",
        title="Média de Importância por Afirmativa — Professores",
        labels={"Média": "Importância (%)", "Pergunta_Curta": ""},
        color_discrete_sequence=["#D01020"],
        text_auto=".1f",
        custom_data=["Pergunta_Padronizada"],
    )
    fig.update_traces(
        textposition="outside", textfont_size=13,
        hovertemplate="%{customdata[0]}<br>Importância: %{x:.1f}%<extra></extra>",
    )
    fig.update_layout(
        paper_bgcolor="white",
        plot_bgcolor="white",
        xaxis=dict(range=[0, 100], title="Importância (%)"),
        yaxis=dict(title=""),
        font=dict(size=14),
        margin=dict(t=55, b=10, l=380, r=80),
    )
    return fig


# ── App ───────────────────────────────────────────────────────────────────────

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
app.title = "Dashboard de Eficácia Escolar"
server = app.server


# ── Helpers ───────────────────────────────────────────────────────────────────

def filter_df(municipio, escola):
    mask = pd.Series(True, index=df.index)
    if municipio:
        mask &= df["Cidade da Escola"] == municipio
    if escola:
        mask &= df["Nome da Escola"] == escola
    return df[mask]


def filter_prof_df(cre, funcao, genero, as12_val, estudou, vinculo, nescolas):
    dff = df.copy()
    if cre:
        dff = dff[dff["CRE"].isin(cre)]
    if funcao:
        dff = dff[dff["Função na Escola"].isin(funcao)]
    if genero:
        dff = dff[dff["Gênero"].isin(genero)]
    if as12_val is not None:
        dff = dff[dff["as12"] == float(as12_val)]
    if estudou:
        dff = dff[dff["Estudou na Escola"].isin(estudou)]
    if vinculo:
        dff = dff[dff["Vínculo de Trabalho"].isin(vinculo)]
    if nescolas:
        dff = dff[dff["Número de Escolas (Trabalho)"].isin(nescolas)]
    return dff


# Faixa etária para Alunos
def _faixa_etaria(idade):
    if pd.isna(idade): return "Não informado"
    if idade <= 10:    return "Até 10 anos"
    if idade <= 14:    return "11-14 anos"
    if idade <= 17:    return "15-17 anos"
    if idade <= 24:    return "18-24 anos"
    return "25 anos ou mais"

df["Faixa Etária"] = df["Idade"].apply(_faixa_etaria)

# Opções pré-computadas para os filtros de Profissionais
_prof = df[df["Perfil"] == "Profissional"].drop_duplicates("ID_Respondente")
_PROF_CRE_OPTS      = [{"label": v, "value": v} for v in CRE_LABEL.values()]
_PROF_FUNCAO_OPTS   = sorted(_prof["Função na Escola"].dropna().unique())
_PROF_GENERO_OPTS   = sorted(_prof["Gênero"].dropna().unique())
_PROF_VINCULO_OPTS  = sorted(_prof["Vínculo de Trabalho"].dropna().unique())
_PROF_NESCOLAS_OPTS = sorted(_prof["Número de Escolas (Trabalho)"].dropna().unique())
_PROF_ESTUDOU_OPTS  = sorted(_prof["Estudou na Escola"].dropna().unique())

# Opções pré-computadas para Alunos
_aluno = df[df["Perfil"] == "Aluno"].drop_duplicates("ID_Respondente")
_ALUNO_CRE_OPTS        = [{"label": v, "value": v} for v in CRE_LABEL.values()]
_ALUNO_GENERO_OPTS     = sorted(_aluno["Gênero"].dropna().unique())
_ALUNO_MODAL_OPTS      = sorted(_aluno["Modalidade de Ensino (Aluno)"].dropna().unique())
_ALUNO_FAMILIAR_OPTS   = sorted(_aluno["Familiar Estudou na Escola"].dropna().unique())
_ALUNO_FAIXA_OPTS      = ["Até 10 anos", "11-14 anos", "15-17 anos", "18-24 anos", "25 anos ou mais"]
_ALUNO_JOVEM_OPTS      = sorted(_aluno["Auxilio Todo Jovem na Escola (Aluno)"].dropna().unique())

# Opções pré-computadas para Responsáveis
_resp_r = df[df["Perfil"] == "Responsável"].drop_duplicates("ID_Respondente")
_RESP_CRE_OPTS         = [{"label": v, "value": v} for v in CRE_LABEL.values()]
_RESP_GENERO_OPTS      = sorted(_resp_r["Gênero"].dropna().unique())
_RESP_PARENTESCO_OPTS  = sorted(_resp_r["Grau de Parentesco"].dropna().unique())
_RESP_ESTUDOU_OPTS     = sorted(_resp_r["Responsável Estudou na Escola"].dropna().unique())
_RESP_JOVEM_OPTS       = sorted(_resp_r["Auxilio Todo Jovem na Escola (Aluno)"].dropna().unique())


def filter_alunos_df(cre, genero, modalidade, as12_val, familiar, faixa, jovem):
    dff = df.copy()
    if cre:
        dff = dff[dff["CRE"].isin(cre)]
    if genero:
        dff = dff[dff["Gênero"].isin(genero)]
    if modalidade:
        dff = dff[dff["Modalidade de Ensino (Aluno)"].isin(modalidade)]
    if as12_val is not None:
        dff = dff[dff["as12"] == float(as12_val)]
    if familiar:
        dff = dff[dff["Familiar Estudou na Escola"].isin(familiar)]
    if faixa:
        dff = dff[dff["Faixa Etária"].isin(faixa)]
    if jovem:
        dff = dff[dff["Auxilio Todo Jovem na Escola (Aluno)"].isin(jovem)]
    return dff


def filter_resp_df(cre, genero, parentesco, as12_val, estudou, jovem):
    dff = df.copy()
    if cre:
        dff = dff[dff["CRE"].isin(cre)]
    if genero:
        dff = dff[dff["Gênero"].isin(genero)]
    if parentesco:
        dff = dff[dff["Grau de Parentesco"].isin(parentesco)]
    if as12_val is not None:
        dff = dff[dff["as12"] == float(as12_val)]
    if estudou:
        dff = dff[dff["Responsável Estudou na Escola"].isin(estudou)]
    if jovem:
        dff = dff[dff["Auxilio Todo Jovem na Escola (Aluno)"].isin(jovem)]
    return dff


def stat_card(title, value_id, subtitle_id=None):
    body = [html.P(title, className="text-uppercase text-muted small mb-1 fw-bold")]
    body.append(html.H3(id=value_id, className="mb-0"))
    if subtitle_id:
        body.append(html.P(id=subtitle_id, className="text-muted small mt-1 mb-0"))
    return dbc.Card(dbc.CardBody(body), className="shadow-sm h-100 border-0")


# ── Layout ────────────────────────────────────────────────────────────────────

navbar = dbc.NavbarSimple(
    brand="Dashboard de Eficácia Escolar — Rio Grande do Sul",
    color="#808080",
    dark=True,
    fluid=True,
)

filtros = dbc.Row(
    [
        dbc.Col(
            [
                html.Label("Município", className="fw-semibold small"),
                dcc.Dropdown(
                    id="municipio-filter",
                    options=[{"label": m, "value": m} for m in municipios],
                    placeholder="Todos os municípios",
                    clearable=True,
                ),
            ],
            md=4,
        ),
        dbc.Col(
            [
                html.Label("Escola", className="fw-semibold small"),
                dcc.Dropdown(
                    id="escola-filter",
                    placeholder="Todas as escolas",
                    clearable=True,
                ),
            ],
            md=4,
        ),
    ],
    className="mb-4 align-items-end",
)

cards = dbc.Row(
    [
        dbc.Col(stat_card("Respondentes", "card-respondentes", "card-perfis"), md=4),
        dbc.Col(stat_card("Escolas participantes", "card-escolas"), md=4),
        dbc.Col(stat_card("Municípios", "card-municipios"), md=4),
    ],
    className="mb-4",
)

pizzas = dbc.Row(
    [
        dbc.Col(
            dcc.Graph(id="pizza-perfil", config={"displayModeBar": False}),
            md=6,
        ),
        dbc.Col(
            dcc.Graph(id="pizza-genero", config={"displayModeBar": False}),
            md=6,
        ),
    ],
    className="mb-4",
)

grafico_cre = dbc.Row(
    dbc.Col(
        dcc.Graph(id="barras-cre", config={"displayModeBar": False}),
        md=12,
    ),
    className="mb-4",
)

grafico_categoria = dbc.Row(
    dbc.Col(
        dcc.Graph(id="barras-categoria", config={"displayModeBar": False}),
        md=12,
    ),
    className="mb-4",
)

filtros_alunos = dbc.Card(
    dbc.CardBody([
        html.H6("Filtros — Estudantes", className="fw-bold text-muted mb-3"),
        dbc.Row([
            dbc.Col([
                html.Label("Coordenadoria de Educação", className="fw-semibold small"),
                dcc.Dropdown(id="aluno-cre-filter", options=_ALUNO_CRE_OPTS,
                             placeholder="Todas", multi=True, clearable=True),
            ], md=3),
            dbc.Col([
                html.Label("Gênero", className="fw-semibold small"),
                dcc.Dropdown(id="aluno-genero-filter",
                             options=[{"label": v, "value": v} for v in _ALUNO_GENERO_OPTS],
                             placeholder="Todos", multi=True, clearable=True),
            ], md=3),
            dbc.Col([
                html.Label("Modalidade de Ensino", className="fw-semibold small"),
                dcc.Dropdown(id="aluno-modal-filter",
                             options=[{"label": v, "value": v} for v in _ALUNO_MODAL_OPTS],
                             placeholder="Todas", multi=True, clearable=True),
            ], md=3),
            dbc.Col([
                html.Label("Escola — Estudo Qualitativo", className="fw-semibold small"),
                dcc.Dropdown(id="aluno-as12-filter",
                             options=[{"label": "Sim", "value": "1"},
                                      {"label": "Não", "value": "0"}],
                             placeholder="Todas", clearable=True),
            ], md=3),
        ], className="mb-3"),
        dbc.Row([
            dbc.Col([
                html.Label("Familiar Estudou na Escola", className="fw-semibold small"),
                dcc.Dropdown(id="aluno-familiar-filter",
                             options=[{"label": v, "value": v} for v in _ALUNO_FAMILIAR_OPTS],
                             placeholder="Todos", multi=True, clearable=True),
            ], md=3),
            dbc.Col([
                html.Label("Faixa Etária", className="fw-semibold small"),
                dcc.Dropdown(id="aluno-faixa-filter",
                             options=[{"label": v, "value": v} for v in _ALUNO_FAIXA_OPTS],
                             placeholder="Todas", multi=True, clearable=True),
            ], md=3),
            dbc.Col([
                html.Label("Auxílio Todo Jovem na Escola", className="fw-semibold small"),
                dcc.Dropdown(id="aluno-jovem-filter",
                             options=[{"label": v, "value": v} for v in _ALUNO_JOVEM_OPTS],
                             placeholder="Todos", multi=True, clearable=True),
            ], md=3),
        ]),
    ]),
    className="mb-4 shadow-sm border-0",
    style={"backgroundColor": "#f8f9fa"},
)

filtros_resp = dbc.Card(
    dbc.CardBody([
        html.H6("Filtros — Responsáveis", className="fw-bold text-muted mb-3"),
        dbc.Row([
            dbc.Col([
                html.Label("Coordenadoria de Educação", className="fw-semibold small"),
                dcc.Dropdown(id="resp-cre-filter", options=_RESP_CRE_OPTS,
                             placeholder="Todas", multi=True, clearable=True),
            ], md=3),
            dbc.Col([
                html.Label("Gênero", className="fw-semibold small"),
                dcc.Dropdown(id="resp-genero-filter",
                             options=[{"label": v, "value": v} for v in _RESP_GENERO_OPTS],
                             placeholder="Todos", multi=True, clearable=True),
            ], md=3),
            dbc.Col([
                html.Label("Grau de Parentesco", className="fw-semibold small"),
                dcc.Dropdown(id="resp-parentesco-filter",
                             options=[{"label": v, "value": v} for v in _RESP_PARENTESCO_OPTS],
                             placeholder="Todos", multi=True, clearable=True),
            ], md=3),
            dbc.Col([
                html.Label("Escola — Estudo Qualitativo", className="fw-semibold small"),
                dcc.Dropdown(id="resp-as12-filter",
                             options=[{"label": "Sim", "value": "1"},
                                      {"label": "Não", "value": "0"}],
                             placeholder="Todas", clearable=True),
            ], md=3),
        ], className="mb-3"),
        dbc.Row([
            dbc.Col([
                html.Label("Estudou na Escola", className="fw-semibold small"),
                dcc.Dropdown(id="resp-estudou-filter",
                             options=[{"label": v, "value": v} for v in _RESP_ESTUDOU_OPTS],
                             placeholder="Todos", multi=True, clearable=True),
            ], md=3),
            dbc.Col([
                html.Label("Todo Jovem na Escola", className="fw-semibold small"),
                dcc.Dropdown(id="resp-jovem-filter",
                             options=[{"label": v, "value": v} for v in _RESP_JOVEM_OPTS],
                             placeholder="Todos", multi=True, clearable=True),
            ], md=3),
        ]),
    ]),
    className="mb-4 shadow-sm border-0",
    style={"backgroundColor": "#f8f9fa"},
)

filtros_prof = dbc.Card(
    dbc.CardBody([
        html.H6("Filtros — Profissionais", className="fw-bold text-muted mb-3"),
        dbc.Row([
            dbc.Col([
                html.Label("Coordenadoria de Educação", className="fw-semibold small"),
                dcc.Dropdown(id="prof-cre-filter", options=_PROF_CRE_OPTS,
                             placeholder="Todas", multi=True, clearable=True),
            ], md=3),
            dbc.Col([
                html.Label("Função na Escola", className="fw-semibold small"),
                dcc.Dropdown(id="prof-funcao-filter",
                             options=[{"label": v, "value": v} for v in _PROF_FUNCAO_OPTS],
                             placeholder="Todas", multi=True, clearable=True),
            ], md=3),
            dbc.Col([
                html.Label("Gênero", className="fw-semibold small"),
                dcc.Dropdown(id="prof-genero-filter",
                             options=[{"label": v, "value": v} for v in _PROF_GENERO_OPTS],
                             placeholder="Todos", multi=True, clearable=True),
            ], md=3),
            dbc.Col([
                html.Label("Vínculo de Trabalho", className="fw-semibold small"),
                dcc.Dropdown(id="prof-vinculo-filter",
                             options=[{"label": v, "value": v} for v in _PROF_VINCULO_OPTS],
                             placeholder="Todos", multi=True, clearable=True),
            ], md=3),
        ], className="mb-3"),
        dbc.Row([
            dbc.Col([
                html.Label("Escola — Estudo Qualitativo", className="fw-semibold small"),
                dcc.Dropdown(id="prof-as12-filter",
                             options=[{"label": "Sim", "value": "1"},
                                      {"label": "Não", "value": "0"}],
                             placeholder="Todas", clearable=True),
            ], md=3),
            dbc.Col([
                html.Label("Estudou na Escola", className="fw-semibold small"),
                dcc.Dropdown(id="prof-estudou-filter",
                             options=[{"label": v, "value": v} for v in _PROF_ESTUDOU_OPTS],
                             placeholder="Todos", multi=True, clearable=True),
            ], md=3),
            dbc.Col([
                html.Label("Nº de Escolas que Trabalha", className="fw-semibold small"),
                dcc.Dropdown(id="prof-nescolas-filter",
                             options=[{"label": v, "value": v} for v in _PROF_NESCOLAS_OPTS],
                             placeholder="Todos", multi=True, clearable=True),
            ], md=3),
        ]),
    ]),
    className="mb-4 shadow-sm border-0",
    style={"backgroundColor": "#f8f9fa"},
)

cards_diretiva = dbc.Row(
    [
        dbc.Col(stat_card("Equipe Diretiva", "card-diretiva-n"), md=4),
        dbc.Col(stat_card("Carga Horária Média Semanal", "card-diretiva-ch"), md=4),
        dbc.Col(stat_card("Vínculo Efetivo", "card-diretiva-efetivo"), md=4),
    ],
    className="mb-4",
)

conteudo_diretiva = html.Div(
    [
        cards_diretiva,
        dbc.Row(
            dbc.Col(
                dcc.Graph(id="likert-diretiva", style={"height": "750px"}, config={"displayModeBar": False}),
                md=12,
            ),
            className="mb-4",
        ),
    ],
    className="pt-4",
)

# ── Pré-cômputo aba Geral ─────────────────────────────────────────────────────
def _cats_para(perfil):
    _p = perguntas[perguntas["Perfil_Alvo"] == perfil]
    return sorted(
        set(_p[_p["Métrica"] == "Concordância"]["Categoria"].unique()) &
        set(_p[_p["Métrica"] == "Importância"]["Categoria"].unique())
    )

CATS_GERAL     = _cats_para("Profissional")
CATS_ALUNOS    = _cats_para("Aluno")
CATS_RESP      = _cats_para("Responsável")


conteudo_docente = html.Div(
    [
        dbc.Row(
            dbc.Col(
                dcc.Graph(id="docente-selecoes", style={"height": "650px"}, config={"displayModeBar": False}),
                md=12,
            ),
            className="mb-4",
        ),
        dbc.Row(
            dbc.Col(
                dcc.Graph(id="docente-importancia", style={"height": "520px"}, config={"displayModeBar": False}),
                md=12,
            ),
            className="mb-4",
        ),
    ],
    className="pt-4",
)

_PERFIL_ALVO_CORES = {"Aluno": "#009B4E", "Responsável": "#F5C518", "Profissional": "#D01020"}


def _figs_selecoes_importancia(categoria, perfil_alvo, dff=None):
    if dff is None:
        dff = df
    empty = go.Figure().update_layout(paper_bgcolor="white", plot_bgcolor="white")
    if not categoria:
        return empty, empty

    cor = _PERFIL_ALVO_CORES.get(perfil_alvo, "#555555")

    mask_conc = (
        (dff["Categoria"] == categoria) &
        (dff["Métrica"] == "Concordância") &
        (dff["Perfil_Alvo"] == perfil_alvo) &
        (dff["Resposta_Numerica"] == 1)
    )
    counts = (
        dff[mask_conc]
        .groupby("Pergunta_Padronizada").size()
        .reset_index(name="Seleções")
        .sort_values("Seleções", ascending=False)
    )
    total_resp = dff[
        (dff["Categoria"] == categoria) &
        (dff["Métrica"] == "Concordância") &
        (dff["Perfil_Alvo"] == perfil_alvo)
    ]["ID_Respondente"].nunique()
    counts["Label"] = counts["Seleções"].apply(
        lambda n: f"{n} ({n / total_resp * 100:.1f}%)" if total_resp else str(n)
    )
    counts["Pergunta_Curta"] = counts["Pergunta_Padronizada"].apply(_wrap_label)

    fig1 = px.bar(
        counts, x="Pergunta_Curta", y="Seleções",
        title=f"Número de Seleções — {categoria}",
        labels={"Seleções": "Nº de seleções", "Pergunta_Curta": ""},
        color_discrete_sequence=[cor], text="Label",
        custom_data=["Pergunta_Padronizada"],
    )
    fig1.update_traces(
        textposition="outside", textfont_size=13,
        hovertemplate="%{customdata[0]}<br>Seleções: %{y}<extra></extra>",
    )
    fig1.update_layout(
        paper_bgcolor="white", plot_bgcolor="white",
        xaxis=dict(title="", tickangle=0, tickfont=dict(size=14), ticklen=0, automargin=True),
        yaxis=dict(title="Nº de seleções"),
        bargap=0.6, font=dict(size=14),
        margin=dict(t=55, b=60, l=10, r=10),
    )

    mask_imp = (
        (dff["Categoria"] == categoria) &
        (dff["Métrica"] == "Importância") &
        (dff["Perfil_Alvo"] == perfil_alvo)
    )
    media = (
        dff[mask_imp]
        .groupby("Pergunta_Padronizada")["Importancia_Normalizada"].mean()
        .reset_index(name="Média")
        .sort_values("Média", ascending=True)
    )
    media["Pergunta_Curta"] = media["Pergunta_Padronizada"].apply(
        lambda x: x[:70] + "…" if len(x) > 70 else x
    )

    fig2 = px.bar(
        media, x="Média", y="Pergunta_Curta", orientation="h",
        title=f"Média de Importância — {categoria}",
        labels={"Média": "Importância (%)", "Pergunta_Curta": ""},
        color_discrete_sequence=[cor], text_auto=".1f",
        custom_data=["Pergunta_Padronizada"],
    )
    fig2.update_traces(
        textposition="outside", textfont_size=13,
        hovertemplate="%{customdata[0]}<br>Importância: %{x:.1f}%<extra></extra>",
    )
    fig2.update_layout(
        paper_bgcolor="white", plot_bgcolor="white",
        xaxis=dict(range=[0, 100], title="Importância (%)"),
        yaxis=dict(title=""),
        font=dict(size=14),
        margin=dict(t=55, b=10, l=380, r=80),
    )
    return fig1, fig2


def _build_wordcloud_figure(categoria, perfil_alvo, dff=None):
    if dff is None:
        dff = df
    mask = (
        (dff["Categoria"] == categoria) &
        (dff["Perfil_Alvo"] == perfil_alvo) &
        dff["Resposta_Texto"].notna() &
        (dff["Resposta_Texto"].str.strip() != "")
    )
    textos = dff[mask]["Resposta_Texto"].str.strip()

    fig = go.Figure()
    fig.update_layout(
        paper_bgcolor="white", plot_bgcolor="white",
        xaxis=dict(visible=False, range=[0, 1]),
        yaxis=dict(visible=False, range=[0, 1]),
        margin=dict(l=0, r=0, t=40, b=0),
        title="Nuvem de Palavras — Respostas Textuais",
    )

    if textos.empty:
        fig.add_annotation(
            text="Sem respostas textuais<br>para esta categoria",
            showarrow=False, font=dict(size=14),
            xref="paper", yref="paper", x=0.5, y=0.5,
        )
        return fig

    texto_completo = " ".join(textos.tolist()).lower()
    cor = _PERFIL_ALVO_CORES.get(perfil_alvo, "#555555")
    cmap = LinearSegmentedColormap.from_list("perfil", ["#e0e0e0", cor])

    wc = WordCloud(
        width=500, height=760,
        background_color="white",
        colormap=cmap,
        max_words=120,
        collocations=True,
        stopwords=_STOPWORDS_PT,
    ).generate(texto_completo)

    buf = io.BytesIO()
    wc.to_image().save(buf, format="PNG")
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode("utf-8")

    fig.add_layout_image(
        dict(
            source=f"data:image/png;base64,{img_b64}",
            x=0, y=1,
            xref="paper", yref="paper",
            sizex=1, sizey=1,
            xanchor="left", yanchor="top",
            layer="below",
        )
    )
    return fig



conteudo_geral = html.Div(
    [
        dbc.Row(
            dbc.Col(
                [
                    html.Label("Categoria", className="fw-semibold small"),
                    dcc.Dropdown(
                        id="geral-cat-filter",
                        options=[{"label": c, "value": c} for c in CATS_GERAL],
                        value=CATS_GERAL[0],
                        clearable=False,
                    ),
                ],
                md=8,
            ),
            className="mb-4",
        ),
        dbc.Row(
            [
                dbc.Col(
                    dcc.Graph(id="geral-selecoes", style={"height": "800px"}, config={"displayModeBar": False}),
                    md=9,
                ),
                dbc.Col(
                    dcc.Graph(id="geral-wordcloud", style={"height": "800px"}, config={"displayModeBar": False}),
                    md=3,
                ),
            ],
            className="mb-4",
        ),
        dbc.Row(
            dbc.Col(dcc.Graph(id="geral-importancia", style={"height": "520px"}, config={"displayModeBar": False}), md=12),
            className="mb-4",
        ),
    ],
    className="pt-4",
)
conteudo_alunos = html.Div(
    [
        dbc.Row(
            dbc.Col(
                [
                    html.Label("Categoria", className="fw-semibold small"),
                    dcc.Dropdown(
                        id="alunos-cat-filter",
                        options=[{"label": c, "value": c} for c in CATS_ALUNOS],
                        value=CATS_ALUNOS[0],
                        clearable=False,
                    ),
                ],
                md=8,
            ),
            className="mb-4",
        ),
        dbc.Row(
            [
                dbc.Col(
                    dcc.Graph(id="alunos-selecoes", style={"height": "800px"}, config={"displayModeBar": False}),
                    md=9,
                ),
                dbc.Col(
                    dcc.Graph(id="alunos-wordcloud", style={"height": "800px"}, config={"displayModeBar": False}),
                    md=3,
                ),
            ],
            className="mb-4",
        ),
        dbc.Row(
            dbc.Col(dcc.Graph(id="alunos-importancia", style={"height": "520px"}, config={"displayModeBar": False}), md=12),
            className="mb-4",
        ),
    ],
    className="pt-4",
)

conteudo_resp = html.Div(
    [
        dbc.Row(
            dbc.Col(
                [
                    html.Label("Categoria", className="fw-semibold small"),
                    dcc.Dropdown(
                        id="resp-cat-filter",
                        options=[{"label": c, "value": c} for c in CATS_RESP],
                        value=CATS_RESP[0],
                        clearable=False,
                    ),
                ],
                md=8,
            ),
            className="mb-4",
        ),
        dbc.Row(
            [
                dbc.Col(
                    dcc.Graph(id="resp-selecoes", style={"height": "800px"}, config={"displayModeBar": False}),
                    md=9,
                ),
                dbc.Col(
                    dcc.Graph(id="resp-wordcloud", style={"height": "800px"}, config={"displayModeBar": False}),
                    md=3,
                ),
            ],
            className="mb-4",
        ),
        dbc.Row(
            dbc.Col(dcc.Graph(id="resp-importancia", style={"height": "520px"}, config={"displayModeBar": False}), md=12),
            className="mb-4",
        ),
    ],
    className="pt-4",
)


# ── Análise de Prioridades ────────────────────────────────────────────────────

_COR_QUAD = {
    "Alta Prioridade":  "#D01020",
    "Ponto Forte":      "#009B4E",
    "Baixa Prioridade": "#AAAAAA",
}

_PERFIL_PLURAL = {
    "Aluno": "Estudantes",
    "Responsável": "Responsáveis",
    "Profissional": "Profissionais",
}


def _build_prioridades(perfil_alvo, dff=None):
    if dff is None:
        dff = df
    _conc = (
        dff[(dff["Métrica"] == "Concordância") & (dff["Perfil_Alvo"] == perfil_alvo)]
        .groupby("Afirmativa_Unificada")["Resposta_Numerica"]
        .mean()
        .rename("Concordância (%)")
        * 100
    )
    _imp = (
        dff[(dff["Métrica"] == "Importância") & (dff["Perfil_Alvo"] == perfil_alvo)]
        .groupby("Afirmativa_Unificada")["Importancia_Normalizada"]
        .mean()
        .rename("Importância (norm.)")
    )
    df_p = (
        _conc.reset_index()
        .merge(_imp.reset_index(), on="Afirmativa_Unificada")
        .dropna()
        .sort_values("Importância (norm.)", ascending=False)
        .reset_index(drop=True)
    )

    def _quad(row):
        if row["Importância (norm.)"] > 50 and row["Concordância (%)"] < 50:
            return "Alta Prioridade"
        if row["Importância (norm.)"] > 50 and row["Concordância (%)"] >= 50:
            return "Ponto Forte"
        return "Baixa Prioridade"

    df_p["Quadrante"] = df_p.apply(_quad, axis=1)

    plural = _PERFIL_PLURAL.get(perfil_alvo, perfil_alvo)
    fig = px.scatter(
        df_p,
        x="Importância (norm.)",
        y="Concordância (%)",
        color="Quadrante",
        color_discrete_map=_COR_QUAD,
        hover_name="Afirmativa_Unificada",
        title=f"Matriz de Prioridades — Importância × Concordância ({plural})",
        labels={
            "Importância (norm.)": "Importância (0–100)",
            "Concordância (%)":    "Concordância (0–100)",
        },
    )
    fig.add_hline(y=50, line_dash="dash", line_color="gray", line_width=1)
    fig.add_vline(x=50, line_dash="dash", line_color="gray", line_width=1)
    fig.update_traces(marker=dict(size=10, opacity=0.8))
    fig.update_layout(
        paper_bgcolor="white",
        plot_bgcolor="white",
        xaxis=dict(range=[0, 105], title="Importância (0–100)"),
        yaxis=dict(range=[0, 105], title="Concordância (0–100)"),
        legend_title="Quadrante",
        font=dict(size=14),
        margin=dict(t=55, b=10, l=10, r=10),
    )

    tabela = df_p[["Afirmativa_Unificada", "Concordância (%)", "Importância (norm.)", "Quadrante"]].copy()
    tabela["Concordância (%)"]    = tabela["Concordância (%)"].round(1)
    tabela["Importância (norm.)"] = tabela["Importância (norm.)"].round(1)

    return html.Div(
        [
            dbc.Row(
                dbc.Col(
                    dash_table.DataTable(
                        data=tabela.to_dict("records"),
                        columns=[
                            {"name": "Afirmativa",          "id": "Afirmativa_Unificada"},
                            {"name": "Concordância (%)",    "id": "Concordância (%)"},
                            {"name": "Importância (0–100)", "id": "Importância (norm.)"},
                            {"name": "Quadrante",           "id": "Quadrante"},
                        ],
                        sort_action="native",
                        filter_action="native",
                        page_size=15,
                        style_table={"overflowX": "auto"},
                        style_cell={
                            "textAlign": "left",
                            "padding": "8px 12px",
                            "fontFamily": "sans-serif",
                            "fontSize": "13px",
                            "whiteSpace": "normal",
                            "height": "auto",
                        },
                        style_header={
                            "backgroundColor": "#808080",
                            "color": "white",
                            "fontWeight": "bold",
                        },
                        style_data_conditional=[
                            {
                                "if": {"filter_query": '{Quadrante} = "Alta Prioridade"'},
                                "backgroundColor": "#FFE5E5",
                                "color": "#D01020",
                            },
                            {
                                "if": {"filter_query": '{Quadrante} = "Ponto Forte"'},
                                "backgroundColor": "#E5F5EC",
                                "color": "#006B34",
                            },
                        ],
                    ),
                    md=12,
                ),
                className="mb-4",
            ),
            dbc.Row(
                dbc.Col(
                    dcc.Graph(figure=fig, style={"height": "560px"}, config={"displayModeBar": False}),
                    md=12,
                ),
                className="mb-4",
            ),
        ],
        className="pt-4",
    )




def _build_panorama_eficacia():
    configs = [
        ("EFICACIA_PROFISSIONAIS", "Profissionais", "#D01020"),
        ("EFICACIA_ALUNO",         "Estudantes",    "#009B4E"),
        ("EFICACIA_PAIS",          "Responsáveis",  "#F5C518"),
    ]

    cols = []
    for col, label, cor in configs:
        serie = respondentes[col].dropna()
        n = len(serie)
        media = serie.mean()

        fig = go.Figure()
        fig.add_trace(go.Histogram(
            x=serie,
            nbinsx=30,
            marker_color=cor,
            opacity=0.85,
            showlegend=False,
        ))
        fig.add_vline(
            x=media,
            line_dash="dash",
            line_color="#333333",
            line_width=2,
            annotation_text=f"Média: {media:.1f}",
            annotation_position="top right",
            annotation_font_size=13,
        )
        fig.update_layout(
            paper_bgcolor="white",
            plot_bgcolor="white",
            xaxis=dict(title="Eficácia Estimada"),
            yaxis=dict(title="Frequência"),
            margin=dict(t=40, b=40, l=50, r=20),
            font=dict(size=13),
            height=320,
        )

        card = dbc.Card(
            dbc.CardBody([
                html.H5(label, className="fw-bold text-center mb-2",
                        style={"color": cor}),
                html.P(f"{n:,} respondentes",
                       className="text-center text-muted small mb-1"),
                html.Div([
                    html.Span("Eficácia média estimada: ",
                              style={"fontSize": "0.95rem", "color": "#555"}),
                    html.Br(),
                    html.Span(f"{media:.1f}",
                              style={"fontSize": "2.4rem", "fontWeight": "bold",
                                     "color": cor, "lineHeight": "1.1"}),
                ], className="text-center mb-3"),
                dcc.Graph(figure=fig, config={"displayModeBar": False}),
            ]),
            className="shadow-sm border-0 h-100",
            style={"backgroundColor": "white"},
        )
        cols.append(dbc.Col(card, md=4))

    return html.Div(
        dbc.Row(cols, className="g-4"),
        className="pt-4",
    )


app.layout = html.Div(
    [
        navbar,
        dbc.Container(
            [
                html.Div(id="resize-trigger", style={"display": "none"}),
                dcc.Tabs(
                    id="main-tabs",
                    value="visao-geral",
                    className="mb-2",
                    children=[
                        dcc.Tab(
                            label="Visão Geral",
                            value="visao-geral",
                            children=html.Div(
                                [
                                    dbc.Button("Filtros", id="btn-filtros-geral",
                                               color="secondary", size="lg",
                                               className="mb-2 fw-semibold",
                                               style={"borderRadius": "20px", "letterSpacing": "0.05em"}),
                                    dbc.Collapse(filtros, id="collapse-geral", is_open=False),
                                    dcc.Tabs(
                                        id="visao-geral-tabs",
                                        value="visao-panorama",
                                        className="mt-3 mb-2",
                                        children=[
                                            dcc.Tab(
                                                label="Panorama Geral",
                                                value="visao-panorama",
                                                children=html.Div(
                                                    [cards, pizzas, grafico_cre, grafico_categoria],
                                                    className="pt-4",
                                                ),
                                            ),
                                            dcc.Tab(
                                                label="Panorama Geral de Eficácia Estimada",
                                                value="visao-eficacia",
                                                children=_build_panorama_eficacia(),
                                            ),
                                        ],
                                    ),
                                ],
                                className="pt-4",
                            ),
                        ),
                        dcc.Tab(
                            label="Estudantes",
                            value="alunos",
                            children=html.Div([
                                dbc.Button("Filtros", id="btn-filtros-alunos",
                                           color="secondary", size="lg",
                                           className="mb-2 fw-semibold",
                                           style={"borderRadius": "20px", "letterSpacing": "0.05em"}),
                                dbc.Collapse(filtros_alunos, id="collapse-alunos", is_open=False),
                                dcc.Tabs(
                                    id="alunos-tabs",
                                    value="alunos-resultados",
                                    className="mt-3 mb-2",
                                    children=[
                                        dcc.Tab(label="Resultados por Categoria", value="alunos-resultados", children=conteudo_alunos),
                                        dcc.Tab(label="Análise de Prioridades", value="alunos-prio",
                                                children=html.Div(id="prioridades-alunos-content", className="pt-4")),
                                    ],
                                ),
                            ], className="pt-3"),
                        ),
                        dcc.Tab(
                            label="Responsáveis",
                            value="responsaveis",
                            children=html.Div([
                                dbc.Button("Filtros", id="btn-filtros-resp",
                                           color="secondary", size="lg",
                                           className="mb-2 fw-semibold",
                                           style={"borderRadius": "20px", "letterSpacing": "0.05em"}),
                                dbc.Collapse(filtros_resp, id="collapse-resp", is_open=False),
                                dcc.Tabs(
                                    id="resp-tabs",
                                    value="resp-resultados",
                                    className="mt-3 mb-2",
                                    children=[
                                        dcc.Tab(label="Resultados por Categoria", value="resp-resultados", children=conteudo_resp),
                                        dcc.Tab(label="Análise de Prioridades", value="resp-prio",
                                                children=html.Div(id="prioridades-resp-content", className="pt-4")),
                                    ],
                                ),
                            ], className="pt-3"),
                        ),
                        dcc.Tab(
                            label="Profissionais",
                            value="profissionais",
                            children=html.Div(
                                [
                                    dbc.Button("Filtros", id="btn-filtros-prof",
                                               color="secondary", size="lg",
                                               className="mb-2 fw-semibold",
                                               style={"borderRadius": "20px", "letterSpacing": "0.05em"}),
                                    dbc.Collapse(filtros_prof, id="collapse-prof", is_open=False),
                                    dcc.Tabs(
                                        id="prof-tabs",
                                        value="diretiva",
                                        className="mt-3 mb-2",
                                        children=[
                                            dcc.Tab(
                                                label="Perspectiva Equipe Diretiva",
                                                value="diretiva",
                                                children=conteudo_diretiva,
                                            ),
                                            dcc.Tab(label="Perspectiva Equipe Docente", value="docente", children=conteudo_docente),
                                            dcc.Tab(label="Geral", value="geral", children=conteudo_geral),
                                            dcc.Tab(label="Análise de Prioridades", value="prioridades",
                                                    children=html.Div(id="prioridades-prof-content", className="pt-4")),
                                        ],
                                    ),
                                ],
                                className="pt-3",
                            ),
                        ),
                    ],
                ),
            ],
            fluid=True,
            className="py-4 px-4",
        ),
    ],
    style={"backgroundColor": "#F8F9FA", "minHeight": "100vh"},
)


# ── Callbacks ─────────────────────────────────────────────────────────────────

@app.callback(
    Output("escola-filter", "options"),
    Output("escola-filter", "value"),
    Input("municipio-filter", "value"),
)
def atualizar_escolas(municipio):
    if municipio:
        opcoes = sorted(
            df[df["Cidade da Escola"] == municipio]["Nome da Escola"].dropna().unique()
        )
    else:
        opcoes = sorted(df["Nome da Escola"].dropna().unique())
    return [{"label": e, "value": e} for e in opcoes], None


@app.callback(
    Output("card-respondentes", "children"),
    Output("card-perfis", "children"),
    Output("card-escolas", "children"),
    Output("card-municipios", "children"),
    Input("municipio-filter", "value"),
    Input("escola-filter", "value"),
)
def atualizar_cards(municipio, escola):
    dff = filter_df(municipio, escola)

    n_resp = dff["ID_Respondente"].nunique()
    perfil_counts = dff.groupby("Perfil")["ID_Respondente"].nunique()
    _label_perfil = {"Aluno": "Estudante", "Responsável": "Responsável", "Profissional": "Profissional"}
    perfis_str = "  |  ".join(
        f"{_label_perfil[p]}: {perfil_counts.get(p, 0):,}"
        for p in ["Aluno", "Responsável", "Profissional"]
    )
    n_escolas = dff["Nome da Escola"].nunique()
    n_municipios = dff["Cidade da Escola"].nunique()

    return f"{n_resp:,}", perfis_str, f"{n_escolas:,}", f"{n_municipios:,}"


@app.callback(
    Output("pizza-perfil", "figure"),
    Input("municipio-filter", "value"),
    Input("escola-filter", "value"),
)
def atualizar_pizza(municipio, escola):
    dff = filter_df(municipio, escola)
    counts = (
        dff.groupby("Perfil")["ID_Respondente"]
        .nunique()
        .reset_index(name="Quantidade")
    )
    counts["Perfil"] = counts["Perfil"].replace({"Aluno": "Estudante"})

    fig = px.pie(
        counts,
        names="Perfil",
        values="Quantidade",
        color="Perfil",
        color_discrete_map=PERFIL_COLORS,
        title="Distribuição de Respondentes por Perfil",
        hole=0.45,
    )
    fig.update_traces(textposition="outside", textinfo="percent+label")
    fig.update_layout(
        paper_bgcolor="white",
        showlegend=False,
        margin=dict(t=55, b=10, l=10, r=10),
        font=dict(size=15),
    )
    return fig


@app.callback(
    Output("pizza-genero", "figure"),
    Input("municipio-filter", "value"),
    Input("escola-filter", "value"),
)
def atualizar_pizza_genero(municipio, escola):
    dff = filter_df(municipio, escola)
    counts = (
        dff.drop_duplicates("ID_Respondente")
        .assign(Gênero=lambda d: d["Gênero"].fillna("Não informado"))
        .groupby("Gênero")
        .size()
        .reset_index(name="Quantidade")
    )

    fig = px.pie(
        counts,
        names="Gênero",
        values="Quantidade",
        title="Distribuição de Gênero dos Respondentes",
        hole=0.45,
        color_discrete_sequence=["#636EFA", "#EF553B", "#FFA15A", "#B6B6B6"],
    )
    fig.update_traces(textposition="outside", textinfo="percent+label")
    fig.update_layout(
        paper_bgcolor="white",
        showlegend=False,
        margin=dict(t=55, b=10, l=10, r=10),
        font=dict(size=15),
    )
    return fig


@app.callback(
    Output("barras-categoria", "figure"),
    Output("barras-categoria", "style"),
    Input("municipio-filter", "value"),
    Input("escola-filter", "value"),
)
def atualizar_barras_categoria(municipio, escola):
    dff = filter_df(municipio, escola)
    _excluir = {"Demográfico", "Relação Ensino-aprendizagem, Currículo e Práticas Pedagógicas (respondido apenas por professores(as))"}
    dff = dff[(dff["Métrica"] == "Concordância") & (~dff["Categoria"].isin(_excluir))]

    grouped = (
        dff.groupby(["Categoria", "Perfil"])["Resposta_Numerica"]
        .mean()
        .reset_index(name="Média")
    )
    grouped["Média"] = grouped["Média"] * 100
    grouped["Perfil"] = grouped["Perfil"].replace({"Aluno": "Estudante"})

    ordem = (
        grouped.groupby("Categoria")["Média"]
        .mean()
        .sort_values()
        .index.tolist()
    )

    n_cats = grouped["Categoria"].nunique()

    fig = px.bar(
        grouped,
        x="Média",
        y="Categoria",
        color="Perfil",
        barmode="group",
        color_discrete_map=PERFIL_COLORS,
        orientation="h",
        title="Média de Concordância por Categoria Temática (comparativo por Perfil)",
        labels={"Média": "Concordância (%)", "Categoria": ""},
        category_orders={"Categoria": ordem},
        text_auto=".1f",
    )
    fig.update_traces(textfont_size=13)
    fig.update_layout(
        paper_bgcolor="white",
        plot_bgcolor="white",
        legend_title="Perfil",
        margin=dict(t=55, b=10, l=320, r=10),
        xaxis=dict(range=[0, 100], title="Concordância (%)"),
        yaxis=dict(title=""),
        bargap=0.05,
        bargroupgap=0.02,
        font=dict(size=14),
    )
    height = max(420, n_cats * 80)
    return fig, {"height": f"{height}px"}



@app.callback(
    Output("barras-cre", "figure"),
    Output("barras-cre", "style"),
    Input("municipio-filter", "value"),
    Input("escola-filter", "value"),
)
def atualizar_barras_cre(municipio, escola):
    dff = filter_df(municipio, escola)

    counts = (
        dff.groupby(["CRE", "Perfil"])["ID_Respondente"]
        .nunique()
        .reset_index(name="Respondentes")
    )
    counts["Perfil"] = counts["Perfil"].replace({"Aluno": "Estudante"})
    totais = counts.groupby("CRE")["Respondentes"].sum().to_dict()

    ordem_cre = [v for v in CRE_LABEL.values() if v in counts["CRE"].unique()]

    fig = px.bar(
        counts,
        x="CRE",
        y="Respondentes",
        color="Perfil",
        color_discrete_map=PERFIL_COLORS,
        barmode="stack",
        title="Respondentes por Coordenadoria Regional de Educação (CRE)",
        text="Respondentes",
        category_orders={"CRE": ordem_cre},
    )
    fig.update_traces(textposition="inside", textfont_size=14)

    for cre, total in totais.items():
        fig.add_annotation(
            x=cre,
            y=total,
            text=f"<b>{total:,}</b>",
            showarrow=False,
            yshift=14,
            font=dict(size=15),
        )

    fig.update_layout(
        paper_bgcolor="white",
        plot_bgcolor="white",
        legend_title="Perfil",
        margin=dict(t=60, b=10, l=10, r=10),
        yaxis_title="Respondentes únicos",
        xaxis_title="",
        font=dict(size=14),
    )
    return fig, {"height": "420px"}



@app.callback(
    Output("card-diretiva-n", "children"),
    Output("card-diretiva-ch", "children"),
    Output("card-diretiva-efetivo", "children"),
    Output("likert-diretiva", "figure"),
    Input("prof-cre-filter", "value"),
    Input("prof-funcao-filter", "value"),
    Input("prof-genero-filter", "value"),
    Input("prof-as12-filter", "value"),
    Input("prof-estudou-filter", "value"),
    Input("prof-vinculo-filter", "value"),
    Input("prof-nescolas-filter", "value"),
)
def atualizar_diretiva(cre, funcao, genero, as12_val, estudou, vinculo, nescolas):
    dff = filter_prof_df(cre, funcao, genero, as12_val, estudou, vinculo, nescolas)
    subset = dff[dff["Função na Escola"] == FUNC_DIRETIVA].drop_duplicates("ID_Respondente")
    n = len(subset)
    ch = f"{subset['Carga Horária Semanal'].mean():.0f}h" if n else "—"
    efetivo = f"{(subset['Vínculo de Trabalho'] == 'Efetivo').mean() * 100:.0f}%" if n else "—"
    return str(n), ch, efetivo, _build_likert_diretiva(dff)


@app.callback(
    Output("docente-selecoes", "figure"),
    Output("docente-importancia", "figure"),
    Input("prof-cre-filter", "value"),
    Input("prof-funcao-filter", "value"),
    Input("prof-genero-filter", "value"),
    Input("prof-as12-filter", "value"),
    Input("prof-estudou-filter", "value"),
    Input("prof-vinculo-filter", "value"),
    Input("prof-nescolas-filter", "value"),
)
def atualizar_docente(cre, funcao, genero, as12_val, estudou, vinculo, nescolas):
    dff = filter_prof_df(cre, funcao, genero, as12_val, estudou, vinculo, nescolas)
    return _build_docente_selecoes(dff), _build_docente_importancia(dff)


@app.callback(
    Output("geral-selecoes", "figure"),
    Output("geral-importancia", "figure"),
    Output("geral-wordcloud", "figure"),
    Input("geral-cat-filter", "value"),
    Input("prof-cre-filter", "value"),
    Input("prof-funcao-filter", "value"),
    Input("prof-genero-filter", "value"),
    Input("prof-as12-filter", "value"),
    Input("prof-estudou-filter", "value"),
    Input("prof-vinculo-filter", "value"),
    Input("prof-nescolas-filter", "value"),
)
def atualizar_geral(categoria, cre, funcao, genero, as12_val, estudou, vinculo, nescolas):
    dff = filter_prof_df(cre, funcao, genero, as12_val, estudou, vinculo, nescolas)
    fig_sel, fig_imp = _figs_selecoes_importancia(categoria, "Profissional", dff)
    fig_wc = _build_wordcloud_figure(categoria, "Profissional", dff)
    return fig_sel, fig_imp, fig_wc


@app.callback(
    Output("prioridades-prof-content", "children"),
    Input("prof-cre-filter", "value"),
    Input("prof-funcao-filter", "value"),
    Input("prof-genero-filter", "value"),
    Input("prof-as12-filter", "value"),
    Input("prof-estudou-filter", "value"),
    Input("prof-vinculo-filter", "value"),
    Input("prof-nescolas-filter", "value"),
)
def atualizar_prioridades_prof(cre, funcao, genero, as12_val, estudou, vinculo, nescolas):
    dff = filter_prof_df(cre, funcao, genero, as12_val, estudou, vinculo, nescolas)
    return _build_prioridades("Profissional", dff)


@app.callback(
    Output("alunos-selecoes", "figure"),
    Output("alunos-importancia", "figure"),
    Output("alunos-wordcloud", "figure"),
    Input("alunos-cat-filter", "value"),
    Input("aluno-cre-filter", "value"),
    Input("aluno-genero-filter", "value"),
    Input("aluno-modal-filter", "value"),
    Input("aluno-as12-filter", "value"),
    Input("aluno-familiar-filter", "value"),
    Input("aluno-faixa-filter", "value"),
    Input("aluno-jovem-filter", "value"),
)
def atualizar_alunos(categoria, cre, genero, modal, as12_val, familiar, faixa, jovem):
    dff = filter_alunos_df(cre, genero, modal, as12_val, familiar, faixa, jovem)
    fig_sel, fig_imp = _figs_selecoes_importancia(categoria, "Aluno", dff)
    return fig_sel, fig_imp, _build_wordcloud_figure(categoria, "Aluno", dff)


@app.callback(
    Output("prioridades-alunos-content", "children"),
    Input("aluno-cre-filter", "value"),
    Input("aluno-genero-filter", "value"),
    Input("aluno-modal-filter", "value"),
    Input("aluno-as12-filter", "value"),
    Input("aluno-familiar-filter", "value"),
    Input("aluno-faixa-filter", "value"),
    Input("aluno-jovem-filter", "value"),
)
def atualizar_prioridades_alunos(cre, genero, modal, as12_val, familiar, faixa, jovem):
    dff = filter_alunos_df(cre, genero, modal, as12_val, familiar, faixa, jovem)
    return _build_prioridades("Aluno", dff)


@app.callback(
    Output("resp-selecoes", "figure"),
    Output("resp-importancia", "figure"),
    Output("resp-wordcloud", "figure"),
    Input("resp-cat-filter", "value"),
    Input("resp-cre-filter", "value"),
    Input("resp-genero-filter", "value"),
    Input("resp-parentesco-filter", "value"),
    Input("resp-as12-filter", "value"),
    Input("resp-estudou-filter", "value"),
    Input("resp-jovem-filter", "value"),
)
def atualizar_responsaveis(categoria, cre, genero, parentesco, as12_val, estudou, jovem):
    dff = filter_resp_df(cre, genero, parentesco, as12_val, estudou, jovem)
    fig_sel, fig_imp = _figs_selecoes_importancia(categoria, "Responsável", dff)
    return fig_sel, fig_imp, _build_wordcloud_figure(categoria, "Responsável", dff)


@app.callback(
    Output("prioridades-resp-content", "children"),
    Input("resp-cre-filter", "value"),
    Input("resp-genero-filter", "value"),
    Input("resp-parentesco-filter", "value"),
    Input("resp-as12-filter", "value"),
    Input("resp-estudou-filter", "value"),
    Input("resp-jovem-filter", "value"),
)
def atualizar_prioridades_resp(cre, genero, parentesco, as12_val, estudou, jovem):
    dff = filter_resp_df(cre, genero, parentesco, as12_val, estudou, jovem)
    return _build_prioridades("Responsável", dff)


@app.callback(
    Output("collapse-geral", "is_open"),
    Output("btn-filtros-geral", "children"),
    Input("btn-filtros-geral", "n_clicks"),
    State("collapse-geral", "is_open"),
    prevent_initial_call=True,
)
def toggle_filtros_geral(_, is_open):
    novo = not is_open
    return novo, "Ocultar Filtros" if novo else "Filtros"


@app.callback(
    Output("collapse-alunos", "is_open"),
    Output("btn-filtros-alunos", "children"),
    Input("btn-filtros-alunos", "n_clicks"),
    State("collapse-alunos", "is_open"),
    prevent_initial_call=True,
)
def toggle_filtros_alunos(_, is_open):
    novo = not is_open
    return novo, "Ocultar Filtros" if novo else "Filtros"


@app.callback(
    Output("collapse-resp", "is_open"),
    Output("btn-filtros-resp", "children"),
    Input("btn-filtros-resp", "n_clicks"),
    State("collapse-resp", "is_open"),
    prevent_initial_call=True,
)
def toggle_filtros_resp(_, is_open):
    novo = not is_open
    return novo, "Ocultar Filtros" if novo else "Filtros"


@app.callback(
    Output("collapse-prof", "is_open"),
    Output("btn-filtros-prof", "children"),
    Input("btn-filtros-prof", "n_clicks"),
    State("collapse-prof", "is_open"),
    prevent_initial_call=True,
)
def toggle_filtros_prof(_, is_open):
    novo = not is_open
    return novo, "Ocultar Filtros" if novo else "Filtros"


app.clientside_callback(
    """
    function(t1, t2, t3, t4, t5) {
        function resizeAll() {
            var graphs = document.querySelectorAll('.js-plotly-plot');
            for (var i = 0; i < graphs.length; i++) {
                try { Plotly.Plots.resize(graphs[i]); } catch(e) {}
            }
        }
        setTimeout(resizeAll, 100);
        setTimeout(resizeAll, 300);
        setTimeout(resizeAll, 600);
        return window.dash_clientside.no_update;
    }
    """,
    Output("resize-trigger", "children"),
    Input("main-tabs", "value"),
    Input("alunos-tabs", "value"),
    Input("resp-tabs", "value"),
    Input("prof-tabs", "value"),
    Input("visao-geral-tabs", "value"),
    prevent_initial_call=True,
)

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8050)
