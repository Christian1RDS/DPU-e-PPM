
import io
import sqlite3
from datetime import date, datetime, time, timedelta
from calendar import monthrange
import pandas as pd
import streamlit as st

st.set_page_config(page_title='DPU & PPM - Base RFT', page_icon='📊', layout='wide')

DB_APP = 'dpu_ppm_historico.db'
REQ = ['NR_WO', 'DT_HR_INSPECAO', 'C_DPU_QG_AMARELO', 'CD_POSTO_CN']
POSTOS_VALIDOS = ['QG09', 'QG07']
POSTO_PRINCIPAL = 'QG09'
DEFAULT_META_RFT = 95.0
DEFAULT_META_PPM = 50000

CSS = '<style>.metric-card{border-radius:18px;padding:18px;background:white;box-shadow:0 6px 18px rgba(15,23,42,.10);border:1px solid #e2e8f0;min-height:125px}.metric-card .label{font-size:.8rem;color:#64748b;font-weight:800;text-transform:uppercase}.metric-card .value{font-size:1.8rem;font-weight:900;color:#0f172a}.metric-card .sub{font-size:.85rem;color:#64748b}.ok{border-left:8px solid #16a34a}.bad{border-left:8px solid #dc2626}.neutral{border-left:8px solid #2563eb}.warn{border-left:8px solid #f59e0b}.hero{background:linear-gradient(135deg,#0f172a,#1e3a8a,#0369a1);color:white;border-radius:24px;padding:28px;margin-bottom:20px}.formula{background:#f8fafc;border:1px solid #e2e8f0;border-radius:16px;padding:16px;margin-bottom:10px}</style>'


def get_conn():
    return sqlite3.connect(DB_APP, check_same_thread=False)


