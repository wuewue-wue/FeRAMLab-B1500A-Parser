import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import zipfile
import re
import io
import google.generativeai as genai

#此網頁是為了方便直觀顯示FeRAM的相關數據圖，意圖整合excel及Origin的功能
#V17(每跑不動or功能有問題就記錄一次)
#特別感謝王鑫-{輕鬆又漂亮的Python Web框架} & Gemini 3pro & Github大老，小弟受寵若驚
#電物116謝文豪敬上

#.[def]讀取檔案設定
# ------------------------------------------
#定義load_file函式以在後續調用
def load_file(file_obj,filename):

    #先讀前20行找excel中的表格標題
    #且為了同時支援csv跟excel才用try...except(後續也有類似操作)
    # ------------------------------------------
    try:
        file_obj.seek(0)
        preview=pd.read_csv(file_obj,header=None,nrows=20,encoding='utf-8')
    except:
        try:
            file_obj.seek(0)
            preview=pd.read_excel(file_obj, header=None, nrows=20)
        except:return None
    # ------------------------------------------

    #找出數據從第幾行開始
    # ------------------------------------------
    h_idx=0
    for i,row in preview.iterrows():
        s=str(row.values).lower()
        if 'voltage' in s or 'measresult' in s:
            h_idx=i
            break
    # ------------------------------------------

    #找到表格標題在第幾行後開始讀取標題下的數據
    # ------------------------------------------
    file_obj.seek(0)
    try:
        if filename.endswith('.xlsx'): 
            return pd.read_excel(file_obj,header=h_idx)
        else: 
            return pd.read_csv(file_obj,header=h_idx)

    except: return None
    # ------------------------------------------
# ------------------------------------------

#.[def]調用Gemini協助分析
# ------------------------------------------
#調用Gemini以便協助分析Cycle-2Pr-2Vc資料
#用API會算Token費用，需要使用請詳閱Google API說明
def gemini(api_key, df):
    if not api_key: 
        return "請輸入Gemini API Key"
    #辨識Gemini API key並處理在Python算好的Cycle-2Pr-2Vc資料
    # ------------------------------------------
    try:
        genai.configure(api_key=api_key)
        model=genai.GenerativeModel('gemini-1.5-flash')
        csv=df[['cycle_label','2Pr','2Vc']].to_markdown(index=False)
        prompt=f"分析 FeRAM 耐久度:\n{csv}\n1.喚醒 2.疲勞 3.機制 4.可靠度"
        with st.spinner("Gemini分析中..."): 
            return model.generate_content(prompt).text

    except Exception as e:
        return str(e)
    # ------------------------------------------
# ------------------------------------------


#A.網頁標題與Python數據圖設定
# ====================================================================================

#網頁標題
# ------------------------------------------
st.set_page_config(page_title="FeRAM Lab",layout="wide")
# ------------------------------------------

#圖表風格
#若沒有下載Matplotlib調用seaborn-v0_8-whitegrid就以ggplot顯示圖表
# ------------------------------------------
try:
    plt.style.use('seaborn-v0_8-whitegrid')
except:
    plt.style.use('ggplot')
# ------------------------------------------

#以防Python的負號變方框的亂碼情況
# ------------------------------------------
plt.rcParams['axes.unicode_minus']=False 
plt.rcParams.update({'font.size':11})
# ------------------------------------------

# ====================================================================================


