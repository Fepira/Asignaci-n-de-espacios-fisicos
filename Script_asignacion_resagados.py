import pandas as pd
import re

# ==========================================
# 1. CONFIGURACIÓN Y DICCIONARIOS
# ==========================================

mapa_inicio = {
    830: 1, 950: 2, 1110: 3, 1230: 4,
    1350: 5, 1510: 6, 1630: 7, 1750: 8,
    1910: 9, 2030: 10, 2020: 10, 2130: 11
}

CATALOGO_BLOQUES = {
    1: {'txt': '08:30 - 09:45'}, 2: {'txt': '09:50 - 11:05'},
    3: {'txt': '11:10 - 12:25'}, 4: {'txt': '12:30 - 13:45'},
    5: {'txt': '13:50 - 15:05'}, 6: {'txt': '15:10 - 16:25'},
    7: {'txt': '16:30 - 17:45'}, 8: {'txt': '17:50 - 19:05'},
    9: {'txt': '19:10 - 20:25'}, 10: {'txt': '20:30 - 21:45'},
    11: {'txt': '21:50 - 22:10'}
}

# Definimos las columnas clave que queremos ver en el Excel final
COLUMNAS_CLAVE_REPORTE = [
    'NRC', 'Materia', 'Curso', 'Titulo_curso', 'Dias', 
    'Hora_inicio', 'Hora_fin', 'Cupo_maximo', 'salon_cod',
    'ASIGNADO_EDIFICIO', 'ASIGNADO_SALA', 'ASIGNADO_TIPO', 'ASIGNADO_CAPACIDAD', 
    'ESTADO_PROCESO'
]

# ==========================================
# 2. FUNCIONES AUXILIARES
# ==========================================

def extraer_numero_bloque(texto):
    if pd.isna(texto): return None
    if isinstance(texto, (int, float)):
        return int(texto)
    numeros = re.findall(r'\d+', str(texto))
    return int(numeros[0]) if numeros else None

def calcular_puntaje(materia, salon_cod, cupo, num_bloques):
    puntaje = 0
    if salon_cod == 4:
        puntaje += 10000 
    if "CCL" not in str(materia).upper():
        puntaje += 5000
    puntaje += (cupo * 10)
    puntaje += (num_bloques * 5)
    return puntaje

# ==========================================
# 3. LÓGICA PRINCIPAL
# ==========================================

