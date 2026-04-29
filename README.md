Sistema de Asignación Automatizada de Salas (SAAS)
Este proyecto consiste en un motor de asignación basado en Python que optimiza la distribución de cursos académicos en las salas disponibles de la institución, considerando restricciones de horario, capacidad, tipo de aula y prioridades institucionales.

Estructura del Proyecto.
El script utiliza rutas relativas basadas en la ubicación del archivo ejecutable. Se espera la siguiente jerarquía:

.
├── scripts/
│   └── asignador_salas.py        # Código fuente principal
└── datos/
    ├── 01_brutos/                 # Input: Archivos Excel/CSV originales
    └── 03_procesados/             # Output: Resultados de la asignación

Requisitos Técnicos.
El sistema está desarrollado en Python 3.8+ y depende de las siguientes librerías:

- pandas: Procesamiento de estructuras de datos.
- numpy: Operaciones lógicas y manejo de nulos.
- openpyxl: Motor de lectura/escritura para archivos Excel (.xlsx).

Para instalar las dependencias:

    pip install pandas numpy openpyxl

Lógica de Funcionamiento.
El motor de asignación sigue un flujo de cuatro etapas:

1. Ingesta y Limpieza
 - Formatos: Soporta Excel para el maestro de cursos y CSV (con detección automática de encoding utf-8-sig o latin-1) para el maestro de salones.
 - Sanitización: Limpia espacios en blanco, convierte encabezados a mayúsculas y elimina caracteres especiales (BOM) de las columnas

2. Normalización por Bloques.
El sistema convierte las horas de inicio en Bloques Académicos fijos (1 al 11). Esto permite una comparación matricial rápida para detectar colisiones de horario (topes).
 - Ejemplo: Un curso que inicia a las 08:30 se mapea al Bloque 1.
 
3. Modelo de Priorización (Heurística).
Antes de asignar, el script ordena los cursos mediante un score calculado:
 - Estado del Curso: Los cursos "Contracíclicos" o fuera de régimen suelen recibir un peso distinto para asegurar espacios críticos.
 - Perfil del Alumno: Se da prioridad a los cursos de "Ingreso Nuevo".
 - Materias CCL: Tienen un bono de prioridad en la cola de asignación.

4. Índice de Saturación (IS).
Esta es una de las métricas más críticas. Se calcula como:

$$IS = \frac{\text{Demanda (Cursos con Cupo X)}}{\text{Oferta (Salas con Capacidad} \geq \text{X)}}$$


- Los cursos con un IS alto se asignan primero, ya que tienen menos opciones de salas disponibles en el inventario físico.🛠 

Especificaciones del Código.

Clase GestorDeSalas
Es el núcleo del sistema. Maneja un diccionario de disponibilidad en memoria:
 - self.disp[dia][id_sala]: Contiene un set de bloques disponibles.
 - Al asignar un curso, se realiza una operación de resta de conjuntos (set - set) para marcar los bloques como ocupados.
 
Criterios de Selección de Sala
- Tipo: Debe coincidir el TIPO_CODE (Ej: 4 para Laboratorios, 3 para Salas Teóricas).
- Capacidad: La capacidad de la sala debe ser $\geq$ a los cupos requeridos.
- Disponibilidad: Todos los bloques del curso deben estar libres en esa sala específica. 

Salida de Datos (Output)
El archivo generado en 03_procesados/ contiene:
 - Asignados: Lista de cursos con su sala exitosa y el % de ocupación (eficiencia de la sala).
 - No_Asignados: Cursos rechazados con el motivo específico (ej. "Tope horario" o "Sin capacidad/tipo").
 - Bloques_Libres: Inventario de espacios remanentes para asignaciones manuales o eventos extra.
