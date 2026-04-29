import pandas as pd
import numpy as np
from datetime import datetime, time
import os

# ==========================================
# 0. CONFIGURACIÓN DE RUTAS RELATIVAS
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) #Linea que configura las rutas relativas al codigo
RUTA_BRUTOS = os.path.join(BASE_DIR, "datos", "01_brutos") #Los datos donde beber son de la carpeta 01_brutos
RUTA_PROCESADOS = os.path.join(BASE_DIR, "datos", "03_procesados") #Los datos de destino van en 03_procesados

# ==========================================
# 1. CARGA DE DATOS
# ==========================================

def cargar_datos():
    print("--- Cargando archivos desde datos/01_brutos ---")
    archivo_cursos = os.path.join(RUTA_BRUTOS, "maestro_cursos 202625_30ENERO.xlsx")
    archivo_salones = os.path.join(RUTA_BRUTOS, "maestro_salones 202625.csv")

    if not os.path.exists(archivo_cursos): raise FileNotFoundError(f"Falta: {archivo_cursos}") #Manejo de errores
    if not os.path.exists(archivo_salones): raise FileNotFoundError(f"Falta: {archivo_salones}")

    df_cursos = pd.read_excel(archivo_cursos)
    try:
        df_salones = pd.read_csv(archivo_salones, sep=None, engine='python', encoding='utf-8-sig')
    except:
        df_salones = pd.read_csv(archivo_salones, sep=None, engine='python', encoding='latin-1')  #manejo de posibles tokenizacion de csv

    # Limpieza
    df_cursos.columns = df_cursos.columns.astype(str).str.upper().str.strip()  
    df_salones.columns = df_salones.columns.astype(str).str.upper().str.strip()
    df_salones.columns = df_salones.columns.str.replace('ï»¿', '').str.replace('\ufeff', '')

    return df_cursos, df_salones   #Archivos listos para procesar

# ==========================================
# 2. NORMALIZACIÓN
# ==========================================

CATALOGO_BLOQUES = {
    1: {'ini': 830, 'fin': 945,  'txt': '08:30 - 09:45'},
    2: {'ini': 950, 'fin': 1105, 'txt': '09:50 - 11:05'},
    3: {'ini': 1110,'fin': 1225, 'txt': '11:10 - 12:25'},
    4: {'ini': 1230, 'fin': 1345, 'txt': '12:30 - 13:45'},
    5: {'ini': 1350, 'fin': 1505, 'txt': '13:50 - 15:05'},
    6: {'ini': 1510, 'fin': 1625, 'txt': '15:10 - 16:25'},
    7: {'ini': 1630, 'fin': 1745, 'txt': '16:30 - 17:45'},
    8: {'ini': 1750, 'fin': 1905, 'txt': '17:50 - 19:05'},
    9: {'ini': 1910, 'fin': 2025, 'txt': '19:10 - 20:25'},
    10: {'ini': 2030, 'fin': 2145, 'txt': '20:30 - 21:45'},
    11: {'ini': 2150, 'fin': 2210, 'txt': '21:50 - 22:10'},
}

def normalizar_datos(df_cursos, df_salones):
    print("--- Normalizando a Bloques ---")

    def limpiar_hora(valor):
        if pd.isna(valor): return 0
        try: return int(float(valor))
        except: return 0

    df_cursos['HHMM_INICIO'] = df_cursos['HORA_INICIO'].apply(limpiar_hora)
    df_cursos['HHMM_FIN'] = df_cursos['HORA_FIN'].apply(limpiar_hora)

    def extraer_bloques(row):
        ini = row['HHMM_INICIO']
        mapa_inicio = {
            830: [1], 950: [2], 1110: [3], 1230: [4], 1350: [5],
            1510: [6], 1630: [7], 1750: [8], 1910: [9], 2030: [10],
            2020: [10], 2130: [11]
        }
        return mapa_inicio.get(ini, [])  # Aquí lo que hacemos es extraer como flecha la columna hora_inicio, relacionamos el catálogo de mapa_inicio con la hora de ini

    df_cursos['BLOQUES_REQ'] = df_cursos.apply(extraer_bloques, axis=1)
    
    if 'TIPO' in df_salones.columns:
        df_salones['TIPO'] = pd.to_numeric(df_salones['TIPO'], errors='coerce').fillna(3).astype(int)
    else:
        print("No se ha encoontrado al columna Tipo en el archivo de salones")

    def calcular_prioridad(row):
        score = 0
        estado = str(row.get('ESTADO_CURSO', '')).upper()
        materia = str(row.get('MATERIA', '')).upper()
        
        es_regimen = 'CÍCLICO' in estado and 'CONTRACÍCLICO' not in estado
        es_ccl = 'CCL' in materia
        
        if es_regimen:
            score += 1000
            score += 200 if es_ccl else 100
        else:
            score += 3000
            score += 200 if es_ccl else 100
            
        return score

    df_cursos['PRIORIDAD_CALC'] = df_cursos.apply(calcular_prioridad, axis=1)

    mapa_ind_sat = {}
    if 'CUPOS' in df_cursos.columns and 'TIPO_SALON_CODE' in df_cursos.columns:
        tipos_sala = df_cursos['TIPO_SALON_CODE'].unique()
        for t in tipos_sala:
            salas_t = df_salones[df_salones['TIPO'] == t]
            nrcs_t = df_cursos[df_cursos['TIPO_SALON_CODE'] == t]

            for cupo in nrcs_t['CUPOS'].unique():
                demanda = len(nrcs_t[nrcs_t['CUPOS'] == cupo])
                oferta = len(salas_t[salas_t['CAPACIDAD'] >= cupo])

                mapa_ind_sat[(t, cupo)] = demanda / oferta if oferta > 0 else 999.0
        df_cursos['IND_SATURACION'] = df_cursos.apply(
            lambda r: mapa_ind_sat.get((r['TIPO_SALON_CODE'], r['CUPOS']), 0), axis=1
        )
    else:
        df_cursos['IND_SATURACION'] = 0
    
    return df_cursos, df_salones

