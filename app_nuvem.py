import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- CONFIGURAÇÕES ---
ORG_MAP = {
    "SEDUC": "663e115f9ed08cc52aadec83",
    "SEDUC CLARO": "68f8df6c2f79267a966d8367"
}
ARQUIVO_DADOS = "monitor_conecta_cache.csv"
NOME_MATRIZ = "MATRIZ - SEDUC RS"

# --- INTERFACE E CSS ---
st.set_page_config(page_title="Monitor Conecta RS - Nuvem", layout="wide")

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
    </style>
""", unsafe_allow_html=True)

def carregar_dados():
    if os.path.exists(ARQUIVO_DADOS):
        df = pd.read_csv(ARQUIVO_DADOS)
        m_time = datetime.fromtimestamp(os.path.getmtime(ARQUIVO_DADOS))
        return df, m_time
    return None, None

# --- CABEÇALHO ---
c_head, c_pdf, c_att = st.columns([5, 1, 2])
df_salvo, ultima_v = carregar_dados()

with c_head:
    st.markdown("## 📡 \"MONITOR CONECTA RS\"")
    st.caption("Visão em Cache - Atualizado via Sincronização Local")
    
with c_pdf:
    if df_salvo is not None:
        csv = df_salvo.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Baixar Dados (CSV)",
            data=csv,
            file_name=f"Relatorio_Conecta_RS.csv",
            mime="text/csv",
            use_container_width=True
        )

with c_att:
    txt_h = ultima_v.strftime("%H:%M") if ultima_v else "--:--"
    st.markdown(f"<div style='text-align:right; color:#666;'>Atualização dos dados em:<br><b>{txt_h}</b></div>", unsafe_allow_html=True)

st.divider()

# --- DASHBOARD ---
if df_salvo is not None:
    df_tudo = df_salvo.copy()
    
    df_tudo['Escola/Site'] = df_tudo['Escola/Site'].astype(str)
    
    f1, f2 = st.columns([1, 2])
    
    opcoes_projeto = ["TODOS OS PROJETOS"] + list(ORG_MAP.keys()) + ["🏢 UNIDADE CENTRAL (MATRIZ)"]
    sel_p = f1.selectbox("PROJETO:", opcoes_projeto)
    
    busca = f2.text_input("PESQUISAR ESCOLA OU MAC:", placeholder="Ex: Julio de Castilhos ou 00:AA...")

    colunas_alvo = ['Tipo', 'Modelo', 'Dispositivo', 'MAC', 'Status']

    # --- LÓGICA DA MATRIZ ---
    if sel_p == "🏢 UNIDADE CENTRAL (MATRIZ)":
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
            if not df_view_matriz.empty and 'Status' in df_view_matriz.columns:
                df_view_matriz['Status'] = df_view_matriz['Status'].apply(lambda x: "🟢 ONLINE" if x == "ONLINE" else "🔴 OFFLINE")
            
            st.success(f"**Status da Matriz:** {m_on} de {m_total} equipamentos estão ONLINE.")
            st.dataframe(df_view_matriz, use_container_width=True, hide_index=True)
        else:
            st.warning("Nenhum equipamento encontrado na Matriz no arquivo de cache.")
            
    # --- LÓGICA DAS ESCOLAS ---
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

        # Agrupamento inteligente para gerar a Tabela de Velocidades
        resumo_escolas = df_listagem.groupby('Escola/Site').agg(
            Status=('Status', lambda x: 'OFFLINE' if 'OFFLINE' in x.values else 'ONLINE'),
            Total_Equipamentos=('Dispositivo', 'count'),
            Equip_Online=('Status', lambda x: (x == 'ONLINE').sum()),
            Mbps=('Mbps', 'sum')
        ).reset_index()

        # Formatando as colunas do resumo
        resumo_escolas['Throughput'] = resumo_escolas['Mbps'].apply(
            lambda x: f"{x / 1000.0:.2f} Gbps" if x >= 1000 else f"{x:.0f} Mbps"
        )
        resumo_escolas['Status_Exibicao'] = resumo_escolas['Status'].apply(
            lambda x: "🟢 ONLINE" if x == 'ONLINE' else "🔴 COM FALHA"
        )
        resumo_escolas['Equipamentos'] = resumo_escolas.apply(
            lambda row: f"{row['Equip_Online']}/{row['Total_Equipamentos']}", axis=1
        )

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
            total_eq_on = len(df_listagem[df_listagem['Status'] == 'ONLINE'])
            total_eq_off = len(df_listagem[df_listagem['Status'] == 'OFFLINE'])
        else:
            ap_on = ap_off = sw_on = sw_off = fw_on = fw_off = total_eq_on = total_eq_off = 0

        st.markdown(f"""
        <div class="kpi-row">
            <div class="kpi-box k-sites"><span style='font-size:13px; font-weight:bold; color:#666;'>Escolas Totais</span><span class="k-val">{n_sites}</span></div>
            <div class="kpi-box k-on"><span style='font-size:13px; font-weight:bold; color:#059669;'>Escolas 100% Online</span><span class="k-val">{n_on}</span></div>
            <div class="kpi-box k-off"><span style='font-size:13px; font-weight:bold; color:#dc2626;'>Escolas Com Falha</span><span class="k-val">{n_off}</span></div>
            <div class="kpi-box k-saude"><span style='font-size:13px; font-weight:bold; color:#0d9488;'>Saúde das Escolas</span><span class="k-val">{saude}%</span></div>
            <div class="kpi-box k-speed"><span style='font-size:13px; font-weight:bold; color:#1e3a8a;'>Throughput Escolas</span><span class="k-val">{v_total_gbps:.2f} Gbps</span></div>
        </div>
        
        <div class="kpi-row">
            <div class="kpi-box k-on" style="flex: 1; padding: 20px;">
                <span style='font-size:15px; font-weight:bold; color:#059669; text-transform:uppercase;'>🟢 Equipamentos ONLINE ({total_eq_on} Totais)</span>
                <div style="font-size:16px; margin-top:12px; color:#1f2937; display:flex; justify-content:center; gap:25px;">
                    <span>📡 APs: <b style="font-size:18px;">{ap_on}</b></span>
                    <span>🔌 Switches: <b style="font-size:18px;">{sw_on}</b></span>
                    <span>🛡️ Firewalls: <b style="font-size:18px;">{fw_on}</b></span>
                </div>
            </div>
            <div class="kpi-box k-off" style="flex: 1; padding: 20px;">
                <span style='font-size:15px; font-weight:bold; color:#dc2626; text-transform:uppercase;'>🔴 Equipamentos OFFLINE ({total_eq_off} Totais)</span>
                <div style="font-size:16px; margin-top:12px; color:#1f2937; display:flex; justify-content:center; gap:25px;">
                    <span>📡 APs: <b style="font-size:18px;">{ap_off}</b></span>
                    <span>🔌 Switches: <b style="font-size:18px;">{sw_off}</b></span>
                    <span>🛡️ Firewalls: <b style="font-size:18px;">{fw_off}</b></span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        col_list_on, col_list_off = st.columns(2)
        
        colunas_exibicao = ['Escola/Site', 'Modelo', 'MAC']
        colunas_reais_exib = [c for c in colunas_exibicao if c in df_listagem.columns]

        with col_list_on:
            with st.expander(f"🔍 CLIQUE AQUI PARA VER OS {total_eq_on} EQUIPAMENTOS ONLINE"):
                tab_on_ap, tab_on_sw, tab_on_fw = st.tabs([f"📡 APs ({ap_on})", f"🔌 Switches ({sw_on})", f"🛡️ Firewalls ({fw_on})"])
                with tab_on_ap:
                    st.dataframe(df_listagem[(df_listagem['Status'] == 'ONLINE') & (df_listagem['Tipo'] == '📡 AP')][colunas_reais_exib], hide_index=True, use_container_width=True)
                with tab_on_sw:
                    st.dataframe(df_listagem[(df_listagem['Status'] == 'ONLINE') & (df_listagem['Tipo'] == '🔌 Switch')][colunas_reais_exib], hide_index=True, use_container_width=True)
                with tab_on_fw:
                    st.dataframe(df_listagem[(df_listagem['Status'] == 'ONLINE') & (df_listagem['Tipo'] == '🛡️ Firewall')][colunas_reais_exib], hide_index=True, use_container_width=True)

        with col_list_off:
            with st.expander(f"🔍 CLIQUE AQUI PARA VER OS {total_eq_off} EQUIPAMENTOS OFFLINE"):
                tab_off_ap, tab_off_sw, tab_off_fw = st.tabs([f"📡 APs ({ap_off})", f"🔌 Switches ({sw_off})", f"🛡️ Firewalls ({fw_off})"])
                with tab_off_ap:
                    st.dataframe(df_listagem[(df_listagem['Status'] == 'OFFLINE') & (df_listagem['Tipo'] == '📡 AP')][colunas_reais_exib], hide_index=True, use_container_width=True)
                with tab_off_sw:
                    st.dataframe(df_listagem[(df_listagem['Status'] == 'OFFLINE') & (df_listagem['Tipo'] == '🔌 Switch')][colunas_reais_exib], hide_index=True, use_container_width=True)
                with tab_off_fw:
                    st.dataframe(df_listagem[(df_listagem['Status'] == 'OFFLINE') & (df_listagem['Tipo'] == '🛡️ Firewall')][colunas_reais_exib], hide_index=True, use_container_width=True)

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
                has_off = "OFFLINE" in df_esc['Status'].values
                icon = "🔴" if has_off else "🟢"
                
                # Cálculo do throughput total da escola para o título
                vel_mbps = df_esc['Mbps'].sum()
                if vel_mbps >= 1000:
                    vel_str = f"{vel_mbps / 1000.0:.2f} Gbps"
                else:
                    vel_str = f"{vel_mbps:.0f} Mbps"
                
                titulo_expander = f"{icon} {escola} ({len(df_esc[df_esc['Status']=='ONLINE'])}/{len(df_esc)} Equipamentos | ⚡ Throughput Total: {vel_str})"
                
                with st.expander(titulo_expander):
                    colunas_reais_esc = [c for c in colunas_alvo if c in df_esc.columns]
                    df_view = df_esc[colunas_reais_esc].copy()
                    if not df_view.empty and 'Status' in df_view.columns:
                        df_view['Status'] = df_view['Status'].apply(lambda x: "🟢 ONLINE" if x == "ONLINE" else "🔴 OFFLINE")
                    st.dataframe(df_view, use_container_width=True, hide_index=True)

        with tab_falha:
            renderizar_lista_escolas(escolas_falha)
        with tab_on:
            renderizar_lista_escolas(escolas_online)
        with tab_todas:
            renderizar_lista_escolas(todas_escolas)
            
        # RENDERIZAÇÃO DA TABELA DE VELOCIDADES
        with tab_velocidade:
            st.info("💡 **Dica:** Clique no cabeçalho das colunas para ordenar os dados (ex: ver quem tem maior Throughput).")
            df_exibicao_velocidade = resumo_escolas[['Escola/Site', 'Status_Exibicao', 'Equipamentos', 'Throughput', 'Mbps']].copy()
            df_exibicao_velocidade.rename(columns={
                'Status_Exibicao': 'Status Geral',
                'Equipamentos': 'Equip. Online / Total'
            }, inplace=True)
            
            df_exibicao_velocidade = df_exibicao_velocidade.sort_values(by='Mbps', ascending=False).drop(columns=['Mbps'])
            st.dataframe(df_exibicao_velocidade, use_container_width=True, hide_index=True)

else:
    st.error("⚠️ ERRO: O arquivo 'monitor_conecta_cache.csv' não foi encontrado. Certifique-se de fazer o upload dele junto com este código.")