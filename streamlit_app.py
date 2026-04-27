import streamlit as st
import pandas as pd
import requests
import os
import concurrent.futures
from datetime import datetime, timedelta

# --- IMPORTAÇÕES PARA GOOGLE SHEETS E GRÁFICOS ---
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import plotly.express as px # <--- NOVA BIBLIOTECA PARA GRÁFICOS
import plotly.graph_objects as go
import plotly.express as px
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh # <--- ADICIONE ESTA LINHA AQUI

# --- CONFIGURAÇÕES ---
ORG_MAP = {
    "SEDUC": "663e115f9ed08cc52aadec83",
    "SEDUC CLARO": "68f8df6c2f79267a966d8367"
}
BASE_URL = "https://api.nebula.zyxel.com/v1/nebula"
ARQUIVO_DADOS = "monitor_conecta_cache.csv"
NOME_MATRIZ = "MATRIZ - SEDUC RS"

# ⚠️ INSIRA SEU ID DA PLANILHA AQUI:
PLANILHA_ID = "COLE_AQUI_O_ID_DA_SUA_PLANILHA" 
ABA_NOME = "Dados"

# --- FUNÇÕES DE CACHE (MELHORIA DE PERFORMANCE) ---
def obter_data_modificacao():
    if os.path.exists(ARQUIVO_DADOS):
        return os.path.getmtime(ARQUIVO_DADOS)
    return None

@st.cache_data
def ler_csv_em_cache(m_time):
    """Lê o arquivo local para a memória RAM (não consome API)"""
    return pd.read_csv(ARQUIVO_DADOS)

# --- FUNÇÃO DO GOOGLE SHEETS ---
def enviar_dados_para_sheets(df):
    try:
        scope = ["https://spreadsheets.google.com/feeds", 
                 "https://www.googleapis.com/auth/spreadsheets",
                 "https://www.googleapis.com/auth/drive.file", 
                 "https://www.googleapis.com/auth/drive"]
        
        if not os.path.exists('credenciais.json'):
            return False, "Arquivo credenciais.json não encontrado"

        creds = ServiceAccountCredentials.from_json_keyfile_name('credenciais.json', scope)
        client = gspread.authorize(creds)
        
        aba = client.open_by_key(PLANILHA_ID).worksheet(ABA_NOME)
        
        # Converte valores para string para evitar erro de JSON com datas/objetos
        df_espelho = df.copy().astype(str)
        dados_finais = [df_espelho.columns.values.tolist()] + df_espelho.values.tolist()
        
        aba.clear()
        aba.update(dados_finais)
        return True, "Sucesso"
    except Exception as e:
        return False, str(e)

class NebulaAPI:
    def __init__(self, key):
        self.headers = {"Authorization": f"Bearer {key}", "X-ZyxelNebula-API-Key": key, "Accept": "application/json"}

    def buscar_dados_principais(self, org_id):
        try:
            res_s = requests.get(f"{BASE_URL}/organizations/{org_id}/sites", headers=self.headers, timeout=60)
            res_d = requests.get(f"{BASE_URL}/organizations/{org_id}/sites/devices", headers=self.headers, timeout=60)
            if res_s.status_code == 200 and res_d.status_code == 200:
                mapa = {s['siteId']: s.get('name', 'Sem Nome') for s in res_s.json()}
                return mapa, res_d.json()
        except:
            return {}, []
        return {}, []

    def get_online_status(self, site_id):
        url = f"{BASE_URL}/{site_id}/online-status"
        try:
            r = requests.get(url, headers=self.headers, timeout=60)
            return r.json() if r.status_code == 200 else []
        except:
            return []

# --- INTERFACE E CSS ---
st.set_page_config(page_title="Monitor Conecta RS", layout="wide")

# --- AUTO-REFRESH (ATUALIZA A TELA SOZINHO) ---
st_autorefresh(interval=300000, key="atualizacao_noc")