# ==========================================
# 3. MOTOR DE ASIGNACIÓN
# ==========================================

class GestorDeSalas:
    def __init__(self, df_salones, dias_posibles):
        self.salones = df_salones.sort_values(by='CAPACIDAD', ascending=True)
        self.disp = {}
        for dia in dias_posibles:
            self.disp[dia] = {str(s): set(CATALOGO_BLOQUES.keys()) for s in self.salones['NUMERO'].unique()}

    def buscar_sala_para_grupo(self, bloques_req_set, dia, cupos_req, tipo_req):
        if dia not in self.disp or not bloques_req_set: return None, "Día o Bloque inválido"
        
        candidatas = self.salones[
            (self.salones['TIPO'] == tipo_req) &
            (self.salones['CAPACIDAD'] >= cupos_req)
        ]

        if candidatas.empty: return None, "Sin capacidad/tipo"

        for idx, sala in candidatas.iterrows():
            id_sala = str(sala['NUMERO'])
            if id_sala in self.disp[dia] and bloques_req_set.issubset(self.disp[dia][id_sala]):
                self.disp[dia][id_sala] -= bloques_req_set 
                return id_sala, "OK"
        return None, "Tope horario"

    def generar_reporte_restantes(self):
        reporte = []
        for dia, salas in self.disp.items():
            for id_sala, bloques_libres in salas.items():
                if bloques_libres:
                    info = self.salones[self.salones['NUMERO'].astype(str) == id_sala].iloc[0]
                    for b in sorted(list(bloques_libres)):
                        reporte.append({
                            'Dia': dia, 'Num_Bloque': b,
                            'Horario': CATALOGO_BLOQUES[b]['txt'], 'Sala': id_sala,
                            'Edificio': info.get('EDIFICIO'), 'Capacidad': info.get('CAPACIDAD'),
                            'Estado': 'LIBRE'
                        })
        return pd.DataFrame(reporte)

# ==========================================
# 4. EJECUCIÓN 
# ==========================================

def main():
    try:
        df_c, df_s = cargar_datos()
        df_c, df_s = normalizar_datos(df_c, df_s)
        
        df_c = df_c.sort_values(by=['PRIORIDAD_CALC', 'IND_SATURACION', 'CUPOS'], ascending=[True, False, False])
        grupos = df_c.groupby(['NRC', 'DIAS'], sort=False)
        
        dias_unicos = df_c['DIAS'].unique()
        gestor = GestorDeSalas(df_s, dias_unicos)
        
        asignados = []
        pendientes = []

        for (nrc, dia), grupo_df in grupos:
            cupos_max = grupo_df['CUPOS'].max()
            tipo_req = grupo_df['TIPO_SALON_CODE'].iloc[0]
            prioridad = grupo_df['PRIORIDAD_CALC'].iloc[0]
            
            set_bloques_grupo = set()
            for b_list in grupo_df['BLOQUES_REQ']:
                set_bloques_grupo.update(b_list)
            
            sala_asignada, status = gestor.buscar_sala_para_grupo(set_bloques_grupo, dia, cupos_max, tipo_req)
            
            for idx, row in grupo_df.iterrows():
                fila = {
                    'NRC': row['NRC'], 'Materia': row['MATERIA'], 'Curso': row['CURSO'],
                    'Regimen': row['ESTADO_CURSO'], 'Dia': row['DIAS'],
                    'Bloques_Usados': str(row['BLOQUES_REQ']), 'hora_inicio': row['HORA_INICIO'],
                    'hora_fin': row['HORA_FIN'], 'Cupos': row['CUPOS'],
                    'Tipo_Req': row['TIPO_SALON_CODE']
                }
                
                if sala_asignada:
                    ds = df_s[df_s['NUMERO'].astype(str) == sala_asignada].iloc[0]
                    fila.update({
                        'Sala_Asignada': sala_asignada, 'Edificio': ds['EDIFICIO'],
                        'Capacidad': ds['CAPACIDAD'], '%_Ocupacion': round((row['CUPOS']/ds['CAPACIDAD'])*100, 1)
                    })
                    asignados.append(fila)
                else:
                    fila.update({'Error': status, 'Prioridad': prioridad})
                    pendientes.append(fila)

        # ==========================================
        # 5. GENERAR UN ÚNICO ARCHIVO CONSOLIDADO
        # ==========================================
        df_asig = pd.DataFrame(asignados)
        df_pend = pd.DataFrame(pendientes)
        df_disp = gestor.generar_reporte_restantes()
        
        marca_tiempo = datetime.now().strftime('%H%M%S')
        ruta_consolidado = os.path.join(RUTA_PROCESADOS, f"Resultado_Asignacion_Completo_{marca_tiempo}.xlsx")
        
        print(f"\n✅ Filas Asignadas: {len(df_asig)} | ❌ Fallidas: {len(df_pend)}")
        
        with pd.ExcelWriter(ruta_consolidado) as writer:
            if not df_asig.empty: df_asig.to_excel(writer, sheet_name='Asignados', index=False)
            if not df_pend.empty: df_pend.to_excel(writer, sheet_name='No_Asignados', index=False)
            if not df_disp.empty: df_disp.to_excel(writer, sheet_name='Bloques_Libres', index=False)
            
        print(f"Archivo guardado exitosamente en: {ruta_consolidado}")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()