#B.數據計算與處理
# ==========================================
class FerroelectricAnalyzer:
    def __init__(self,df,area_um2,filename="Unknown",force_pund=False):
        self.df=df
        self.filename=filename
        self.area_cm2=area_um2*1e-8 #將μm^2換算成cm^2以利後續計算
        self.error_msg=None
        self.mode="LOOP" 

        #之前為了檢測檔案是否包含PUND or P-U而寫的
        #後續寫完才想到如果用連續波型(如sin/cos波等)沒事
        #但若是方波或其他自定義奇形怪狀的波型就會掛掉
        #這是目前版本裡較危險的地方，雖然幾乎只會用PUND
        # ------------------------------------------
        if force_pund:
            self.mode = 'PUND'
        elif 'PUND' in str(filename).upper():
            self.mode = 'PUND'
        elif any('P-U' in str(c) for c in df.columns):
            self.mode = 'PUND'
        # ------------------------------------------

        #執行初始化動作
        # ------------------------------------------
        try:
            self._map_columns() 
            self._parse_cycle_count()#找Cycle數(1E0~1E9)
        except Exception as e:
            self.error_msg = f"Init Error: {e}"
        # ------------------------------------------

    #.[def]從.zip檔案的Excel中找出哪一欄是電壓/電流/時間
    def _map_columns(self):
        cols=self.df.columns
        #轉成小寫以方便比對
        # ------------------------------------------
        cols_lower=[str(c).lower() for c in cols]
        # ------------------------------------------
        
        #用預設關鍵字找欄位(全部用小寫)
        # ------------------------------------------
        v_keys=["measresult1", "voltage", "force", "v_avg", "voltage_1", "v1"]
        i_keys=["measresult2", "current", "i_avg", "current_1", "i1"]
        t_keys=["time", "t", "measresult1_time"]
        # ------------------------------------------

        #找索引(Index)
        v_idx=next((i for i,c in enumerate(cols_lower) if any(k in c for k in v_keys)), None)
        i_idx=next((i for i,c in enumerate(cols_lower) if any(k in c for k in i_keys)), None)
        t_idx=next((i for i,c in enumerate(cols_lower) if any(k in c for k in t_keys)), None)

        if v_idx is not None and i_idx is not None:
            self.V=pd.to_numeric(self.df.iloc[:, v_idx], errors='coerce').values
            self.I=pd.to_numeric(self.df.iloc[:, i_idx], errors='coerce').values
            
            if t_idx is not None:
                self.T=pd.to_numeric(self.df.iloc[:, t_idx], errors='coerce').values
            else:
                self.T=np.arange(len(self.V)) * self.fallback_dt_s
            
            # 移除空格
            mask=~np.isnan(self.V) & ~np.isnan(self.I) & ~np.isnan(self.T)
            self.V,self.I,self.T=self.V[mask],self.I[mask],self.T[mask]
        else:
            #如果真的找不到才調用Fallback用位置猜
            if self.df.shape[1]>=3:
                 self.T=pd.to_numeric(self.df.iloc[:,0],errors='coerce').values
                 self.V=pd.to_numeric(self.df.iloc[:,1],errors='coerce').values
                 self.I=pd.to_numeric(self.df.iloc[:,2],errors='coerce').values
            elif self.df.shape[1] == 2:
                 self.V=pd.to_numeric(self.df.iloc[:,0],errors='coerce').values
                 self.I=pd.to_numeric(self.df.iloc[:,1],errors='coerce').values
                 self.T=np.arange(len(self.V))*self.fallback_dt_s
            else:
                raise ValueError("無法識別欄位 (MeasResult1/2 Not Found)")
            
            mask=~np.isnan(self.V) & ~np.isnan(self.I) & ~np.isnan(self.T)
            self.V,self.I,self.T=self.V[mask],self.I[mask],self.T[mask]
    # ------------------------------------------

    #判斷循環次數
    # ------------------------------------------
    def _parse_cycle_count(self):
        #抓1E[N]並轉換成10^N(Cycle數)
        match=re.search(r'1E(\d+)',self.filename,re.IGNORECASE) #抓1E[N]的N
        if match:
            self.cycle_pow=int(match.group(1))
            self.cycle_num=10**self.cycle_pow #轉換成10^N(Cycle數)
            self.cycle_label=f"1E{self.cycle_pow}"
        else:
            self.cycle_num=1
            self.cycle_label="Fresh"
    # ------------------------------------------

    #[.def]一般模式，不利用漏電補償(Leakage Current Compensation)
    #若Loop沒有閉合可能為材料的氧化層漏電or others
    #若沒開啟此模式預設用學術界公認的DLCC(Dynamic Leakage Current Compensation)算法修正
    #開啟後不會有任何修正算法介入
    #呈現真實測得的情況
    # ------------------------------------------
    def _calculate_normal_raw(self):
        #若表格有時間軸，利用上下行相減就可知dt
        #真的沒有時間軸才會用前端輸入的dt
        # ------------------------------------------
        if len(self.T)>1 and (self.T[-1]-self.T[0])>1e-12:
            dt=np.diff(self.T,prepend=self.T[0])
            dt[0]=np.mean(dt[1:]) 
        else:
            dt=self.fallback_dt_s
        # -----------------------------------------

        #黎曼合[Sum(I*dt)]
        #這裡I*dt得到dQ，然後cumsum得到Q
        # -----------------------------------------
        dQ=self.I*dt
        Q_raw=np.cumsum(dQ)
        # -----------------------------------------

        #歸一化P=Q/Area(轉為μC/cm^2)
        P_raw=(Q_raw/self.area_cm2)*1e6

        #僅置中(Shift)
        # -----------------------------------------
        shift=(np.max(P_raw)+np.min(P_raw))/2
        P_final=P_raw-shift
        # -----------------------------------------

        #計算粗略Pr
        # -----------------------------------------
        Two_Pr=np.max(P_final)-np.min(P_final)
        Two_Vc=0.0 #Raw mode不算Vc
        # -----------------------------------------

        return{
            "cycle_num": self.cycle_num,
            "cycle_label": self.cycle_label,
            "filename": self.filename,
            "2Pr": Two_Pr,
            "2Vc": Two_Vc,
            "data_P": P_final, #這是螺旋線
            "data_V": self.V
        },None
    # ------------------------------------------

    #[.def]線性修正模式
    # -----------------------------------------
    def _calculate_corrected(self, invert_polarity, compensate_leakage, isolate, v_th):

        if self.mode=='PUND':
            #基礎閾值偵測
            is_active=np.abs(self.V)>v_th
            diff=np.diff(is_active.astype(int),prepend=0)
            starts=np.where(diff==1)[0]
            ends=np.where(diff==-1)[0]
            
            #脈衝合併解決"多圈/碎片"問題
            #如果一個波結束後沒過多久(如10個數據點)又開始，會視為同一個波(雜訊抖動)
            # ------------------------------------------------
            if len(starts)>0 and len(ends)>0:
                merged_starts,merged_ends=[starts[0]],[]
                for i in range(1,len(starts)):
                    gap_threshold=2 
                    if starts[i]-ends[i-1]<gap_threshold: 
                        pass # 真的靠太近才視為雜訊
                    else:
                        merged_ends.append(ends[i-1]); merged_starts.append(starts[i])
                merged_ends.append(ends[-1])
                starts=np.array(merged_starts)
                ends=np.array(merged_ends)
            # ------------------------------------------------

            #脈衝數量邏輯 (處理 "上下下上上")
            # ------------------------------------------------
            final_p_pair=None
            final_n_pair=None
            
            #建立脈衝物件列表
            pulses=[]
            if len(starts)==len(ends):
                for s,e in zip(starts, ends):
                    if e>s:
                        mid=(s+e)//2
                        pol=1 if self.V[mid] > 0 else -1
                        pulses.append({'s':s,'e':e,'pol':pol})
            
            #脈衝邏輯(Preset, N, D, P, U)或(Preset, P, U, N, D)
            #這樣B1500/Keithley可以(上下下上上...)or(下上上下下...)
            if len(pulses)==5:
                #丟掉第0個(Preset)只看後4項
                target_pulses=pulses[1:] 
            elif len(pulses) >= 4:
                #如果是4個或更多，使用全部進行配對
                target_pulses=pulses
            else:
                return None, f"PUND Error: 脈衝過少 ({len(pulses)})"
            # ------------------------------------------------

            #在target_pulses裡面找P-U和N-D
            for i in range(len(target_pulses)-1):
                #找P-U(++)
                # ------------------------------------------------
                if target_pulses[i]['pol']==1 and target_pulses[i+1]['pol']==1:
                    if final_p_pair is None: #只抓第一組
                        final_p_pair=(target_pulses[i],target_pulses[i+1])
                # ------------------------------------------------
                
                #找N-D(--)
                # ------------------------------------------------
                if target_pulses[i]['pol']==-1 and target_pulses[i+1]['pol']==-1:
                    if final_n_pair is None:
                        final_n_pair=(target_pulses[i],target_pulses[i+1])
                # ------------------------------------------------

            #執行PU,ND計算
            # ------------------------------------------------
            if final_p_pair and final_n_pair:

                #P-U
                # ------------------------------------------------
                P,U=(final_p_pair[0]['s'],final_p_pair[0]['e']),(final_p_pair[1]['s'],final_p_pair[1]['e'])#範圍
                len1=min(P[1]-P[0],U[1]-U[0])
                I_pos=self.I[P[0]:P[0]+len1]-self.I[U[0]:U[0]+len1]
                V_pos=self.V[P[0]:P[0]+len1]
                # ------------------------------------------------
                
                #N-D
                # ------------------------------------------------
                N,D=(final_n_pair[0]['s'],final_n_pair[0]['e']),(final_n_pair[1]['s'],final_n_pair[1]['e'])
                len2=min(N[1]-N[0],D[1]-D[0])
                I_neg=self.I[N[0]:N[0]+len2]-self.I[D[0]:D[0]+len2]
                V_neg=self.V[N[0]:N[0]+len2]
                # ------------------------------------------------
                
                #拼接
                # ------------------------------------------------
                proc_I = np.concatenate([I_pos, I_neg])
                proc_V = np.concatenate([V_pos, V_neg])
                # ------------------------------------------------
                
                #重建時間軸(使用平均dt)
                #測量數據點的dt也為固定值，可用平均算出無須前端輸入
                # ------------------------------------------------
                if len(self.T)>1:
                    avg_dt=(self.T[-1]-self.T[0])/len(self.T)
                else:
                    avg_dt=self.fallback_dt_s
                proc_T=np.arange(len(proc_I))*avg_dt
                # ------------------------------------------------
            
            #"PUND Error：無法找到完整的P-U(++)與N-D(--)配對"
            # ------------------------------------------------
            else:
                return None,"PUND Error：無法找到完整的P-U(++)與N-D(--)配對"
            # ------------------------------------------------

        else:
            if isolate:
                #使用Peak-to-Peak 強制單圈
                # ------------------------------------------------
                window=5
                v_smooth=np.convolve(self.V,np.ones(window)/window,mode='same') if len(self.V)>window else self.V
                v_max,v_min=np.max(v_smooth),np.min(v_smooth)
                th_h=v_max-(v_max-v_min)*0.2
                th_l=v_min+(v_max-v_min)*0.2
                highs=np.where(v_smooth>th_h)[0]
                lows=np.where(v_smooth<th_l)[0]
                # ------------------------------------------------
                
                if len(highs)>0 and len(lows)>0:
                    #嘗試找谷-峰-谷(最穩)
                    last_peak=highs[-1]
                    starts=lows[lows<last_peak]
                    ends=lows[lows>last_peak]
                    if len(starts)>0 and len(ends)>0:
                        s, e = starts[-1], ends[0]
                        proc_V,proc_I,proc_T=self.V[s:e+1],self.I[s:e+1],self.T[s:e+1]
                    else:
                        proc_V,proc_I,proc_T=self.V,self.I,self.T
                else:
                    proc_V,proc_I,proc_T=self.V,self.I,self.T
            else:
                proc_V,proc_I,proc_T =self.V,self.I,self.T

        #自定義測量電流方向
        #滯留曲線上下翻轉
        # ------------------------------------------------
        if invert_polarity: proc_I=-proc_I
        # ------------------------------------------------

        #黎曼合
        # ------------------------------------------------
        dt=np.mean(np.diff(proc_T)) if len(proc_T)>1 else 1e-7
        Q_raw=np.cumsum(proc_I)*dt
        # ------------------------------------------------

        #歸一化P=Q/Area(轉為μC/cm^2)
        # ------------------------------------------------
        P_raw=(Q_raw/self.area_cm2)*1e6
        # ------------------------------------------------

        #漏電補償
        # ------------------------------------------------
        if compensate_leakage and len(P_raw)>1:
            delta=P_raw[-1]-P_raw[0]
            correction=np.linspace(0,delta,len(P_raw))
            P_corr=P_raw-correction
        else: 
            P_corr=P_raw
        # ------------------------------------------------
            
        #置中
        # ------------------------------------------------
        P_final=P_corr-(np.max(P_corr)+np.min(P_corr))/2
        # ------------------------------------------------
        
        #截距法算2Pr
        # ------------------------------------------------
        try:
            idx_vmax=np.argmax(proc_V)
            idx_vmin=np.argmin(proc_V)
            i1,i2=min(idx_vmax,idx_vmin),max(idx_vmax,idx_vmin)
            b1_V,b1_P=proc_V[i1:i2],P_final[i1:i2]
            b2_V,b2_P=np.concatenate((proc_V[i2:],proc_V[:i1])),np.concatenate((P_final[i2:],P_final[:i1]))
            
            def get_p0(v,p):
                if len(v)==0:
                    return 0
                return p[np.argmin(np.abs(v))]
            pr1=get_p0(b1_V,b1_P)
            pr2=get_p0(b2_V,b2_P)
            Two_Pr=np.abs(pr1-pr2)
        except:
            Two_Pr=np.max(P_final)-np.min(P_final)
        # ------------------------------------------------

        #算2Vc
        # ------------------------------------------------
        zeros=np.where(np.diff(np.sign(P_final)))[0]
        Two_Vc=0.0
        if len(zeros)>=2:
            vs=proc_V[zeros]
            Two_Vc=np.max(vs)-np.min(vs)

        return{
            "cycle_num": self.cycle_num,
            "cycle_label": self.cycle_label,
            "filename": self.filename,
            "2Pr": Two_Pr,
            "2Vc": Two_Vc,
            "data_P": P_final,
            "data_V": proc_V
        },None
    
    #
    def calculate_metrics(self, raw_mode=False, **kwargs):
        if self.error_msg:
            return None, self.error_msg
        try:
            if raw_mode:
                return self._calculate_normal_raw()
            else:
                return self._calculate_corrected(**kwargs)
        except Exception as e:
            return None,str(e)
