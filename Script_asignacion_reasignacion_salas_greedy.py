import pandas as pd
import numpy as np
from datetime import datetime
import os

# ==========================================
# 0. CONFIGURACIÓN DE RUTAS RELATIVAS
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTA_BRUTOS = os.path.join(BASE_DIR, "datos", "01_brutos")
RUTA_PROCESADOS = os.path.join(BASE_DIR, "datos", "03_procesados")

# ==========================================
# 1. CARGA DE DATOS
# ==========================================

def cargar_datos():
    print("--- Cargando archivos de entrada ---")
    archivo_cursos = os.path.join(RUTA_BRUTOS, "maestro_cursos 202625_30ENERO.xlsx")
    archivo_salones = os.path.join(RUTA_BRUTOS, "maestro_salones 202625.csv")

    if not os.path.exists(archivo_cursos): raise FileNotFoundError(f"Falta: {archivo_cursos}")
    if not os.path.exists(archivo_salones): raise FileNotFoundError(f"Falta: {archivo_salones}")

    df_cursos = pd.read_excel(archivo_cursos)
    try:
        df_salones = pd.read_csv(archivo_salones, sep=None, engine='python', encoding='utf-8-sig')
    except:
        df_salones = pd.read_csv(archivo_salones, sep=None, engine='python', encoding='latin-1')

    # Estandarización de nombres de columnas
    df_cursos.columns = df_cursos.columns.astype(str).str.upper().str.strip()
    df_salones.columns = df_salones.columns.astype(str).str.upper().str.strip()
    df_salones.columns = df_salones.columns.str.replace('ï»¿', '').str.replace('\ufeff', '')

    df_cursos = df_cursos.dropna(subset=['DIAS', 'HORA_INICIO'])

    return df_cursos, df_salones

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
    print("--- Normalizando datos ---")

    def limpiar_hora(valor):
        try: return int(float(valor))
        except: return 0

    df_cursos['HH_INI'] = df_cursos['HORA_INICIO'].apply(limpiar_hora)
    
    mapa_inicio = {
        830: [1], 950: [2], 1110: [3], 1230: [4], 1350: [5],
        1510: [6], 1630: [7], 1750: [8], 1910: [9], 2030: [10],
        2020: [10], 2130: [11]
    }
    df_cursos['BLOQUES_REQ'] = df_cursos['HH_INI'].map(lambda x: mapa_inicio.get(x, []))

    def detectar_tipo(txt):
        s = str(txt).upper()
        return 4 if ('LAB' in s or 'COMPU' in s) else 3

    if 'TIPO_CODE' not in df_salones.columns:
        col = 'TIPO' if 'TIPO' in df_salones.columns else df_salones.columns[4]
        df_salones['TIPO_CODE'] = df_salones[col].apply(detectar_tipo)

    def calcular_prioridad(row):
        score = 0
        estado = str(row.get('ESTADO_CURSO', '')).upper()
        materia = str(row.get('MATERIA', '')).upper()
        Tipo_alumno = str(row.get('TIPO_ALUMNO', '')).upper()
        es_regimen = 'CÍCLICO' in estado and 'CONTRACÍCLICO' not in estado
        
        if es_regimen:
            score += 1000
            score += 200 if 'CCL' in materia else 100
            score += 200 if 'NUEVO' in Tipo_alumno else 100
        else:
            score += 3000
            score += 200 if 'CCL' in materia else 100
        return score

    df_cursos['PRIORIDAD_CALC'] = df_cursos.apply(calcular_prioridad, axis=1)
    return df_cursos, df_salones

# ==========================================
# 3. GESTOR DE SALAS (ALGORITMO REASIGNACIÓN)
# ==========================================

class GestorDeSalas:
    def __init__(self, df_salones, dias_posibles):
        self.salones_info = df_salones.copy()
        self.inventario = {}
        
        # Estructura: self.inventario[id_sala][dia] = set(bloques_libres)
        for _, row in df_salones.iterrows():
            id_sala = str(row['NUMERO']).strip().upper()
            self.inventario[id_sala] = {dia: set(CATALOGO_BLOQUES.keys()) for dia in dias_posibles}

    def buscar_mejor_sala(self, bloques_req, dia, cupos, tipo_req, jornada):
        mejor_sala = None
        min_desperdicio = float('inf')

        for _, sala in self.salones_info.iterrows():
            id_sala = str(sala['NUMERO']).strip().upper()
            edificio = str(sala.get('EDIFICIO', '')).strip().upper()
            capacidad = sala['CAPACIDAD']
            tipo_sala = sala['TIPO_CODE']

            # 1. Validación de Tipo y Capacidad
            if capacidad < cupos: continue
            if tipo_req == 4 and tipo_sala != 4: continue
            if tipo_req == 3 and tipo_sala == 4: continue

            # 2. Regla Vespertina ('V') - Blindaje Casa Central
            if jornada == 'V':
                if 'POSGRADO' in edificio or id_sala.startswith('P'):
                    continue

            # 3. Validación de Horario
            if dia in self.inventario[id_sala]:
                bloques_libres = self.inventario[id_sala][dia]
                if bloques_req.issubset(bloques_libres):
                    desperdicio = capacidad - cupos
                    if desperdicio < min_desperdicio:
                        min_desperdicio = desperdicio
                        mejor_sala = id_sala

        if mejor_sala:
            self.inventario[mejor_sala][dia] -= bloques_req
            return mejor_sala
        
        return None

    def reporte_libres(self):
        reporte = []
        for id_sala, dias in self.inventario.items():
            # Buscar info de la sala para el reporte
            filtro = self.salones_info['NUMERO'].astype(str).str.upper() == id_sala
            if not filtro.any(): continue
            info = self.salones_info[filtro].iloc[0]
            
            for dia, bloques in dias.items():
                for b in sorted(list(bloques)):
                    reporte.append({
                        'Edificio': info.get('EDIFICIO'), 'Sala': id_sala, 
                        'Capacidad': info['CAPACIDAD'], 'Dia': dia, 'Bloque': b,
                        'Horario': CATALOGO_BLOQUES[b]['txt']
                    })
        return pd.DataFrame(reporte)

