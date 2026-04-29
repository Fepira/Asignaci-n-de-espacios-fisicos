import pandas as pd
import numpy as np
from datetime import datetime
import os

# ==========================================
# (MISMAS RUTAS Y FUNCIONES DE CARGA Y NORMALIZACIÓN QUE LA OPCIÓN 1)
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTA_BRUTOS = os.path.join(BASE_DIR, "datos", "01_brutos")
RUTA_PROCESADOS = os.path.join(BASE_DIR, "datos", "03_procesados")

def cargar_datos():
    archivo_cursos = os.path.join(RUTA_BRUTOS, "maestro_cursos 202625_30ENERO.xlsx")
    archivo_salones = os.path.join(RUTA_BRUTOS, "maestro_salones 202625.csv")
    df_cursos = pd.read_excel(archivo_cursos)
    try: df_salones = pd.read_csv(archivo_salones, sep=None, engine='python', encoding='utf-8-sig')
    except: df_salones = pd.read_csv(archivo_salones, sep=None, engine='python', encoding='latin-1')
    df_cursos.columns = df_cursos.columns.astype(str).str.upper().str.strip()
    df_salones.columns = df_salones.columns.astype(str).str.upper().str.strip()
    df_cursos = df_cursos.dropna(subset=['DIAS'])
    return df_cursos, df_salones

CATALOGO_BLOQUES = {1:{'txt':'08:30 - 09:45'}, 2:{'txt':'09:50 - 11:05'}, 3:{'txt':'11:10 - 12:25'}, 4:{'txt':'12:30 - 13:45'}, 5:{'txt':'13:50 - 15:05'}, 6:{'txt':'15:10 - 16:25'}, 7:{'txt':'16:30 - 17:45'}, 8:{'txt':'17:50 - 19:05'}, 9:{'txt':'19:10 - 20:25'}, 10:{'txt':'20:30 - 21:45'}, 11:{'txt':'21:50 - 22:10'}}

def normalizar_datos(df_cursos, df_salones):
    def limpiar_hora(v):
        try: return int(float(v))
        except: return 0
    df_cursos['HHMM_INICIO'] = df_cursos['HORA_INICIO'].apply(limpiar_hora)
    mapa = {830:[1], 950:[2], 1110:[3], 1230:[4], 1350:[5], 1510:[6], 1630:[7], 1750:[8], 1910:[9], 2030:[10], 2020:[10], 2130:[11]}
    df_cursos['BLOQUES_REQ'] = df_cursos['HHMM_INICIO'].map(lambda x: mapa.get(x, []))
    def detectar_tipo(txt): return 4 if 'LAB' in str(txt).upper() or 'COMPU' in str(txt).upper() else 3
    col_tipo = 'TIPO' if 'TIPO' in df_salones.columns else df_salones.columns[4]
    df_salones['TIPO_CODE'] = df_salones[col_tipo].apply(detectar_tipo)
    def calcular_prio(row):
        est, mat, alum = str(row.get('ESTADO_CURSO','')).upper(), str(row.get('MATERIA','')).upper(), str(row.get('TIPO_ALUMNO','')).upper()
        reg, ccl, nue = 'CÍCLICO' in est and 'CONTRA' not in est, 'CCL' in mat, 'NUEVO' in alum
        s = 1000 if reg else 3000
        s += 200 if ccl else 100
        if reg: s += (200 if nue else 100) + (50 if not ccl and nue else 0)
        return s
    df_cursos['PRIORIDAD_CALC'] = df_cursos.apply(calcular_prio, axis=1)
    return df_cursos, df_salones

