import pandas as pd
import itertools
import os

# ==========================================
# 0. CONFIGURACIÓN DE RUTAS
# ==========================================
# Rutas de entrada según tu contexto
RUTA_ASIGNADOS = r"C:\Users\fpinaleo\Desktop\REPOSITORIO\PROYECTOS_DOAE\PROYECTOS_CONTROL_DE_GESTION\PROYECTOS\PROYECTO_ASIGNACION_SALAS\datos\01_brutos\maestro_asignados_202625.xlsx"
RUTA_SALONES = r"C:\Users\fpinaleo\Desktop\REPOSITORIO\PROYECTOS_DOAE\PROYECTOS_CONTROL_DE_GESTION\PROYECTOS\PROYECTO_ASIGNACION_SALAS\datos\01_brutos\maestro_salones 202625.csv"

# Ruta de salida (asumiendo tu carpeta de procesados)
CARPETA_PROCESADOS = r"C:\Users\fpinaleo\Desktop\REPOSITORIO\PROYECTOS_DOAE\PROYECTOS_CONTROL_DE_GESTION\PROYECTOS\PROYECTO_ASIGNACION_SALAS\datos\03_procesados"
RUTA_SALIDA = os.path.join(CARPETA_PROCESADOS, "Catalogo_Disponibilidad_Salas.xlsx")

# ==========================================
# 1. CARGA DE DATOS
# ==========================================
def cargar_datos():
    print("--- Cargando archivos ---")
    df_asignados = pd.read_excel(RUTA_ASIGNADOS)
    
    # Manejo de codificación para el CSV de salones (igual que en tu código original)
    try:
        df_salones = pd.read_csv(RUTA_SALONES, sep=None, engine='python', encoding='utf-8-sig')
    except:
        df_salones = pd.read_csv(RUTA_SALONES, sep=None, engine='python', encoding='latin-1')
        
    # Limpieza básica de columnas de salones
    df_salones.columns = df_salones.columns.astype(str).str.upper().str.strip()
    df_salones.columns = df_salones.columns.str.replace('ï»¿', '').str.replace('\ufeff', '')
    
    return df_asignados, df_salones

# ==========================================
# 2. GENERACIÓN DEL CATÁLOGO Y CRUCE
# ==========================================
def analizar_disponibilidad(df_asignados, df_salones):
    print("--- Generando catálogo de bloques y cruzando datos ---")
    
    # 1. Definir los universos posibles
    dias_semana = ['L', 'M', 'Mi', 'J', 'V', 'S'] # Agrega 'D' si hay clases los domingos
    bloques = list(range(1, 12)) # Bloques del 1 al 11
    salas_unicas = df_salones['NUMERO'].dropna().unique()
    
    # 2. Crear el producto cartesiano (Catálogo maestro de todos los huecos posibles)
    combinaciones = list(itertools.product(salas_unicas, dias_semana, bloques))
    df_catalogo = pd.DataFrame(combinaciones, columns=['SALA', 'DIA', 'BLOQUE'])
    
    # 3. Enriquecer el catálogo con la información de los salones (Edificio, Capacidad, Tipo)
    df_salones_info = df_salones[['NUMERO', 'EDIFICIO', 'CAPACIDAD', 'TIPO']].drop_duplicates('NUMERO')
    df_catalogo = pd.merge(df_catalogo, df_salones_info, left_on='SALA', right_on='NUMERO', how='left')
    df_catalogo.drop(columns=['NUMERO'], inplace=True)
    
    # 4. Preparar el dataframe de asignados para el cruce
    # Nos aseguramos de que las columnas tengan el mismo nombre y tipo para hacer el merge
    df_asignados_clean = df_asignados[['NRC', 'Dia', 'Bloques_Usados', 'sala']].copy()
    df_asignados_clean.columns = ['NRC_ASIGNADO', 'DIA', 'BLOQUE', 'SALA']
    
    # Limpiar espacios en blanco y estandarizar tipos de datos para asegurar el cruce
    df_asignados_clean['SALA'] = df_asignados_clean['SALA'].astype(str).str.strip()
    df_catalogo['SALA'] = df_catalogo['SALA'].astype(str).str.strip()
    
    df_asignados_clean['DIA'] = df_asignados_clean['DIA'].astype(str).str.strip()
    df_catalogo['DIA'] = df_catalogo['DIA'].astype(str).str.strip()
    
    # Asegurar que los bloques sean numéricos
    df_asignados_clean['BLOQUE'] = pd.to_numeric(df_asignados_clean['BLOQUE'], errors='coerce')
    df_asignados_clean = df_asignados_clean.dropna(subset=['BLOQUE']) # Quitar filas sin bloque
    
    # 5. Cruzar el Catálogo con las Asignaciones (LEFT JOIN)
    df_resultado = pd.merge(df_catalogo, df_asignados_clean, 
                            on=['SALA', 'DIA', 'BLOQUE'], 
                            how='left')
    
    # 6. Determinar el Estado (LIBRE o OCUPADO)
    # Si cruzó y tiene un NRC, está ocupado. Si el NRC es nulo, está libre.
    df_resultado['ESTADO'] = df_resultado['NRC_ASIGNADO'].apply(lambda x: 'LIBRE' if pd.isna(x) else 'OCUPADO')
    
    # Opcional: Reordenar columnas para que sea más legible
    columnas_finales = ['EDIFICIO', 'SALA', 'CAPACIDAD', 'TIPO', 'DIA', 'BLOQUE', 'ESTADO', 'NRC_ASIGNADO']
    df_resultado = df_resultado[columnas_finales]
    
    # Ordenar el resultado para que tenga sentido temporal y espacial
    df_resultado = df_resultado.sort_values(by=['EDIFICIO', 'SALA', 'DIA', 'BLOQUE'])
    
    return df_resultado

# ==========================================
# 3. EJECUCIÓN Y EXPORTACIÓN
# ==========================================
def main():
    try:
        # Cargar
        df_asig, df_sal = cargar_datos()
        
        # Procesar
        df_disponibilidad = analizar_disponibilidad(df_asig, df_sal)
        
        # Estadísticas rápidas por consola
        total_bloques = len(df_disponibilidad)
        bloques_libres = len(df_disponibilidad[df_disponibilidad['ESTADO'] == 'LIBRE'])
        bloques_ocupados = total_bloques - bloques_libres
        
        print("\n=== RESUMEN DE DISPONIBILIDAD ===")
        print(f"Total de bloques posibles: {total_bloques}")
        print(f"Bloques Ocupados: {bloques_ocupados} ({round(bloques_ocupados/total_bloques*100, 1)}%)")
        print(f"Bloques Libres: {bloques_libres} ({round(bloques_libres/total_bloques*100, 1)}%)")
        print("=================================\n")
        
        # Guardar archivo
        os.makedirs(CARPETA_PROCESADOS, exist_ok=True)
        df_disponibilidad.to_excel(RUTA_SALIDA, index=False, sheet_name='Disponibilidad')
        print(f"✅ Archivo generado exitosamente en: {RUTA_SALIDA}")
        print("Tip: Abre el Excel e inserta una Tabla Dinámica para filtrar rápidamente por Edificio, Día y Estado = 'LIBRE'.")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()