def init_db(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS upload_log (id INTEGER PRIMARY KEY AUTOINCREMENT, file_name TEXT NOT NULL, uploaded_at TEXT NOT NULL, total_rows INTEGER NOT NULL, mode TEXT NOT NULL, status TEXT NOT NULL, message TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS raw_inspections (id INTEGER PRIMARY KEY AUTOINCREMENT, upload_id INTEGER NOT NULL, nr_wo TEXT, dt_hr_inspecao TEXT, c_dpu_qg_amarelo REAL, cd_posto_cn TEXT)')
    conn.commit()


def normalize_columns(df):
    out = df.copy()
    out.columns = [str(x).strip().replace('\ufeff', '') for x in out.columns]
    return out


def parse_dt(series):
    dt = pd.to_datetime(series, errors='coerce')
    mask = dt.isna() & series.notna()
    if mask.any():
        dt.loc[mask] = pd.to_datetime(series[mask], errors='coerce', dayfirst=True)
    return dt


def norm_posto(value):
    txt = str(value).upper().strip()
    if 'QG09' in txt:
        return 'QG09'
    if 'QG07' in txt:
        return 'QG07'
    return txt


def read_file(uploaded_file):
    ext = uploaded_file.name.lower().split('.')[-1]
    content = uploaded_file.getvalue()
    if ext == 'csv':
        last_err = None
        for enc in ['utf-8-sig', 'utf-16', 'latin1']:
            for sep in [None, ';', ',', '\t']:
                try:
                    if sep is None:
                        return normalize_columns(pd.read_csv(io.BytesIO(content), encoding=enc, sep=None, engine='python'))
                    return normalize_columns(pd.read_csv(io.BytesIO(content), encoding=enc, sep=sep))
                except Exception as err:
                    last_err = err
        raise ValueError(f'Não foi possível ler o CSV. Detalhe: {last_err}')
    if ext in ['xlsx', 'xls']:
        engine = 'openpyxl' if ext == 'xlsx' else 'xlrd'
        return normalize_columns(pd.read_excel(io.BytesIO(content), engine=engine))
    raise ValueError('Formato não suportado. Use .xlsx, .xls ou .csv')


def validate_df(df):
    missing = [c for c in REQ if c not in df.columns]
    return len(missing) == 0, missing


def prepare(df):
    work = df.copy()
    work['DT_HR_INSPECAO'] = parse_dt(work['DT_HR_INSPECAO'])
    work['C_DPU_QG_AMARELO'] = pd.to_numeric(work['C_DPU_QG_AMARELO'], errors='coerce').fillna(0)
    work['NR_WO'] = work['NR_WO'].astype(str).str.strip()
    work['CD_POSTO_CN'] = work['CD_POSTO_CN'].astype(str).map(norm_posto)
    work = work[work['DT_HR_INSPECAO'].notna()].copy()
    work = work[work['CD_POSTO_CN'].isin(POSTOS_VALIDOS)].copy()
    return work[REQ].copy()


def create_upload(conn, file_name, total_rows, mode, message=''):
    cur = conn.execute('INSERT INTO upload_log (file_name, uploaded_at, total_rows, mode, status, message) VALUES (?, ?, ?, ?, ?, ?)', (file_name, datetime.now().isoformat(timespec='seconds'), int(total_rows), mode, 'PROCESSADO', message))
    conn.commit()
    return int(cur.lastrowid)


def save_raw(conn, upload_id, df):
    rows = []
    for _, row in df.iterrows():
        rows.append((int(upload_id), str(row['NR_WO']), row['DT_HR_INSPECAO'].isoformat(sep=' ', timespec='seconds'), float(row['C_DPU_QG_AMARELO']), str(row['CD_POSTO_CN'])))
    conn.executemany('INSERT INTO raw_inspections (upload_id, nr_wo, dt_hr_inspecao, c_dpu_qg_amarelo, cd_posto_cn) VALUES (?, ?, ?, ?, ?)', rows)
    conn.commit()


def delete_overlapped_period(conn, df):
    for (year, posto), part in df.groupby([df['DT_HR_INSPECAO'].dt.year, 'CD_POSTO_CN']):
        start_dt = datetime.combine(part['DT_HR_INSPECAO'].dt.date.min(), time(0, 0, 0)).isoformat(sep=' ')
        end_dt = datetime.combine(part['DT_HR_INSPECAO'].dt.date.max(), time(23, 59, 59)).isoformat(sep=' ')
        conn.execute("DELETE FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=? AND datetime(dt_hr_inspecao) BETWEEN datetime(?) AND datetime(?)", (posto, str(int(year)), start_dt, end_dt))
    conn.commit()


def delete_year_for_upload_df(conn, df):
    for (year, posto), _ in df.groupby([df['DT_HR_INSPECAO'].dt.year, 'CD_POSTO_CN']):
        conn.execute("DELETE FROM raw_inspections WHERE cd_posto_cn=? AND strftime('%Y', dt_hr_inspecao)=?", (posto, str(int(year))))
    conn.commit()


def load_app_db(conn):
    df = pd.read_sql_query("SELECT upload_id, nr_wo AS NR_WO, dt_hr_inspecao AS DT_HR_INSPECAO, c_dpu_qg_amarelo AS C_DPU_QG_AMARELO, cd_posto_cn AS CD_POSTO_CN FROM raw_inspections WHERE cd_posto_cn IN ('QG09','QG07') ORDER BY upload_id ASC, id ASC", conn)
    if df.empty:
        return df
    df['DT_HR_INSPECAO'] = pd.to_datetime(df['DT_HR_INSPECAO'], errors='coerce')
    df['C_DPU_QG_AMARELO'] = pd.to_numeric(df['C_DPU_QG_AMARELO'], errors='coerce').fillna(0)
    df['NR_WO'] = df['NR_WO'].astype(str).str.strip()
    df['CD_POSTO_CN'] = df['CD_POSTO_CN'].astype(str).map(norm_posto)
    df = df[df['DT_HR_INSPECAO'].notna()].copy()
    df = df[df['CD_POSTO_CN'].isin(POSTOS_VALIDOS)].copy()
    return df.drop_duplicates(subset=['NR_WO', 'DT_HR_INSPECAO', 'CD_POSTO_CN'], keep='last').reset_index(drop=True)


def uploads_table(conn):
    return pd.read_sql_query('SELECT id, file_name, uploaded_at, total_rows, mode, status, message FROM upload_log ORDER BY id DESC', conn)


def delete_upload(conn, upload_id):
    conn.execute('DELETE FROM raw_inspections WHERE upload_id=?', (int(upload_id),))
    conn.execute('DELETE FROM upload_log WHERE id=?', (int(upload_id),))
    conn.commit()


def empty_metrics():
    return {'rft_pct': None, 'total': 0, 'good': 0, 'bad': 0, 'defects': 0, 'dpu': None, 'ppm_defects': None, 'ppm_bad_units': None, 'detail_by_wo': pd.DataFrame(columns=['NR_WO','SOMA_DEFEITOS','RFT'])}


def calcular_indicadores_qualidade(df, start_date, end_date):
    if df is None or df.empty:
        return empty_metrics()
    sdt = datetime.combine(start_date, time(0, 0, 0))
    edt = datetime.combine(end_date, time(23, 59, 59))
    filt = df[(df['DT_HR_INSPECAO'] >= sdt) & (df['DT_HR_INSPECAO'] <= edt)].copy()
    if filt.empty:
        return empty_metrics()
    grp = filt.groupby('NR_WO', as_index=False)['C_DPU_QG_AMARELO'].sum().rename(columns={'C_DPU_QG_AMARELO': 'SOMA_DEFEITOS'})
    grp['RFT'] = (grp['SOMA_DEFEITOS'] == 0).astype(int)
    total = int(len(grp))
    good = int(grp['RFT'].sum())
    bad = int(total - good)
    defects = float(grp['SOMA_DEFEITOS'].sum())
    return {'rft_pct': round((good / total) * 100, 2) if total else None, 'total': total, 'good': good, 'bad': bad, 'defects': defects, 'dpu': round(defects / total, 4) if total else None, 'ppm_defects': round((defects / total) * 1000000, 0) if total else None, 'ppm_bad_units': round((bad / total) * 1000000, 0) if total else None, 'detail_by_wo': grp}


def week_options(df, year):
    ydf = df[df['DT_HR_INSPECAO'].dt.year == year].copy()
    if ydf.empty:
        return []
    dates = sorted(ydf['DT_HR_INSPECAO'].dt.date.unique().tolist())
    mondays = sorted({d - timedelta(days=d.weekday()) for d in dates})
    return [(f"Semana {idx:02d} - {m.strftime('%d/%m/%Y')} a {(m + timedelta(days=6)).strftime('%d/%m/%Y')}", m, m + timedelta(days=6)) for idx, m in enumerate(mondays, start=1)]


def month_options(df, year):
    ydf = df[df['DT_HR_INSPECAO'].dt.year == year].copy()
    if ydf.empty:
        return []
    opts = []
    for month in sorted(ydf['DT_HR_INSPECAO'].dt.month.unique().tolist()):
        start = date(year, int(month), 1)
        end = date(year, int(month), monthrange(year, int(month))[1])
        opts.append((f"{start.strftime('%m/%Y')} - {start.strftime('%d/%m/%Y')} a {end.strftime('%d/%m/%Y')}", start, end))
    return opts


def trend_monthly(df, year, meta_rft, meta_ppm):
    rows = []
    for label, start, end in month_options(df, year):
        m = calcular_indicadores_qualidade(df, start, end)
        rows.append({'Mês': label.split(' - ')[0], 'RFT': m['rft_pct'] or 0, 'Meta RFT': meta_rft, 'DPU': m['dpu'] or 0, 'PPM Defeitos': m['ppm_defects'] or 0, 'Meta PPM': meta_ppm, 'PPM Não RFT': m['ppm_bad_units'] or 0, 'Total': m['total'], 'Defeitos': m['defects']})
    return pd.DataFrame(rows)


def br_int(v):
    if v is None or pd.isna(v):
        return 'Sem dados'
    return f'{float(v):,.0f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def br_float(v, digits=2):
    if v is None or pd.isna(v):
        return 'Sem dados'
    return f'{float(v):,.{digits}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def br_pct(v):
    return 'Sem dados' if v is None or pd.isna(v) else br_float(v, 2) + '%'


def status_rft(value, meta):
    return 'neutral' if value is None or pd.isna(value) else ('ok' if value >= meta else 'bad')


def status_ppm(value, meta):
    return 'neutral' if value is None or pd.isna(value) else ('ok' if value <= meta else 'bad')


def card(label, value, sub='', status='neutral'):
    st.markdown(f'<div class="metric-card {status}"><div class="label">{label}</div><div class="value">{value}</div><div class="sub">{sub}</div></div>', unsafe_allow_html=True)


def main():
    conn = get_conn()
    init_db(conn)
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown('<div class="hero"><h1>DPU & PPM a partir da base RFT</h1><p>Uploads cumulativos: carregue 2025, depois 2026, e selecione o ano no painel lateral. QG09 é padrão; QG07 é opcional; demais postos são ignorados.</p></div>', unsafe_allow_html=True)

    with st.sidebar:
        st.header('Base e uploads')
        modo_importacao = st.radio('Modo de importação', ['Somar ao histórico', 'Substituir período sobreposto', 'Reprocessar ano inteiro'], index=0)
        uploaded = st.file_uploader('Base RFT/operacional (.xlsx, .xls ou .csv)', type=['xlsx', 'xls', 'csv'])
        prepared = None
        if uploaded is not None:
            try:
                raw = read_file(uploaded)
                ok, missing = validate_df(raw)
                if not ok:
                    st.error('Base inválida. Colunas faltantes: ' + ', '.join(missing))
                else:
                    prepared = prepare(raw)
                    st.success(f'Arquivo lido: {len(prepared)} linhas válidas de QG09/QG07.')
                    resumo = prepared.groupby([prepared['DT_HR_INSPECAO'].dt.year, 'CD_POSTO_CN']).size().reset_index(name='Linhas')
                    resumo = resumo.rename(columns={'DT_HR_INSPECAO': 'Ano', 'CD_POSTO_CN': 'Posto'})
                    st.dataframe(resumo, use_container_width=True, hide_index=True)
            except Exception as err:
                st.error(f'Erro ao ler arquivo: {err}')
        if prepared is not None and not prepared.empty:
            if st.button('Salvar no histórico', type='primary', use_container_width=True):
                if modo_importacao == 'Substituir período sobreposto':
                    delete_overlapped_period(conn, prepared)
                elif modo_importacao == 'Reprocessar ano inteiro':
                    delete_year_for_upload_df(conn, prepared)
                uid = create_upload(conn, uploaded.name, len(prepared), modo_importacao, 'Base salva no histórico local.')
                save_raw(conn, uid, prepared)
                st.success(f'Upload {uid} salvo. A base agora fica acumulada no histórico.')
                st.rerun()

        st.divider()
        st.header('Filtros')
        df_all = load_app_db(conn)
        posto = ano = start_date = end_date = None
        if df_all.empty:
            st.info('Sem dados salvos ainda. Salve o primeiro arquivo no histórico.')
        else:
            incluir_qg07 = st.checkbox('Habilitar QG07 como opção', value=False)
            postos_presentes = set(df_all['CD_POSTO_CN'].dropna().unique().tolist())
            if incluir_qg07 and 'QG07' in postos_presentes:
                opcoes = [p for p in ['QG09', 'QG07'] if p in postos_presentes]
                posto = st.selectbox('Posto', opcoes, index=0)
            else:
                posto = POSTO_PRINCIPAL
                st.info('Posto principal selecionado: QG09')
            df = df_all[df_all['CD_POSTO_CN'] == posto].copy()
            if not df.empty:
                anos = sorted(df['DT_HR_INSPECAO'].dt.year.dropna().astype(int).unique().tolist())
                ano = st.selectbox('Ano', anos, index=len(anos) - 1)
                df = df[df['DT_HR_INSPECAO'].dt.year == ano].copy()
                modo = st.radio('Modo', ['Diário', 'Semanal', 'Mensal', 'Anual', 'Personalizado'], index=2)
                min_d = df['DT_HR_INSPECAO'].dt.date.min()
                max_d = df['DT_HR_INSPECAO'].dt.date.max()
                if modo == 'Diário':
                    selected = st.date_input('Dia', value=max_d, min_value=min_d, max_value=max_d, format='DD/MM/YYYY')
                    start_date = end_date = selected
                elif modo == 'Semanal':
                    opts = week_options(df, ano)
                    labels = [x[0] for x in opts]
                    label = st.selectbox('Semana', labels, index=len(labels) - 1)
                    found = next(x for x in opts if x[0] == label)
                    start_date, end_date = found[1], found[2]
                elif modo == 'Mensal':
                    opts = month_options(df, ano)
                    labels = [x[0] for x in opts]
                    label = st.selectbox('Mês', labels, index=len(labels) - 1)
                    found = next(x for x in opts if x[0] == label)
                    start_date, end_date = found[1], found[2]
                elif modo == 'Anual':
                    start_date, end_date = date(ano, 1, 1), max_d
                else:
                    periodo = st.date_input('Período personalizado', value=(min_d, max_d), min_value=min_d, max_value=max_d, format='DD/MM/YYYY')
                    start_date, end_date = periodo if isinstance(periodo, tuple) and len(periodo) == 2 else (max_d, max_d)
            else:
                st.warning(f'Não há dados disponíveis para {posto}.')
        st.divider()
        st.header('Metas')
        meta_rft = st.number_input('Meta RFT (%)', min_value=0.0, max_value=100.0, value=DEFAULT_META_RFT, step=0.1)
        meta_ppm = st.number_input('Meta PPM por defeito', min_value=0, value=DEFAULT_META_PPM, step=1000)

    tabs = st.tabs(['Dashboard', 'Tendência', 'Base calculada', 'Histórico', 'Critério de cálculo'])

    if df_all.empty or posto is None or ano is None or start_date is None or end_date is None:
        with tabs[0]:
            st.info('Salve uma base no histórico para iniciar os cálculos.')
        return

    metrics = calcular_indicadores_qualidade(df, start_date, end_date)

    with tabs[0]:
        st.subheader('Resultado do recorte selecionado')
        st.caption(f"Posto: {posto} | Ano: {ano} | Período: {start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}")
        c1, c2, c3, c4 = st.columns(4)
        with c1: card('RFT', br_pct(metrics['rft_pct']), f'Meta: {br_pct(meta_rft)}', status_rft(metrics['rft_pct'], meta_rft))
        with c2: card('DPU', br_float(metrics['dpu'], 4), 'Defeitos ÷ total inspecionado', 'neutral')
        with c3: card('PPM por defeito', br_int(metrics['ppm_defects']), f'Meta: {br_int(meta_ppm)}', status_ppm(metrics['ppm_defects'], meta_ppm))
        with c4: card('PPM por peça não RFT', br_int(metrics['ppm_bad_units']), 'Não RFT ÷ total × 1.000.000', 'warn')
        c5, c6, c7, c8 = st.columns(4)
        with c5: card('Total inspecionado', br_int(metrics['total']), 'Quantidade de NR_WO únicos', 'neutral')
        with c6: card('Peças RFT', br_int(metrics['good']), 'WOs com zero defeito', 'ok')
        with c7: card('Peças não RFT', br_int(metrics['bad']), 'WOs com defeito maior que zero', 'bad' if metrics['bad'] else 'ok')
        with c8: card('Total de defeitos', br_int(metrics['defects']), 'Soma de C_DPU_QG_AMARELO', 'warn' if metrics['defects'] else 'ok')

    with tabs[1]:
        st.subheader('Tendência mensal')
        trend = trend_monthly(df, ano, meta_rft, meta_ppm)
        if trend.empty:
            st.info('Sem dados para tendência.')
        else:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown('#### RFT x Meta')
                st.bar_chart(trend.set_index('Mês')[['RFT','Meta RFT']], use_container_width=True)
            with c2:
                st.markdown('#### PPM por defeito x Meta')
                st.bar_chart(trend.set_index('Mês')[['PPM Defeitos','Meta PPM']], use_container_width=True)
            show = trend.copy()
            show['RFT'] = show['RFT'].map(br_pct)
            show['Meta RFT'] = show['Meta RFT'].map(br_pct)
            show['DPU'] = show['DPU'].map(lambda x: br_float(x, 4))
            show['PPM Defeitos'] = show['PPM Defeitos'].map(br_int)
            show['Meta PPM'] = show['Meta PPM'].map(br_int)
            show['PPM Não RFT'] = show['PPM Não RFT'].map(br_int)
            show['Total'] = show['Total'].map(br_int)
            show['Defeitos'] = show['Defeitos'].map(br_int)
            st.dataframe(show, use_container_width=True, hide_index=True)

    with tabs[2]:
        st.subheader('Base calculada por WO')
        detail = metrics['detail_by_wo'].copy()
        if detail.empty:
            st.info('Sem dados no recorte.')
        else:
            detail['Status'] = detail['RFT'].map({1: 'RFT', 0: 'Não RFT'})
            detail = detail.rename(columns={'SOMA_DEFEITOS': 'Defeitos na WO'})
            st.dataframe(detail[['NR_WO', 'Defeitos na WO', 'Status']], use_container_width=True, hide_index=True)
            csv = detail[['NR_WO', 'Defeitos na WO', 'Status']].to_csv(index=False, sep=';').encode('utf-8-sig')
            st.download_button('Baixar base calculada em CSV', data=csv, file_name='base_calculada_dpu_ppm.csv', mime='text/csv', use_container_width=True)

    with tabs[3]:
        st.subheader('Histórico de uploads')
        hist = uploads_table(conn)
        if hist.empty:
            st.info('Os uploads salvos aparecerão aqui.')
        else:
            st.dataframe(hist, use_container_width=True, hide_index=True)
            selected_id = st.selectbox('Selecionar upload para excluir', hist['id'].tolist(), format_func=lambda x: f'Upload {x}')
            if st.button('Excluir upload selecionado', use_container_width=True):
                delete_upload(conn, selected_id)
                st.success('Upload excluído com sucesso.')
                st.rerun()

    with tabs[4]:
        st.subheader('Critério de cálculo travado')
        st.markdown('<div class="formula"><b>Histórico:</b> por padrão, cada arquivo é somado ao histórico. Assim é possível manter 2025 e 2026 na mesma base.</div><div class="formula"><b>Postos:</b> QG09 é principal; QG07 é opcional; qualquer outro posto é ignorado.</div><div class="formula"><b>Total inspecionado</b> = quantidade de NR_WO únicos no período.</div><div class="formula"><b>Total de defeitos</b> = soma de C_DPU_QG_AMARELO agrupada por NR_WO.</div><div class="formula"><b>RFT %</b> = peças RFT ÷ total inspecionado × 100.</div><div class="formula"><b>DPU</b> = total de defeitos ÷ total inspecionado.</div><div class="formula"><b>PPM por defeito</b> = DPU × 1.000.000.</div><div class="formula"><b>PPM por peça não RFT</b> = peças não RFT ÷ total inspecionado × 1.000.000.</div>', unsafe_allow_html=True)

if __name__ == '__main__':
    main()