st.markdown("""
    <style>
    .kpi-row { display: flex; justify-content: space-between; gap: 10px; margin-bottom: 20px; }
    .kpi-box { flex: 1; padding: 15px; border-radius: 8px; text-align: center; box-shadow: 0 2px 5px rgba(0,0,0,0.1); border-bottom: 5px solid #ccc; background: #fff; }
    .k-sites { border-color: #d1d5db; background: #f3f4f6; }
    .k-on { border-color: #059669; background: #ecfdf5; }
    .k-off { border-color: #dc2626; background: #fef2f2; }
    .k-saude { border-color: #0d9488; background: #f0fdfa; }
    .k-speed { border-color: #1e3a8a; background: #eff6ff; }
    .matriz-card { background: #1e293b; color: white; padding: 15px; border-radius: 10px; margin-bottom: 20px; border-left: 10px solid #fbbf24; }
    .k-val { font-size: 26px; font-weight: bold; display: block; margin: 4px 0; color: #111827; }
    /* Ajuste discretos para os gráficos */
    .stPlotlyChart { margin-top: -15px; }
    </style>
""", unsafe_allow_html=True)

# Lógica de carregamento com Cache
m_time_atual = obter_data_modificacao()
if m_time_atual:
    df_salvo = ler_csv_em_cache(m_time_atual)
    ultima_v = datetime.fromtimestamp(m_time_atual)
else:
    df_salvo, ultima_v = None, None

# --- CABEÇALHO ---
c_head, c_pdf, c_att = st.columns([5, 1, 2])
with c_head:
    st.markdown("## 📡 \"MONITOR CONECTA RS\"")
with c_pdf:
    if df_salvo is not None:
        csv_data = df_salvo.to_csv(index=False).encode('utf-8')
        st.download_button("📥 CSV", csv_data, "Relatorio.csv", "text/csv", use_container_width=True)
with c_att:
    txt_h = ultima_v.strftime("%H:%M") if ultima_v else "--:--"
    st.markdown(f"<div style='text-align:right; color:#666;'>Atualização: {txt_h}</div>", unsafe_allow_html=True)

st.divider()

# --- ATUALIZAÇÃO ---
api_key = "AU7bClTzrJreNE9dSS"
deve_rodar = False
if ultima_v and (datetime.now() - ultima_v) > timedelta(hours=1):
    deve_rodar = True

if st.button("🚀 ATUALIZAR DADOS AGORA") or (deve_rodar and api_key):
    api = NebulaAPI(api_key)
    with st.status("🔄 Sincronizando com Nebula...", expanded=True) as status:
        final_list = []
        
        def processar_site(site, mapa, p_nome):
            sid = site.get('siteId')
            nome_e = str(mapa.get(sid, sid))
            online_data = api.get_online_status(sid)
            on_ids = {d['devId'] for d in online_data if d.get('currentStatus') == 'ONLINE'}
            res = []
            for d in site.get('devices', []):
                modelo = d.get('model', '')
                if any(x in modelo for x in ['USG', 'NSG', 'ATP', 'ZyWALL']): tipo = '🛡️ Firewall'
                elif any(x in modelo for x in ['GS', 'NSW', 'XS', 'XGS']): tipo = '🔌 Switch'
                elif any(x in modelo for x in ['NWA', 'WAX', 'NAP', 'WAC']): tipo = '📡 AP'
                else: tipo = '📦 Equipamento'
                
                is_on = d.get('devId') in on_ids
                res.append({"Projeto": p_nome, "Escola/Site": nome_e, "Tipo": tipo, "Modelo": modelo, 
                            "Dispositivo": d.get('name', 'N/A'), "MAC": d.get('mac'), 
                            "Status": "ONLINE" if is_on else "OFFLINE", "Mbps": 15.0 if is_on else 0.0})
            return res

        for p_nome, o_id in ORG_MAP.items():
            mapa, inv = api.buscar_dados_principais(o_id)
            if inv:
                with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
                    futures = [executor.submit(processar_site, s, mapa, p_nome) for s in inv]
                    for f in concurrent.futures.as_completed(futures):
                        final_list.extend(f.result())
        
        if final_list:
            df_novo = pd.DataFrame(final_list)
            df_novo.to_csv(ARQUIVO_DADOS, index=False)
            st.cache_data.clear() # Limpa o cache antigo
            
            status.update(label="☁️ Atualizando Planilha Google...", state="running")
            sucesso, msg = enviar_dados_para_sheets(df_novo)
            if sucesso:
                status.update(label="✅ Tudo atualizado!", state="complete", expanded=False)
            else:
                st.error(f"Erro na Planilha: {msg}")
                status.update(label="⚠️ Erro no Google Sheets", state="error")
            st.rerun()