# ==========================================
# 3. MOTOR DA MULTI-PASS
# ==========================================
class GestorDeSalasDA:
    def __init__(self, df_salones, dias_posibles):
        self.df_salones = df_salones
        self.asignaciones = {dia: {str(s): {} for s in df_salones['NUMERO'].unique()} for dia in dias_posibles}
        self.cuotas_edificio = {str(edif): {} for edif in df_salones['EDIFICIO'].unique()}

    def calcular_utilidad(self, prioridad, cupos, capacidad, edificio, escuela, aplicar_equidad):
        u_base = 5000 - prioridad
        ocupacion = (cupos / capacidad) * 100
        penalidad = 0
        if aplicar_equidad and escuela:
            penalidad = self.cuotas_edificio.get(edificio, {}).get(escuela, 0) * 20
        return u_base + ocupacion - penalidad

    def generar_preferencias(self, cupos, tipo, jornada):
        cands = self.df_salones[(self.df_salones['TIPO_CODE'] == tipo) & (self.df_salones['CAPACIDAD'] >= cupos)].copy()
        if jornada == 'V':
            cands = cands[cands['EDIFICIO'].str.contains('CASA CENTRAL', case=False, na=False) & ~cands['EDIFICIO'].str.contains('POSGRADO', case=False, na=False)]
        cands = cands.sort_values(by='CAPACIDAD', ascending=True)
        return cands['NUMERO'].astype(str).tolist()

    def ejecutar_da(self, grupos_meta, aplicar_equidad=True):
        pendientes = [cid for cid, m in grupos_meta.items() if m['sala_asignada'] is None]
        for pid in pendientes: grupos_meta[pid]['idx'] = 0

        while pendientes:
            cid = pendientes.pop(0)
            meta, nrc, dia = grupos_meta[cid], cid[0], cid[1]
            asignado = False

            while meta['idx'] < len(meta['prefs']):
                id_sala = meta['prefs'][meta['idx']]
                meta['idx'] += 1
                req_bloques = meta['bloques']
                sala_info = self.df_salones[self.df_salones['NUMERO'].astype(str) == id_sala].iloc[0]
                
                utilidad = self.calcular_utilidad(meta['prioridad'], meta['cupos'], sala_info['CAPACIDAD'], str(sala_info['EDIFICIO']), meta['escuela'], aplicar_equidad)

                puede_desplazar, expulsados = True, []
                for b in req_bloques:
                    if b in self.asignaciones[dia][id_sala]:
                        ocupante = self.asignaciones[dia][id_sala][b]
                        if utilidad <= ocupante['utilidad']: puede_desplazar = False; break
                        else: expulsados.append(ocupante['nrc'])

                if puede_desplazar:
                    for perdedor_nrc in set(expulsados):
                        pid = (perdedor_nrc, dia)
                        m_perdedor = grupos_meta[pid]
                        for bp in m_perdedor['bloques']:
                            if bp in self.asignaciones[dia][id_sala] and self.asignaciones[dia][id_sala][bp]['nrc'] == perdedor_nrc:
                                del self.asignaciones[dia][id_sala][bp]
                        m_perdedor['sala_asignada'] = None
                        if pid not in pendientes: pendientes.append(pid)
                        if self.cuotas_edificio[str(sala_info['EDIFICIO'])].get(m_perdedor['escuela'], 0) > 0:
                            self.cuotas_edificio[str(sala_info['EDIFICIO'])][m_perdedor['escuela']] -= 1

                    for b in req_bloques: self.asignaciones[dia][id_sala][b] = {'nrc': nrc, 'utilidad': utilidad}
                    meta['sala_asignada'] = id_sala
                    if meta['escuela']: self.cuotas_edificio[str(sala_info['EDIFICIO'])][meta['escuela']] = self.cuotas_edificio[str(sala_info['EDIFICIO'])].get(meta['escuela'], 0) + 1
                    asignado = True
                    break
            if not asignado: meta['sala_asignada'] = None

    def reporte_libres(self):
        rep = []
        for dia, salas in self.asignaciones.items():
            for s, ocup in salas.items():
                libres = set(CATALOGO_BLOQUES.keys()) - set(ocup.keys())
                if libres:
                    info = self.df_salones[self.df_salones['NUMERO'].astype(str) == s].iloc[0]
                    for b in sorted(list(libres)):
                        rep.append({'Edificio': info.get('EDIFICIO'), 'Sala': s, 'Tipo_sala': info.get('TIPO_CODE'), 'Capacidad': info.get('CAPACIDAD'), 'Dia': dia, 'Num_Bloque': b, 'Horario': CATALOGO_BLOQUES[b]['txt'], 'Estado': 'LIBRE'})
        return pd.DataFrame(rep)

