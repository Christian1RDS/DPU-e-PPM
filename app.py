
import io
import sqlite3
from datetime import date, datetime, time, timedelta
from calendar import monthrange

import pandas as pd
import streamlit as st

# ============================================================
# CONFIGURAÇÃO GERAL
# ============================================================
st.set_page_config(
    page_title="DPU & PPM - Base RFT",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_PADRAO = "rft_v61_local.db"
REQ = ["NR_WO", "DT_HR_INSPECAO", "C_DPU_QG_AMARELO", "CD_POSTO_CN"]
POSTOS_PADRAO = ["QG09", "QG07"]
DEFAULT_META_RFT = 95.0
DEFAULT_META_PPM = 50000

CSS = """
<style>
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }

    .hero {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 55%, #0369a1 100%);
        color: white;
        border-radius: 26px;
        padding: 30px 34px;
        margin-bottom: 22px;
        box-shadow: 0 18px 45px rgba(15, 23, 42, 0.24);
    }

    .hero .tag {
        display: inline-block;
        padding: 7px 12px;
        border-radius: 999px;
        background: rgba(255,255,255,0.13);
        font-weight: 700;
        font-size: 0.84rem;
        margin-bottom: 12px;
    }

    .hero h1 {
        margin: 0;
        font-size: 2.2rem;
        line-height: 1.12;
        font-weight: 900;
        letter-spacing: -0.04em;
    }

    .hero p {
        margin-top: 10px;
        color: #dbeafe;
        font-size: 1.02rem;
        max-width: 980px;
    }

    .metric-card {
        border-radius: 22px;
        padding: 20px;
        background: white;
        box-shadow: 0 10px 28px rgba(15,23,42,0.09);
        border: 1px solid rgba(148,163,184,0.25);
        min-height: 142px;
    }

    .metric-card .label {
        font-size: 0.82rem;
        color: #64748b;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }

    .metric-card .value {
        font-size: 2.0rem;
        font-weight: 950;
        color: #0f172a;
        margin-top: 6px;
        letter-spacing: -0.03em;
    }

    .metric-card .sub {
        font-size: 0.86rem;
        color: #64748b;
        margin-top: 6px;
    }

    .ok { border-left: 8px solid #16a34a; }
    .bad { border-left: 8px solid #dc2626; }
    .neutral { border-left: 8px solid #2563eb; }
    .warn { border-left: 8px solid #f59e0b; }

    .section-title {
        margin-top: 10px;
        margin-bottom: 10px;
        color: #0f172a;
        font-weight: 900;
        letter-spacing: -0.03em;
    }

    .formula-box {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 18px;
        padding: 18px;
        color: #334155;
        margin-bottom: 12px;
    }

    .formula-box code {
        background: white;
        padding: 3px 7px;
        border-radius: 8px;
        color: #0f172a;
        font-weight: 700;
    }
</style>
"""

# ============================================================
# FUNÇÕES DE LEITURA E PREPARAÇÃO
# ============================================================
def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(x).strip().replace("\ufeff", "") for x in out.columns]
    return out


def read_file(uploaded_file) -> pd.DataFrame:
    ext = uploaded_file.name.lower().split(".")[-1]
    content = uploaded_file.getvalue()

    if ext == "csv":
        last_err = None
        for enc in ["utf-8-sig", "utf-16", "latin1"]:
            for sep in [None, ";", ",", "\t"]:
                try:
                    if sep is None:
                        return normalize_columns(pd.read_csv(io.BytesIO(content), encoding=enc, sep=None, engine="python"))
                    return normalize_columns(pd.read_csv(io.BytesIO(content), encoding=enc, sep=sep))
                except Exception as err:
                    last_err = err
        raise ValueError(f"Não foi possível ler o CSV. Detalhe: {last_err}")

    if ext in ["xlsx", "xls"]:
        engine = "openpyxl" if ext == "xlsx" else "xlrd"
        return normalize_columns(pd.read_excel(io.BytesIO(content), engine=engine))

    raise ValueError("Formato não suportado. Use .xlsx, .xls ou .csv")


def validate_df(df: pd.DataFrame):
    missing = [c for c in REQ if c not in df.columns]
    return len(missing) == 0, missing