# ==========================================

#C.前端設計
# ==========================================
def main():
    st.title("FeRAM Lab")
    st.markdown("---")

    with st.sidebar:
        st.header("元件參數")
        # 預設為50x50(可改)
        L=st.number_input("長度(µm)",value=50.0,step=10.0)
        W=st.number_input("寬度(µm)",value=50.0,step=10.0)
        area=L*W
        
        st.divider()
        force_pund = True 
        
        st.subheader("優化參數")
        v_th = st.number_input("PUND閾值 (V)", value=0.01, step=0.01, format="%.2f", help="若沒圖，請調低此值")
        st.caption("進階修正")
        use_isolation=st.checkbox("週期鎖定 (Isolation)", value=True)
        invert_pol=st.checkbox("反轉極性 (Invert)", value=False)
        use_comp=st.checkbox("漏電補償 (Linear Comp.)", value=True)
        plot_type=st.radio("繪圖風格", ["Line", "Scatter", "Both"])
        cmap_option = st.selectbox("色彩配置", ["viridis (預設)","plasma (暖色)","rainbow (彩虹)","coolwarm (冷暖)"])

        st.divider()
        key = st.text_input("Gemini API Key", type="password")
    #檔案上傳區
    uploaded_file=st.file_uploader("📂上傳檔案 (支援 .zip, .xlsx, .csv)", type=["zip", "xlsx", "csv"])

    if uploaded_file:
        results=[]
        files_to_process=[]

        # 檔案解包邏輯
        if uploaded_file.name.endswith('.zip'):
            with zipfile.ZipFile(uploaded_file,'r') as z:
                #濾掉macOS的隱藏檔
                #macOS補丁
                files=[f for f in z.namelist() if f.endswith(('.xlsx','.csv')) and 'MACOSX' not in f]
                for f in files:
                    files_to_process.append((f, io.BytesIO(z.read(f))))
        else:
            files_to_process.append((uploaded_file.name, uploaded_file))

        #批次處理邏輯
        if files_to_process:
            bar = st.progress(0)
            status_text = st.empty()
            
            for i, (fname, fcontent) in enumerate(files_to_process):
                status_text.text(f"正在分析: {fname}...")
                try:
                    #Load & Init
                    df = load_file(fcontent, fname)
                    if df is not None:
                        ana = FerroelectricAnalyzer(df, area, fname, force_pund=force_pund)
                        
                        
                        #計算
                        res,err=ana.calculate_metrics(
                            invert_polarity=invert_pol,
                            compensate_leakage=use_comp,
                            isolate=use_isolation,
                            v_th=v_th
                        )
                        
                        if res: 
                            results.append(res)
                        elif err:
                            st.warning(f"檔案 {fname} 處理失敗:{err}")
                except Exception as e:
                    print(f"Error processing {fname}:{e}")
                
                bar.progress((i+1)/len(files_to_process))
            
            status_text.text("分析完成！")
            bar.empty()

        #計算結果顯示
        if results:
            #建立總表並排序
            df_res=pd.DataFrame(results).sort_values("cycle_num")
            
            #分頁顯示
            tab1,tab2,tab3=st.tabs(["P-E Loops", "Endurance", "AI Analysis"])
            
            with tab1:
                col1,col2=st.columns([1, 3])
                with col1:
                    st.markdown("#### 選擇週期")
                    labels=df_res['cycle_label'].unique()
                    sel=st.multiselect("顯示圖層", labels, default=[labels[-1]] if len(labels) > 0 else [])
                
                with col2:
                    if sel:
                        fig, ax = plt.subplots(figsize=(6,5))                        
                        
                        cmap_name=cmap_option.split()[0] #從選單字串取出顏色名稱
                        cmap=plt.get_cmap(cmap_name) #獲取對應的colormap物件
                        colors=cmap(np.linspace(0,1,len(sel))) #產生顏色陣列
                        
                        for i,lbl in enumerate(sel):
                            row=df_res[df_res['cycle_label']==lbl].iloc[0]
                            if "Line" in plot_type or "Both" in plot_type:
                                ax.plot(row['data_V'],row['data_P'],label=lbl,lw=2,color=colors[i],alpha=0.8)
                            if "Scatter" in plot_type or "Both" in plot_type:
                                ax.scatter(row['data_V'],row['data_P'],s=15,color=colors[i],alpha=0.6)
                        ax.set_xlabel("Voltage (V)")
                        ax.set_ylabel("Polarization ($\mu C/cm^2$)")
                        ax.axhline(0,c='gray',lw=0.5,ls='--')
                        ax.axvline(0,c='gray',lw=0.5,ls='--')
                        
                        ax.set_title("P-E Hysteresis Loops")
                        ax.legend()
                        ax.grid(True, alpha=0.3)
                        st.pyplot(fig)
                        
                        #下載按鈕
                        img = io.BytesIO()
                        fig.savefig(img, format='png', dpi=300, bbox_inches='tight')
                        st.download_button("Download chart", img, "pe_loops.png", "image/png")
                    else:
                        st.info("請從左側選擇要顯示的週期數據。")

            with tab2:
                if len(df_res)>0:
                    st.markdown("#### Endurance Trend")
                    fig2,ax=plt.subplots(figsize=(10,5))
                    
                    #繪製2Pr
                    ax.semilogx(df_res['cycle_num'], df_res['2Pr'],'o-',color='tab:blue',label='$2P_r$',lw=2,markersize=8)
                    ax.set_xlabel("Cycles (log scale)")
                    ax.set_ylabel("$2P_r$ ($\mu C/cm^2$)",color='tab:blue')
                    ax.tick_params(axis='y',labelcolor='tab:blue')
                    ax.grid(True,which="both",ls="-",alpha=0.2)
                    
                    #雙軸繪製2Vc 
                    ax2=ax.twinx()
                    ax2.semilogx(df_res['cycle_num'],df_res['2Vc'],'s--',color='tab:red',label='$2V_c$',lw=1.5,markersize=6,alpha=0.7)
                    ax2.set_ylabel("$2V_c$ (V)",color='tab:red')
                    ax2.tick_params(axis='y',labelcolor='tab:red')

                    #合併Legend
                    lines,labels=ax.get_legend_handles_labels()
                    lines2,labels2=ax2.get_legend_handles_labels()
                    ax.legend(lines+lines2,labels+labels2,loc='best')

                    st.pyplot(fig2)
                    col_d1,col_d2=st.columns(2)
                    with col_d1:
                        #下載數據
                        csv=df_res.to_csv(index=False).encode('utf-8')
                        st.download_button("Download Data table", csv, "feram_analysis.csv", "text/csv")
                    with col_d2:
                        img2=io.BytesIO()
                        fig2.savefig(img2,format='png',dpi=300,bbox_inches='tight')
                        st.download_button("Download Data chart",img2,"endurance_plot.png","image/png")
                else:
                    st.warning("數據點不足，無法繪製趨勢圖")

            with tab3:
                st.markdown("#### Gemini Assistant")
                if not key:
                    st.info("請先在左側欄位輸入Gemini API Key才能啟用此功能。")
                else:
                    if st.button("開始AI分析"):
                        # 呼叫 gemini 函式 (確保函式名稱與前面定義的一致)
                        analysis_text = gemini(key, df_res) 
                        st.markdown(analysis_text)

if __name__ == "__main__":
    main()
# ==========================================