def main():
    archivo_excel = 'maestro_cursos_no_existentes.xlsx'
    print(f"Leyendo archivo: {archivo_excel} ...")

    try:
        df_cursos = pd.read_excel(archivo_excel, sheet_name='Hoja1')
        df_salas_libres = pd.read_excel(archivo_excel, sheet_name='Hoja2')
    except Exception as e:
        print(f"Error al leer el Excel: {e}")
        return

    # ---------------------------------------------------------
    # PROCESAMIENTO: HOJA 1 (CURSOS)
    # ---------------------------------------------------------
    # Mapear utilizando únicamente la hora_inicio para definir el bloque
    df_cursos['Bloque_req'] = df_cursos['Hora_inicio'].map(mapa_inicio)
    
    cursos_pendientes = df_cursos.dropna(subset=['Bloque_req']).copy()
    cursos_pendientes['Bloque_req'] = cursos_pendientes['Bloque_req'].astype(int)

    lista_grupos_cursos = []
    
    for (nrc, dia), grupo in cursos_pendientes.groupby(['NRC', 'Dias']):
        bloques = sorted(grupo['Bloque_req'].unique().tolist())
        row_ref = grupo.iloc[0] 
        
        score = calcular_puntaje(
            row_ref['Materia'], 
            row_ref['salon_cod'], 
            row_ref['Cupo_maximo'], 
            len(bloques)
        )
        
        lista_grupos_cursos.append({
            'NRC': nrc,
            'Materia': row_ref['Materia'],
            'Curso': row_ref['Curso'],
            'Dias': dia,
            'Bloques_Requeridos': set(bloques),
            'Cupo_maximo': row_ref['Cupo_maximo'],
            'salon_cod': row_ref['salon_cod'],
            'Puntaje': score,
            'Dataframe_Grupo': grupo 
        })

    lista_grupos_cursos.sort(key=lambda x: x['Puntaje'], reverse=True)

    # ---------------------------------------------------------
    # PROCESAMIENTO: HOJA 2 (SALAS)
    # ---------------------------------------------------------
    df_salas_libres['Num_Bloque_Int'] = df_salas_libres['Num_Bloque'].apply(extraer_numero_bloque)
    df_salas_libres = df_salas_libres.dropna(subset=['Num_Bloque_Int'])
    
    if 'Estado' in df_salas_libres.columns:
        df_salas_libres = df_salas_libres[df_salas_libres['Estado'].str.upper() == 'LIBRE']

    # Inventario de salas
    inventario = {}

    for _, row in df_salas_libres.iterrows():
        edificio = str(row['Edificio']).strip()
        nombre_sala = str(row['Sala']).strip() 
        tipo = row['Tipo_sala']
        capacidad = row['Capacidad']
        
        llave_sala = (edificio, nombre_sala, tipo, capacidad)
        
        dia = str(row['Dia']).strip()
        bloque = int(row['Num_Bloque_Int'])
        
        if llave_sala not in inventario:
            inventario[llave_sala] = {}
        
        if dia not in inventario[llave_sala]:
            inventario[llave_sala][dia] = set()
            
        inventario[llave_sala][dia].add(bloque)

    # ---------------------------------------------------------
    # ALGORITMO DE ASIGNACIÓN
    # ---------------------------------------------------------
    resultados_asignados = []
    resultados_no_asignados = []

    print(f"Iniciando asignación para {len(lista_grupos_cursos)} grupos de cursos (NRC/Día)...")

    for curso in lista_grupos_cursos:
        req_bloques = curso['Bloques_Requeridos']
        req_dia = str(curso['Dias']).strip()
        req_cupo = curso['Cupo_maximo']
        req_tipo = curso['salon_cod']
        
        mejor_opcion = None
        min_desperdicio = float('inf')

        for llave_sala, dias_disponibles in inventario.items():
            edificio_cand, sala_cand, tipo_cand, cap_cand = llave_sala
            
            if cap_cand < req_cupo:
                continue
            if req_tipo == 4 and tipo_cand != 4:
                continue 
            if req_tipo == 3 and tipo_cand == 4:
                continue

            if req_dia in dias_disponibles:
                bloques_libres_sala = dias_disponibles[req_dia]
                
                if req_bloques.issubset(bloques_libres_sala):
                    desperdicio = cap_cand - req_cupo
                    if desperdicio < min_desperdicio:
                        min_desperdicio = desperdicio
                        mejor_opcion = llave_sala

        # -----------------------------------------------------
        # REGISTRAR RESULTADO Y ACTUALIZAR INVENTARIO
        # -----------------------------------------------------
        registros_originales = curso['Dataframe_Grupo']
        
        if mejor_opcion:
            edificio_sel, sala_sel, tipo_sel, cap_sel = mejor_opcion
            
            # Quitar los bloques asignados del inventario
            inventario[mejor_opcion][req_dia] = inventario[mejor_opcion][req_dia] - req_bloques
            
            for _, fila in registros_originales.iterrows():
                datos = fila.to_dict()
                datos['ASIGNADO_EDIFICIO'] = edificio_sel
                datos['ASIGNADO_SALA'] = sala_sel
                datos['ASIGNADO_TIPO'] = tipo_sel
                datos['ASIGNADO_CAPACIDAD'] = cap_sel
                datos['ESTADO_PROCESO'] = 'EXITO'
                resultados_asignados.append(datos)
        else:
            for _, fila in registros_originales.iterrows():
                datos = fila.to_dict()
                datos['ASIGNADO_EDIFICIO'] = None
                datos['ASIGNADO_SALA'] = None
                datos['ASIGNADO_TIPO'] = None
                datos['ASIGNADO_CAPACIDAD'] = None
                datos['ESTADO_PROCESO'] = 'SIN CUPO/HORARIO'
                resultados_no_asignados.append(datos)

    # ---------------------------------------------------------
    # GENERAR REPORTE DE SALAS RESTANTES (LIBRES)
    # ---------------------------------------------------------
    bloques_sobrantes = []
    
    # Recorremos el diccionario final para ver qué quedó
    for llave_sala, dias in inventario.items():
        edificio, sala, tipo, capacidad = llave_sala
        for dia, bloques_libres in dias.items():
            for bloque in sorted(list(bloques_libres)): # Solo iteramos sobre los que quedaron en el set
                horario_txt = CATALOGO_BLOQUES.get(bloque, {}).get('txt', 'Desconocido')
                bloques_sobrantes.append({
                    'Edificio': edificio,
                    'Sala': sala,
                    'Tipo_sala': tipo,
                    'Capacidad': capacidad,
                    'Dia': dia,
                    'Num_Bloque': bloque,
                    'Horario': horario_txt,
                    'Estado': 'LIBRE - SIN ASIGNAR'
                })

    # ---------------------------------------------------------
    # EXPORTAR RESULTADOS (FILTRADOS)
    # ---------------------------------------------------------
    df_out_asignados = pd.DataFrame(resultados_asignados)
    df_out_fallidos = pd.DataFrame(resultados_no_asignados)
    df_out_restantes = pd.DataFrame(bloques_sobrantes)

    # Filtrar solo las columnas clave (verificando que existan en el DataFrame)
    cols_asignados = [c for c in COLUMNAS_CLAVE_REPORTE if c in df_out_asignados.columns]
    cols_fallidos = [c for c in COLUMNAS_CLAVE_REPORTE if c in df_out_fallidos.columns]

    if not df_out_asignados.empty:
        df_out_asignados = df_out_asignados[cols_asignados]
    if not df_out_fallidos.empty:
        df_out_fallidos = df_out_fallidos[cols_fallidos]

    nombre_salida = 'resultado_asignacion_resumido.xlsx'
    
    with pd.ExcelWriter(nombre_salida, engine='openpyxl') as writer:
        if not df_out_asignados.empty:
            df_out_asignados.to_excel(writer, sheet_name='Asignados', index=False)
        if not df_out_fallidos.empty:
            df_out_fallidos.to_excel(writer, sheet_name='No Asignados', index=False)
        if not df_out_restantes.empty:
            df_out_restantes.to_excel(writer, sheet_name='Salas Libres Restantes', index=False)

    print(f"Proceso completado.")
    print(f"Cursos Asignados: {len(df_out_asignados)} filas.")
    print(f"Cursos No Asignados: {len(df_out_fallidos)} filas.")
    print(f"Bloques Libres Sobrantes: {len(df_out_restantes)} bloques.")
    print(f"Archivo guardado: {nombre_salida}")

if __name__ == "__main__":
    main()