# ==========================================
# 4. EJECUCIÓN
# ==========================================
def main():
    try:
        df_c, df_s = cargar_datos()
        df_c, df_s = normalizar_datos(df_c, df_s)
        
        grupos_meta = {}
        gestor = GestorDeSalasDA(df_s, df_c['DIAS'].unique())
        
        for (nrc, dia), g_df in df_c.groupby(['NRC', 'DIAS'], sort=False):
            bloques = set()
            for b in g_df['BLOQUES_REQ']: bloques.update(b)
            if not bloques: continue
            
            c, t, p = g_df['CUPOS'].max(), g_df['TIPO_SALON_CODE'].iloc[0], g_df['PRIORIDAD_CALC'].iloc[0]
            esc = str(g_df.get('ESCUELA_DESC', pd.Series([''])).iloc[0]).upper().strip()
            jor = str(g_df.get('JORNADA', pd.Series([''])).iloc[0]).upper().strip()
            
            grupos_meta[(nrc, dia)] = {
                'df': g_df, 'cupos': c, 'tipo': t, 'prioridad': p, 'bloques': bloques,
                'escuela': esc, 'jornada': jor, 'sala_asignada': None,
                'prefs': gestor.generar_preferencias(c, t, jor), 'idx': 0
            }

        print("\n--- PASADA 1: DA Con Equidad ---")
        gestor.ejecutar_da(grupos_meta, aplicar_equidad=True)
        p1 = sum(1 for m in grupos_meta.values() if m['sala_asignada'] is None)
        print(f"Sin asignar: {p1}")

        if p1 > 0:
            print("\n--- PASADA 2: DA Sin Equidad ---")
            gestor.ejecutar_da(grupos_meta, aplicar_equidad=False)

        asignados_list, fallidos_list = [], []
        for (nrc, dia), meta in grupos_meta.items():
            llave = meta['sala_asignada']
            for _, row in meta['df'].iterrows():
                datos = row.to_dict()
                if llave:
                    ds = df_s[df_s['NUMERO'].astype(str) == llave].iloc[0]
                    datos.update({'ASIGNADO_EDIFICIO': ds['EDIFICIO'], 'ASIGNADO_SALA': llave, 'ASIGNADO_TIPO': ds['TIPO_CODE'], 'ASIGNADO_CAPACIDAD': ds['CAPACIDAD'], 'ESTADO_PROCESO': 'EXITO'})
                    asignados_list.append(datos)
                else:
                    datos.update({'ASIGNADO_EDIFICIO': None, 'ASIGNADO_SALA': None, 'ASIGNADO_TIPO': None, 'ASIGNADO_CAPACIDAD': None, 'ESTADO_PROCESO': 'Agotó Opciones'})
                    fallidos_list.append(datos)

        df_out_asignados = pd.DataFrame(asignados_list)
        df_out_fallidos = pd.DataFrame(fallidos_list)
        df_out_restantes = gestor.reporte_libres()

        print(f"\n✅ Filas Asignadas: {len(df_out_asignados)} | ❌ Fallidas: {len(df_out_fallidos)}")
        
        ruta_final = os.path.join(RUTA_PROCESADOS, f"Resultado_DA_{datetime.now().strftime('%H%M%S')}.xlsx")
        with pd.ExcelWriter(ruta_final) as w:
            if not df_out_asignados.empty: df_out_asignados.to_excel(w, sheet_name='Asignados', index=False)
            if not df_out_fallidos.empty: df_out_fallidos.to_excel(w, sheet_name='No_Asignados', index=False)
            if not df_out_restantes.empty: df_out_restantes.to_excel(w, sheet_name='Bloques_Libres', index=False)
            
        print(f"Archivo guardado en: {ruta_final}")

    except Exception as e: print(f"ERROR: {e}")

if __name__ == "__main__":
    main()