def parse_dt(series: pd.Series) -> pd.Series:
    dt = pd.to_datetime(series, errors="coerce")
    mask = dt.isna() & series.notna()
    if mask.any():
        dt.loc[mask] = pd.to_datetime(series[mask], errors="coerce", dayfirst=True)
    return dt


def norm_posto(value) -> str:
    txt = str(value).upper().strip()
    if "QG09" in txt:
        return "QG09"
    if "QG07" in txt:
        return "QG07"
    return txt


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work["DT_HR_INSPECAO"] = parse_dt(work["DT_HR_INSPECAO"])
    work["C_DPU_QG_AMARELO"] = pd.to_numeric(work["C_DPU_QG_AMARELO"], errors="coerce").fillna(0)
    work["NR_WO"] = work["NR_WO"].astype(str).str.strip()
    work["CD_POSTO_CN"] = work["CD_POSTO_CN"].astype(str).map(norm_posto)
    work = work[work["DT_HR_INSPECAO"].notna()].copy()
    return work[REQ].copy()


# ============================================================
# FONTE DE DADOS: SQLITE DO RFT OU UPLOAD DIRETO
# ============================================================
def load_from_sqlite(db_file: str) -> pd.DataFrame:
    conn = sqlite3.connect(db_file, check_same_thread=False)
    query = """
        SELECT
            nr_wo AS NR_WO,
            dt_hr_inspecao AS DT_HR_INSPECAO,
            c_dpu_qg_amarelo AS C_DPU_QG_AMARELO,
            cd_posto_cn AS CD_POSTO_CN
        FROM raw_inspections
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    if df.empty:
        return df
    return prepare(df)


# ============================================================
# MOTOR ÚNICO DE CÁLCULO
# ============================================================
def calcular_indicadores_qualidade(df: pd.DataFrame, start_date: date, end_date: date) -> dict:
    """
    Motor único de cálculo.
    Todos os indicadores saem do mesmo recorte, mesmo filtro e mesmo agrupamento.
    """
    if df is None or df.empty:
        return empty_metrics()

    sdt = datetime.combine(start_date, time(0, 0, 0))
    edt = datetime.combine(end_date, time(23, 59, 59))

    filt = df[(df["DT_HR_INSPECAO"] >= sdt) & (df["DT_HR_INSPECAO"] <= edt)].copy()
    if filt.empty:
        return empty_metrics()

    grp = (
        filt.groupby("NR_WO", as_index=False)["C_DPU_QG_AMARELO"]
        .sum()
        .rename(columns={"C_DPU_QG_AMARELO": "SOMA_DEFEITOS"})
    )

    grp["RFT"] = (grp["SOMA_DEFEITOS"] == 0).astype(int)

    total = int(len(grp))
    good = int(grp["RFT"].sum())
    bad = int(total - good)
    defects = float(grp["SOMA_DEFEITOS"].sum())

    rft_pct = round((good / total) * 100, 2) if total else None
    dpu = round(defects / total, 4) if total else None
    ppm_defects = round((defects / total) * 1_000_000, 0) if total else None
    ppm_bad_units = round((bad / total) * 1_000_000, 0) if total else None

    return {
        "rft_pct": rft_pct,
        "total": total,
        "good": good,
        "bad": bad,
        "defects": defects,
        "dpu": dpu,
        "ppm_defects": ppm_defects,
        "ppm_bad_units": ppm_bad_units,
        "detail_by_wo": grp,
    }


def empty_metrics() -> dict:
    return {
        "rft_pct": None,
        "total": 0,
        "good": 0,
        "bad": 0,
        "defects": 0,
        "dpu": None,
        "ppm_defects": None,
        "ppm_bad_units": None,
        "detail_by_wo": pd.DataFrame(columns=["NR_WO", "SOMA_DEFEITOS", "RFT"]),
    }


# ============================================================
# PERÍODOS E TENDÊNCIAS
# ============================================================
def week_options(df: pd.DataFrame, year: int):
    ydf = df[df["DT_HR_INSPECAO"].dt.year == year].copy()
    if ydf.empty:
        return []
    dates = sorted(ydf["DT_HR_INSPECAO"].dt.date.unique().tolist())
    mondays = sorted({d - timedelta(days=d.weekday()) for d in dates})
    return [
        (f"Semana {idx:02d} - {m.strftime('%d/%m/%Y')} a {(m + timedelta(days=6)).strftime('%d/%m/%Y')}", m, m + timedelta(days=6))
        for idx, m in enumerate(mondays, start=1)
    ]


def month_options(df: pd.DataFrame, year: int):
    ydf = df[df["DT_HR_INSPECAO"].dt.year == year].copy()
    if ydf.empty:
        return []
    opts = []
    for month in sorted(ydf["DT_HR_INSPECAO"].dt.month.unique().tolist()):
        start = date(year, int(month), 1)
        end = date(year, int(month), monthrange(year, int(month))[1])
        opts.append((f"{start.strftime('%m/%Y')} - {start.strftime('%d/%m/%Y')} a {end.strftime('%d/%m/%Y')}", start, end))
    return opts


def trend_monthly(df: pd.DataFrame, year: int, meta_rft: float, meta_ppm: float) -> pd.DataFrame:
    rows = []
    for label, start, end in month_options(df, year):
        m = calcular_indicadores_qualidade(df, start, end)
        rows.append({
            "Mês": label.split(" - ")[0],
            "RFT": m["rft_pct"] or 0,
            "Meta RFT": meta_rft,
            "DPU": m["dpu"] or 0,
            "PPM Defeitos": m["ppm_defects"] or 0,
            "Meta PPM": meta_ppm,
            "PPM Não RFT": m["ppm_bad_units"] or 0,
            "Total": m["total"],
            "Defeitos": m["defects"],
        })
    return pd.DataFrame(rows)


# ============================================================
# FORMATAÇÃO E COMPONENTES VISUAIS
# ============================================================
def br_int(v):
    if v is None or pd.isna(v):
        return "Sem dados"
    return f"{float(v):,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")


def br_float(v, digits=2):
    if v is None or pd.isna(v):
        return "Sem dados"
    return f"{float(v):,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def br_pct(v):
    if v is None or pd.isna(v):
        return "Sem dados"
    return br_float(v, 2) + "%"


def card(label, value, sub="", status="neutral"):
    st.markdown(
        f"""
        <div class="metric-card {status}">
            <div class="label">{label}</div>
            <div class="value">{value}</div>
            <div class="sub">{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_rft(value, meta):
    if value is None or pd.isna(value):
        return "neutral"
    return "ok" if value >= meta else "bad"


def status_ppm(value, meta):
    if value is None or pd.isna(value):
        return "neutral"
    return "ok" if value <= meta else "bad"


# ============================================================
# APP
# ============================================================
def main():
    st.markdown(CSS, unsafe_allow_html=True)

    st.markdown(
        """
        <div class="hero">
            <div class="tag">Segundo site • puxando a base do RFT</div>
            <h1>DPU & PPM a partir do RFT</h1>
            <p>
                Este painel usa a mesma lógica da base RFT: agrupa por NR_WO, soma os defeitos e calcula RFT, DPU e PPM no mesmo motor de cálculo.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("Fonte de dados")
        fonte = st.radio(
            "Como o site deve puxar os dados?",
            ["Banco SQLite do site RFT", "Upload direto de base"],
            index=0,
        )

        df = pd.DataFrame()

        if fonte == "Banco SQLite do site RFT":
            db_file = st.text_input("Arquivo SQLite", value=DB_PADRAO)
            st.caption("Use esta opção se o arquivo .db do site RFT estiver junto deste app.")
            if st.button("Carregar banco RFT", use_container_width=True, type="primary"):
                try:
                    df = load_from_sqlite(db_file)
                    st.session_state["df_base"] = df
                    st.success(f"Banco carregado: {len(df)} linhas válidas.")
                except Exception as err:
                    st.error(f"Não foi possível carregar o banco: {err}")
        else:
            uploaded = st.file_uploader("Base RFT/operacional (.xlsx, .xls ou .csv)", type=["xlsx", "xls", "csv"])
            if uploaded is not None:
                try:
                    raw = read_file(uploaded)
                    ok, missing = validate_df(raw)
                    if not ok:
                        st.error("Base inválida. Colunas faltantes: " + ", ".join(missing))
                    else:
                        df = prepare(raw)
                        st.session_state["df_base"] = df
                        st.success(f"Arquivo carregado: {len(df)} linhas válidas.")
                except Exception as err:
                    st.error(f"Erro ao ler arquivo: {err}")

        df = st.session_state.get("df_base", pd.DataFrame())

        st.divider()
        st.header("Filtros")

        if df.empty:
            st.info("Carregue uma fonte de dados para liberar os filtros.")
            posto = None
            ano = None
            start_date = None
            end_date = None
        else:
            postos = sorted(df["CD_POSTO_CN"].dropna().unique().tolist())
            postos = [p for p in postos if p] or POSTOS_PADRAO
            posto = st.selectbox("Posto", postos, index=0)
            df = df[df["CD_POSTO_CN"] == posto].copy()

            anos = sorted(df["DT_HR_INSPECAO"].dt.year.dropna().astype(int).unique().tolist())
            ano = st.selectbox("Ano", anos, index=len(anos) - 1)
            df = df[df["DT_HR_INSPECAO"].dt.year == ano].copy()

            modo = st.radio("Modo", ["Diário", "Semanal", "Mensal", "Anual", "Personalizado"], index=2)

            min_d = df["DT_HR_INSPECAO"].dt.date.min()
            max_d = df["DT_HR_INSPECAO"].dt.date.max()

            if modo == "Diário":
                selected = st.date_input("Dia", value=max_d, min_value=min_d, max_value=max_d, format="DD/MM/YYYY")
                start_date = end_date = selected
            elif modo == "Semanal":
                opts = week_options(df, ano)
                labels = [x[0] for x in opts]
                label = st.selectbox("Semana", labels, index=len(labels) - 1)
                found = next(x for x in opts if x[0] == label)
                start_date, end_date = found[1], found[2]
            elif modo == "Mensal":
                opts = month_options(df, ano)
                labels = [x[0] for x in opts]
                label = st.selectbox("Mês", labels, index=len(labels) - 1)
                found = next(x for x in opts if x[0] == label)
                start_date, end_date = found[1], found[2]
            elif modo == "Anual":
                start_date, end_date = date(ano, 1, 1), max_d
            else:
                periodo = st.date_input(
                    "Período personalizado",
                    value=(min_d, max_d),
                    min_value=min_d,
                    max_value=max_d,
                    format="DD/MM/YYYY",
                )
                if isinstance(periodo, tuple) and len(periodo) == 2:
                    start_date, end_date = periodo
                else:
                    start_date = end_date = max_d

        st.divider()
        st.header("Metas")
        meta_rft = st.number_input("Meta RFT (%)", min_value=0.0, max_value=100.0, value=DEFAULT_META_RFT, step=0.1)
        meta_ppm = st.number_input("Meta PPM por defeito", min_value=0, value=DEFAULT_META_PPM, step=1000)

    tabs = st.tabs(["Dashboard", "Tendência", "Base calculada", "Critério de cálculo"])

    if df.empty or start_date is None or end_date is None:
        with tabs[0]:
            st.info("Carregue a base do RFT ou faça upload de uma base para iniciar.")
        return

    metrics = calcular_indicadores_qualidade(df, start_date, end_date)

    with tabs[0]:
        st.subheader("Resultado do recorte selecionado")
        st.caption(f"Posto: {posto} | Ano: {ano} | Período: {start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            card("RFT", br_pct(metrics["rft_pct"]), f"Meta: {br_pct(meta_rft)}", status_rft(metrics["rft_pct"], meta_rft))
        with c2:
            card("DPU", br_float(metrics["dpu"], 4), "Defeitos ÷ total inspecionado", "neutral")
        with c3:
            card("PPM por defeito", br_int(metrics["ppm_defects"]), f"Meta: {br_int(meta_ppm)}", status_ppm(metrics["ppm_defects"], meta_ppm))
        with c4:
            card("PPM por peça não RFT", br_int(metrics["ppm_bad_units"]), "Peças não RFT ÷ total × 1.000.000", "warn")

        c5, c6, c7, c8 = st.columns(4)
        with c5:
            card("Total inspecionado", br_int(metrics["total"]), "Quantidade de NR_WO únicos", "neutral")
        with c6:
            card("Peças RFT", br_int(metrics["good"]), "WOs com zero defeito", "ok")
        with c7:
            card("Peças não RFT", br_int(metrics["bad"]), "WOs com defeito maior que zero", "bad" if metrics["bad"] else "ok")
        with c8:
            card("Total de defeitos", br_int(metrics["defects"]), "Soma de C_DPU_QG_AMARELO", "warn" if metrics["defects"] else "ok")

        st.markdown("### Leitura executiva")
        if metrics["total"] == 0:
            st.info("Sem dados para o recorte selecionado.")
        else:
            diff_rft = metrics["rft_pct"] - meta_rft if metrics["rft_pct"] is not None else None
            diff_ppm = metrics["ppm_defects"] - meta_ppm if metrics["ppm_defects"] is not None else None
            st.write(
                f"No período selecionado foram avaliadas **{br_int(metrics['total'])} WOs**, "
                f"com **{br_int(metrics['bad'])} não RFT** e **{br_int(metrics['defects'])} defeitos**. "
                f"O RFT ficou em **{br_pct(metrics['rft_pct'])}** "
                f"({br_float(diff_rft, 2)} p.p. contra a meta) e o PPM por defeito ficou em "
                f"**{br_int(metrics['ppm_defects'])}** ({br_int(diff_ppm)} contra a meta)."
            )

    with tabs[1]:
        st.subheader("Tendência mensal")
        trend = trend_monthly(df, ano, meta_rft, meta_ppm)
        if trend.empty:
            st.info("Sem dados para tendência.")
        else:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("#### RFT x Meta")
                st.bar_chart(trend.set_index("Mês")[["RFT", "Meta RFT"]], use_container_width=True)
            with c2:
                st.markdown("#### PPM por defeito x Meta")
                st.bar_chart(trend.set_index("Mês")[["PPM Defeitos", "Meta PPM"]], use_container_width=True)

            st.markdown("#### Tabela mensal")
            show = trend.copy()
            show["RFT"] = show["RFT"].map(br_pct)
            show["Meta RFT"] = show["Meta RFT"].map(br_pct)
            show["DPU"] = show["DPU"].map(lambda x: br_float(x, 4))
            show["PPM Defeitos"] = show["PPM Defeitos"].map(br_int)
            show["Meta PPM"] = show["Meta PPM"].map(br_int)
            show["PPM Não RFT"] = show["PPM Não RFT"].map(br_int)
            show["Total"] = show["Total"].map(br_int)
            show["Defeitos"] = show["Defeitos"].map(br_int)
            st.dataframe(show, use_container_width=True, hide_index=True)

    with tabs[2]:
        st.subheader("Base calculada por WO")
        st.caption("Esta tabela mostra o agrupamento usado para calcular RFT, DPU e PPM no período selecionado.")
        detail = metrics["detail_by_wo"].copy()
        if detail.empty:
            st.info("Sem dados no recorte.")
        else:
            detail["Status"] = detail["RFT"].map({1: "RFT", 0: "Não RFT"})
            detail = detail.rename(columns={"SOMA_DEFEITOS": "Defeitos na WO"})
            st.dataframe(detail[["NR_WO", "Defeitos na WO", "Status"]], use_container_width=True, hide_index=True)

            csv = detail[["NR_WO", "Defeitos na WO", "Status"]].to_csv(index=False, sep=";").encode("utf-8-sig")
            st.download_button(
                "Baixar base calculada em CSV",
                data=csv,
                file_name="base_calculada_dpu_ppm.csv",
                mime="text/csv",
                use_container_width=True,
            )

    with tabs[3]:
        st.subheader("Critério de cálculo travado")
        st.markdown(
            """
            <div class="formula-box">
                <b>Regra principal:</b> todos os indicadores usam o mesmo recorte de posto, ano e período.
            </div>
            <div class="formula-box">
                <code>Total inspecionado</code> = quantidade de <code>NR_WO</code> únicos no período.
            </div>
            <div class="formula-box">
                <code>Total de defeitos</code> = soma de <code>C_DPU_QG_AMARELO</code> agrupada por <code>NR_WO</code>.
            </div>
            <div class="formula-box">
                <code>Peça RFT</code> = <code>NR_WO</code> com soma de defeitos igual a zero.
            </div>
            <div class="formula-box">
                <code>RFT %</code> = peças RFT ÷ total inspecionado × 100.
            </div>
            <div class="formula-box">
                <code>DPU</code> = total de defeitos ÷ total inspecionado.
            </div>
            <div class="formula-box">
                <code>PPM por defeito</code> = DPU × 1.000.000.
            </div>
            <div class="formula-box">
                <code>PPM por peça não RFT</code> = peças não RFT ÷ total inspecionado × 1.000.000.
            </div>
            """,
            unsafe_allow_html=True,
        )


if __name__ == "__main__":
    main()