# ==========================================
# 4. LÓGICA DE EJECUCIÓN (PROCESO ITERATIVO)
# ==========================================

def main():
    try:
        df_c, df_s = cargar_datos()
        df_c, df_s = normalizar_datos(df_c, df_s)

        # Ordenar por prioridad y tamaño de curso para asegurar que los "grandes" busquen primero
        df_c = df_c.sort_values(by=['PRIORIDAD_CALC', 'CUPOS'], ascending=[True, False])
        
        grupos = df_c.groupby(['NRC', 'DIAS'], sort=False)
        dias_unicos = df_c['DIAS'].unique()
        gestor = GestorDeSalas(df_s, dias_unicos)

        # Pre-procesar todos los grupos en una lista de objetos
        pendientes = []
        for (nrc, dia), g_df in grupos:
            bloques = set()
            for b_list in g_df['BLOQUES_REQ']: 
                if isinstance(b_list, list):
                    bloques.update(b_list)
            
            if not bloques: continue
            
            # AQUÍ ESTABA EL ERROR: Se agregó la llave 'bloques'
            pendientes.append({
                'nrc': nrc, 
                'dia': dia, 
                'df': g_df, 
                'cupos': g_df['CUPOS'].max(), 
                'tipo': g_df['TIPO_SALON_CODE'].iloc[0],
                'jornada': str(g_df.get('JORNADA', pd.Series([''])).iloc[0]).upper().strip(),
                'bloques': bloques, 
                'sala': None
            })

        print(f"\n--- Iniciando Proceso Iterativo (Total grupos: {len(pendientes)}) ---")
        
        iteracion = 1
        hay_cambios = True
        asignados_finales = []

        # El bucle de reasignación: Sigue intentando mientras logre asignar al menos a uno nuevo
        while hay_cambios and len(pendientes) > 0:
            print(f"Iteración {iteracion}: Procesando {len(pendientes)} cursos pendientes...")
            hay_cambios = False
            siguen_pendientes = []

            for item in pendientes:
                # El motor busca la mejor sala (Best-Fit) en el inventario actual
                sala_encontrada = gestor.buscar_mejor_sala(
                    item['bloques'], item['dia'], item['cupos'], item['tipo'], item['jornada']
                )

                if sala_encontrada:
                    item['sala'] = sala_encontrada
                    asignados_finales.append(item)
                    hay_cambios = True 
                else:
                    siguen_pendientes.append(item)
            
            pendientes = siguen_pendientes
            iteracion += 1

        # Reconstrucción de resultados para exportación
        res_asignados = []
        for item in asignados_finales:
            info_s = df_s[df_s['NUMERO'].astype(str).str.upper() == item['sala']].iloc[0]
            for _, row in item['df'].iterrows():
                d = row.to_dict()
                d.update({
                    'SALA_ASIGNADA': item['sala'], 
                    'EDIFICIO_ASIGNADO': info_s['EDIFICIO'], 
                    'CAPACIDAD_SALA': info_s['CAPACIDAD'],
                    'ESTADO_PROCESO': 'ASIGNADO'
                })
                res_asignados.append(d)

        res_fallidos = []
        for item in pendientes:
            for _, row in item['df'].iterrows():
                d = row.to_dict()
                d.update({'ESTADO_PROCESO': 'SIN SALA DISPONIBLE'})
                res_fallidos.append(d)

        # Generación del reporte final
        nombre = f"Resultado_Asignacion_Exhaustiva_{datetime.now().strftime('%H%M%S')}.xlsx"
        ruta = os.path.join(RUTA_PROCESADOS, nombre)
        df_libres = gestor.reporte_libres()

        with pd.ExcelWriter(ruta) as writer:
            if res_asignados:
                pd.DataFrame(res_asignados).to_excel(writer, sheet_name='Asignados', index=False)
            if res_fallidos:
                pd.DataFrame(res_fallidos).to_excel(writer, sheet_name='No_Asignados', index=False)
            if not df_libres.empty:
                df_libres.to_excel(writer, sheet_name='Bloques_Libres', index=False)

        print(f"\n✅ PROCESO FINALIZADO CON ÉXITO")
        print(f"Total Asignados: {len(res_asignados)} filas.")
        print(f"Total Fallidos: {len(res_fallidos)} filas.")
        print(f"Archivo generado en: {ruta}")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()