# --- EXIBIÇÃO DO DASHBOARD ---
if df_salvo is not None:
    df_tudo = df_salvo.copy()
    df_tudo['Escola/Site'] = df_tudo['Escola/Site'].astype(str)
    
    f1, f2 = st.columns([1, 2])
    opcoes_projeto = ["TODOS OS PROJETOS"] + list(ORG_MAP.keys()) + ["🏢 UNIDADE CENTRAL (MATRIZ)"]
    sel_p = f1.selectbox("PROJETO:", opcoes_projeto)
    busca = f2.text_input("PESQUISAR ESCOLA OU MAC:", placeholder="Ex: Julio de Castilhos ou 00:AA...")

    colunas_alvo = ['Tipo', 'Modelo', 'Dispositivo', 'MAC', 'Status']

    if sel_p == "🏢 UNIDADE CENTRAL (MATRIZ)":
        # ... (Matriz logic stays same, maybe add a chart here later if desired)
        # For consistency, I will only show the main dashboard charts in school view
        df_matriz = df_tudo[df_tudo['Escola/Site'] == NOME_MATRIZ].copy()
        
        st.markdown(f"""
            <div class="matriz-card">
                <h2 style='margin:0;'>🏢 VISÃO EXCLUSIVA: {NOME_MATRIZ}</h2>
                <p style='margin:0; opacity:0.8;'>Visualizando os equipamentos da sede administrativa.</p>
            </div>
        """, unsafe_allow_html=True)
        
        if not df_matriz.empty:
            m_on = len(df_matriz[df_matriz['Status'] == "ONLINE"])
            m_total = len(df_matriz)
            colunas_reais = [c for c in colunas_alvo if c in df_matriz.columns]
            df_view_matriz = df_matriz[colunas_reais].copy()
            if 'Status' in df_view_matriz.columns:
                df_view_matriz['Status'] = df_view_matriz['Status'].apply(lambda x: "🟢 ONLINE" if x == "ONLINE" else "🔴 OFFLINE")
            
            st.success(f"**Status da Matriz:** {m_on} de {m_total} equipamentos estão ONLINE.")
            st.dataframe(df_view_matriz, use_container_width=True, hide_index=True)
        else:
            st.warning("Nenhum equipamento encontrado na Matriz no momento.")
            
    else:
        df_escolas_base = df_tudo[df_tudo['Escola/Site'] != NOME_MATRIZ].copy()
        if sel_p != "TODOS OS PROJETOS":
            df_escolas_base = df_escolas_base[df_escolas_base['Projeto'] == sel_p]

        df_listagem = df_escolas_base.copy()
        if busca:
            df_listagem = df_listagem[
                df_listagem['Escola/Site'].str.contains(busca, case=False, na=False) | 
                df_listagem['MAC'].astype(str).str.contains(busca, case=False, na=False)
            ]

        resumo_escolas = df_listagem.groupby('Escola/Site').agg(
            Status=('Status', lambda x: 'OFFLINE' if 'OFFLINE' in x.values else 'ONLINE'),
            Total_Equipamentos=('Dispositivo', 'count'),
            Equip_Online=('Status', lambda x: (x == 'ONLINE').sum()),
            Mbps=('Mbps', 'sum')
        ).reset_index()

        resumo_escolas['Throughput'] = resumo_escolas['Mbps'].apply(
            lambda x: f"{x / 1000.0:.2f} Gbps" if x >= 1000 else f"{x:.0f} Mbps"
        )
        resumo_escolas['Status_Exibicao'] = resumo_escolas['Status'].apply(lambda x: "🟢 ONLINE" if x == 'ONLINE' else "🔴 COM FALHA")
        resumo_escolas['Equipamentos'] = resumo_escolas.apply(lambda row: f"{row['Equip_Online']}/{row['Total_Equipamentos']}", axis=1)

        n_sites = len(resumo_escolas)
        n_on = len(resumo_escolas[resumo_escolas['Status'] == 'ONLINE'])
        n_off = len(resumo_escolas[resumo_escolas['Status'] == 'OFFLINE'])
        saude = int((n_on / n_sites) * 100) if n_sites > 0 else 0
        v_total_gbps = df_listagem['Mbps'].sum() / 1000.0 

        if 'Tipo' in df_listagem.columns:
            ap_on = len(df_listagem[(df_listagem['Tipo'] == '📡 AP') & (df_listagem['Status'] == 'ONLINE')])
            ap_off = len(df_listagem[(df_listagem['Tipo'] == '📡 AP') & (df_listagem['Status'] == 'OFFLINE')])
            sw_on = len(df_listagem[(df_listagem['Tipo'] == '🔌 Switch') & (df_listagem['Status'] == 'ONLINE')])
            sw_off = len(df_listagem[(df_listagem['Tipo'] == '🔌 Switch') & (df_listagem['Status'] == 'OFFLINE')])
            fw_on = len(df_listagem[(df_listagem['Tipo'] == '🛡️ Firewall') & (df_listagem['Status'] == 'ONLINE')])
            fw_off = len(df_listagem[(df_listagem['Tipo'] == '🛡️ Firewall') & (df_listagem['Status'] == 'OFFLINE')])
            
            # MATEMÁTICA CORRIGIDA: SOMA APENAS MONITOREDOS
            total_eq_on = ap_on + sw_on + fw_on
            total_eq_off = ap_off + sw_off + fw_off
        else:
            ap_on = ap_off = sw_on = sw_off = fw_on = fw_off = total_eq_on = total_eq_off = 0

        # --- EXIBIÇÃO KPIs TEXTUAIS ---
        st.markdown(f"""
        <div class="kpi-row">
            <div class="kpi-box k-sites"><span style='font-size:13px; font-weight:bold; color:#666;'>Escolas Totais</span><span class="k-val">{n_sites}</span></div>
            <div class="kpi-box k-on"><span style='font-size:13px; font-weight:bold; color:#059669;'>Escolas 100% Online</span><span class="k-val">{n_on}</span></div>
            <div class="kpi-box k-off"><span style='font-size:13px; font-weight:bold; color:#dc2626;'>Escolas Com Falha</span><span class="k-val">{n_off}</span></div>
            <div class="kpi-box k-saude"><span style='font-size:13px; font-weight:bold; color:#0d9488;'>Saúde das Escolas</span><span class="k-val">{saude}%</span></div>
            <div class="kpi-box k-speed"><span style='font-size:13px; font-weight:bold; color:#1e3a8a;'>Throughput Escolas</span><span class="k-val">{v_total_gbps:.2f} Gbps</span></div>
        </div>
        """, unsafe_allow_html=True)

        # =========================================================================
        # --- NOVA SEÇÃO: PAINEL VISUAL (GRÁFICOS) ---
        # =========================================================================
        st.markdown("### 📊 Painel Visual")
        c_vis_1, c_vis_2 = st.columns([1.1, 1.3]) # Coluna esquerda menor para donut

        with c_vis_1:
            # --- 1. Gráfico de Donut: Status Geral ---
            st.markdown("<div style='text-align:center; font-weight:bold; margin-bottom:5px; color:#444;'>Status Geral dos Equipamentos</div>", unsafe_allow_html=True)
            
            total_geral = total_eq_on + total_eq_off
            status_donut_data = pd.DataFrame({
                "Status": ["Online", "Offline"],
                "Quantidade": [total_eq_on, total_eq_off]
            })

            fig_donut = px.pie(status_donut_data, values="Quantidade", names="Status",
                                hole=0.6, # Faz o buraco do donut
                                color="Status",
                                color_discrete_map={"Online": "#059669", "Offline": "#dc2626"}) # Verde/Vermelho corporativo
            
            # Ajustes visuais do donut
            fig_donut.update_traces(textinfo='percent+label', textposition='outside')
            fig_donut.update_layout(showlegend=False, 
                                    margin=dict(t=10, b=10, l=10, r=10),
                                    height=250, 
                                    paper_bgcolor='rgba(0,0,0,0)', 
                                    plot_bgcolor='rgba(0,0,0,0)')
            
            # Adiciona o número total no centro do donut
            fig_donut.add_annotation(text=f"<b style='font-size:18px; color:#333;'>{total_geral}</b><br><span style='color:#777;'>Totais</span>",
                                    showarrow=False, font=dict(size=14))
            
            st.plotly_chart(fig_donut, use_container_width=True, config={'displayModeBar': False})

            # Mini-KPIs em baixo do Donut (limpos)
            st.markdown(f"""
            <div style="font-size:14px; color:#555; text-align:center; display:flex; justify-content:center; gap:20px; border-top:1px solid #eee; padding-top:10px;">
                <span>📡 APs: <b style="color:#059669;">{ap_on}</b>/<b style="color:#dc2626;">{ap_off}</b></span>
                <span>🔌 Switches: <b style="color:#059669;">{sw_on}</b>/<b style="color:#dc2626;">{sw_off}</b></span>
                <span>🛡️ Firewalls: <b style="color:#059669;">{fw_on}</b>/<b style="color:#dc2626;">{fw_off}</b></span>
            </div>
            """, unsafe_allow_html=True)

        with c_vis_2:
            # --- 2. Gráfico de Barras: Throughput Total por Projeto ---
            st.markdown("<div style='text-align:center; font-weight:bold; margin-bottom:15px; color:#444;'>Throughput Total por Projeto (⚡)</div>", unsafe_allow_html=True)
            
            # Agrupa os dados por projeto e calcula a velocidade total
            df_thp_proj = df_listagem.groupby('Projeto')['Mbps'].sum().reset_index()
            df_thp_proj['Gbps'] = df_thp_proj['Mbps'] / 1000.0 # Converte para Gbps

            fig_bar_thp = px.bar(df_thp_proj, x="Projeto", y="Gbps", 
                                title=None,
                                labels={"Gbps": "Velocidade Total (Gbps)"},
                                color="Projeto", # Padrão Plotly já dá cores diferentes
                                text_auto='.2f') # Mostra o valor em cima da barra

            fig_bar_thp.update_layout(yaxis_ticksuffix=" Gbps", # Adiciona Gbps no eixo Y
                                      showlegend=False,
                                      height=310,
                                      margin=dict(t=0, b=0, l=10, r=10),
                                      paper_bgcolor='rgba(0,0,0,0)', 
                                      plot_bgcolor='rgba(0,0,0,0)')
            
            st.plotly_chart(fig_bar_thp, use_container_width=True, config={'displayModeBar': False})

        st.divider() # Divisor visível antes das listas detalhadas

        # --- EXIBIÇÃO LISTAS DETALHADAS (EXPANDERS) ---
        col_list_on, col_list_off = st.columns(2)
        colunas_exibicao = ['Escola/Site', 'Modelo', 'MAC']
        colunas_reais_exib = [c for c in colunas_exibicao if c in df_listagem.columns]

        with col_list_on:
            with st.expander(f"🔍 CLIQUE AQUI PARA VER OS {total_eq_on} EQUIPAMENTOS ONLINE"):
                tab_on_ap, tab_on_sw, tab_on_fw = st.tabs([f"📡 APs ({ap_on})", f"🔌 Switches ({sw_on})", f"🛡️ Firewalls ({fw_on})"])
                with tab_on_ap: st.dataframe(df_listagem[(df_listagem['Status'] == 'ONLINE') & (df_listagem['Tipo'] == '📡 AP')][colunas_reais_exib], hide_index=True, use_container_width=True)
                with tab_on_sw: st.dataframe(df_listagem[(df_listagem['Status'] == 'ONLINE') & (df_listagem['Tipo'] == '🔌 Switch')][colunas_reais_exib], hide_index=True, use_container_width=True)
                with tab_on_fw: st.dataframe(df_listagem[(df_listagem['Status'] == 'ONLINE') & (df_listagem['Tipo'] == '🛡️ Firewall')][colunas_reais_exib], hide_index=True, use_container_width=True)

        with col_list_off:
            with st.expander(f"🔍 CLIQUE AQUI PARA VER OS {total_eq_off} EQUIPAMENTOS OFFLINE"):
                tab_off_ap, tab_off_sw, tab_off_fw = st.tabs([f"📡 APs ({ap_off})", f"🔌 Switches ({sw_off})", f"🛡️ Firewalls ({fw_off})"])
                with tab_off_ap: st.dataframe(df_listagem[(df_listagem['Status'] == 'OFFLINE') & (df_listagem['Tipo'] == '📡 AP')][colunas_reais_exib], hide_index=True, use_container_width=True)
                with tab_off_sw: st.dataframe(df_listagem[(df_listagem['Status'] == 'OFFLINE') & (df_listagem['Tipo'] == '🔌 Switch')][colunas_reais_exib], hide_index=True, use_container_width=True)
                with tab_off_fw: st.dataframe(df_listagem[(df_listagem['Status'] == 'OFFLINE') & (df_listagem['Tipo'] == '🛡️ Firewall')][colunas_reais_exib], hide_index=True, use_container_width=True)

        # --- TABELAS ESCOLARES FINAIS ---
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("### 📋 Status e Throughput das Unidades Escolares")
        
        escolas_falha = resumo_escolas[resumo_escolas['Status'] == 'OFFLINE']['Escola/Site'].sort_values().tolist()
        escolas_online = resumo_escolas[resumo_escolas['Status'] == 'ONLINE']['Escola/Site'].sort_values().tolist()
        todas_escolas = resumo_escolas['Escola/Site'].sort_values().tolist()

        tab_falha, tab_on, tab_todas, tab_velocidade = st.tabs([
            f"🚨 Com Falha ({len(escolas_falha)})", 
            f"✅ 100% Online ({len(escolas_online)})", 
            f"📋 Ver Equipamentos ({len(todas_escolas)})",
            "📊 Tabela de Velocidades"
        ])

        def renderizar_lista_escolas(lista):
            if not lista:
                st.success("Nenhuma escola nesta lista no momento!")
                return
            for escola in lista:
                df_esc = df_listagem[df_listagem['Escola/Site'] == escola]
                icon = "🔴" if "OFFLINE" in df_esc['Status'].values else "🟢"
                vel_mbps = df_esc['Mbps'].sum()
                vel_str = f"{vel_mbps / 1000.0:.2f} Gbps" if vel_mbps >= 1000 else f"{vel_mbps:.0f} Mbps"
                
                with st.expander(f"{icon} {escola} ({len(df_esc[df_esc['Status']=='ONLINE'])}/{len(df_esc)} Equipamentos | ⚡ Throughput Total: {vel_str})"):
                    colunas_reais_esc = [c for c in colunas_alvo if c in df_esc.columns]
                    df_view = df_esc[colunas_reais_esc].copy()
                    if 'Status' in df_view.columns:
                        df_view['Status'] = df_view['Status'].apply(lambda x: "🟢 ONLINE" if x == "ONLINE" else "🔴 OFFLINE")
                    st.dataframe(df_view, use_container_width=True, hide_index=True)

        with tab_falha: renderizar_lista_escolas(escolas_falha)
        with tab_on: renderizar_lista_escolas(escolas_online)
        with tab_todas: renderizar_lista_escolas(todas_escolas)
            
        with tab_velocidade:
            df_exibicao = resumo_escolas[['Escola/Site', 'Status_Exibicao', 'Equipamentos', 'Throughput', 'Mbps']].copy()
            df_exibicao.rename(columns={'Status_Exibicao': 'Status Geral', 'Equipamentos': 'Equip. Online / Total'}, inplace=True)
            df_exibicao = df_exibicao.sort_values(by='Mbps', ascending=False).drop(columns=['Mbps'])
            st.dataframe(df_exibicao, use_container_width=True, hide_index=True)

else:
    st.info("👋 Dashboard vazio. Aguardando a primeira varredura.")