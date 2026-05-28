# Face Morphing Tool

Herramienta para generar videos de morphing facial de alta calidad a partir de fotografías. Utiliza correspondencia de puntos manual o automática (MediaPipe) y Thin Plate Splines (TPS) como motor de deformación.

---

## 📋 Tabla de contenidos

1. [Instalación](#instalación)
2. [Flujo de trabajo rápido](#flujo-de-trabajo-rápido)
3. [Pipeline principal](#pipeline-principal)
4. [Modos de morphing](#modos-de-morphing)
5. [Editor de landmarks](#editor-de-landmarks)
6. [Revisar y ajustar pares existentes](#revisar-y-ajustar-pares-existentes)
7. [Control de tiempos y frames](#control-de-tiempos-y-frames)
8. [Generación automática de landmarks](#generación-automática-de-landmarks)
9. [Auto-inversión de pares](#auto-inversión-de-pares)
10. [Parámetros de calidad de video](#parámetros-de-calidad-de-video)
11. [Backends de morphing](#backends-de-morphing)
12. [Referencia de argumentos CLI](#referencia-de-argumentos-cli)
13. [Estructura del proyecto](#estructura-del-proyecto)
14. [Ejemplos completos](#ejemplos-completos)
15. [Solución de problemas](#solución-de-problemas)

---

## ⚙️ Instalación

```bash
# Crear entorno virtual e instalar dependencias
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows PowerShell
# source .venv/bin/activate          # macOS / Linux

pip install -r requirements.txt
```

> **Windows:** Si hay error de permisos en PowerShell, ejecuta primero:
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
> ```

---

## ⚡ Flujo de trabajo rápido

```
Fotos (photos/) → pipeline.py → Editor de landmarks → Editor de tiempos → Render → morph.mp4
```

```bash
# Render básico con todas las opciones interactivas
python pipeline.py

# Solo render, sin editores (asume landmarks ya guardados)
python pipeline.py --skip-editor --skip-timing

# Dataset alternativo en modo todos-los-pares
python pipeline.py --photos photos_nuevo --landmarks-dir landmarks_nuevo --mode all-pairs

# Revisar y ajustar pares existentes
python review.py --photos photos_nuevo --landmarks-dir landmarks_nuevo
```

---

## 🔄 Pipeline principal

`pipeline.py` orquesta todo el proceso en pasos secuenciales:

| Paso | Descripción |
|------|-------------|
| **1** | Escanea el directorio `--photos` en busca de imágenes `.jpg` / `.png` |
| **2** | Selección interactiva de modo de morphing (sequential / all-pairs) |
| **3** | Detecta qué pares de landmarks JSON faltan |
| **3.5** | **Auto-inversión:** si existe `B_A.json` y falta `A_B.json`, lo genera automáticamente |
| **4** | Abre el editor de landmarks para los pares que realmente faltan |
| **5** | Editor de tiempos (duración de transiciones, hold, fps) |
| **6** | Invoca `morph.py` para el render final |

### 📌 Opciones del pipeline

```bash
python pipeline.py [opciones]

  --photos DIR            Directorio de fotos           (por defecto: photos)
  --landmarks-dir DIR     Directorio de JSONs            (por defecto: landmarks)
  --output ARCHIVO        Video de salida                (por defecto: output/morph.mp4)
  --mode MODE             sequential | all-pairs
  --backend BACKEND       tps | delaunay | opticalflow   (por defecto: tps)
  --profile PERFIL        preview | final
  --skip-editor           Omitir editor de landmarks
  --skip-timing           Omitir editor de tiempos
  --use-cache             Usar caché de landmarks en el render
```

---

## 🎬 Modos de morphing

### Sequential
Recorre las imágenes en orden y cierra el ciclo al final:

```
img1 → img2 → img3 → img4 → img5 → img1
```

Requiere **N JSONs** (un JSON por transición consecutiva).

### All-pairs (Circuito de Euler)
Visita todos los pares posibles exactamente una vez, sin repetir:

```
img1 → img3 → img5 → img2 → img4 → img1  (orden optimizado)
```

Para N imágenes: `N(N-1)/2` pares únicos. Con auto-inversión solo necesitas crear la mitad.

---

## ✏️ Editor de landmarks

Interfaz gráfica interactiva para colocar y ajustar puntos de correspondencia entre dos imágenes.

### Lanzar directamente (un par)

```bash
python landmark_editor.py --image-a photos/Hermana.jpg --image-b photos/Hermano.jpg
python landmark_editor.py --image-a fotos/A.jpg --image-b fotos/B.jpg --display-width 450
```

### Lanzar en sesión (varios pares en cadena)

```bash
python landmark_editor.py --session session.json
```

El pipeline genera y gestiona `session.json` automáticamente cuando hay múltiples pares pendientes.

### Interfaz de usuario

```
┌──────────────────────────────────────────────────────────────┐
│  [Barra de sesión]  Par 3/8: ImageA <-> ImageB | p=Prev n=Next  │
├────────────────────────┬──┬────────────────────────┤
│                        │  │                        │
│       Imagen A         │▌ │       Imagen B         │
│       (origen)         │  │       (destino)        │
│                        │  │                        │
├────────────────────────┴──┴────────────────────────┤
│  S=Guardar  A=Auto  U=Undo  D=Borrar  Z=Zoom reset  │
│  Pares: 30  |  [*unsaved*]  |  Zoom A:1.0× B:2.3×  │
└──────────────────────────────────────────────────────┘
```

### ⌨️ Atajos de teclado

| Tecla | Acción |
|-------|--------|
| **Clic izquierdo (img A)** | Coloca el punto A (parpadea en amarillo) |
| **Clic izquierdo (img B)** | Completa el par en B |
| **Clic izquierdo sobre punto** | Selecciona para mover (arrastra) |
| **Clic derecho sobre punto** | Selecciona sin mover (naranja) |
| `S` | Guardar JSON |
| `A` | Auto-seed: 30 puntos semánticos de MediaPipe |
| `U` | Deshacer el último par |
| `D` / `Delete` | Eliminar el par seleccionado |
| `R` + `R` | Resetear todos los pares (doble confirmación) |
| `L` | Recargar desde JSON (descarta cambios no guardados) |
| `Z` / `0` | Resetear zoom y pan en ambos paneles |
| `N` | Siguiente par (modo sesión) |
| `P` | Par anterior (modo sesión) |
| `Q` | Salir |
| `Esc` | Cancelar punto A pendiente / deseleccionar |

### 🔍 Zoom y navegación

| Gesto | Acción |
|-------|--------|
| `Ctrl` + scroll arriba | Zoom in centrado en el cursor |
| `Ctrl` + scroll abajo | Zoom out |
| Clic botón del medio + arrastrar | Pan (desplazar vista) |
| `Z` o `0` | Resetear zoom y pan |

**Características:**
- Zoom independiente en panel A y panel B (rango: 1× – 8×)
- Las coordenadas del JSON **no se modifican** al hacer zoom; solo cambia la vista
- La barra de estado muestra el zoom actual: `Zoom A:2.3× B:1.0×`
- Radio de detección: 20px (área alrededor del punto para seleccionar)

### 🎯 Indicadores visuales

| Visual | Significado |
|--------|-------------|
| Punto amarillo parpadeante | Punto A colocado, esperando clic en imagen B |
| Anillo blanco alrededor de un punto | Hover: ese punto se seleccionará al hacer clic |
| Punto naranja | Punto actualmente seleccionado |
| `[*unsaved*]` en barra de estado | Hay cambios sin guardar |

### 🎓 Flujo recomendado para un par nuevo

1. Presionar `A` → auto-seed con 30 puntos de MediaPipe
2. Revisar visualmente que los puntos coincidan bien en ambos lados
3. Hacer zoom (`Ctrl+scroll`) en zonas problemáticas: ojos, boca, contorno
4. Corregir: **clic izquierdo** sobre el punto → arrastrar a la posición correcta
5. Añadir puntos extra si se necesita más control en zonas específicas
6. Presionar `S` para guardar
7. En modo sesión: `N` para pasar al siguiente par

---

## 🔎 Revisar y ajustar pares existentes

### 📦 Script de revisión en lote: `review.py` ⭐ NUEVO

Para abrir todos los landmarks de un directorio en sesión para revisar y ajustar:

```bash
# Revisar todos los pares de un dataset
python review.py --photos photos_nuevo --landmarks-dir landmarks_nuevo

# Con filtro (solo ciertos pares)
python review.py --photos photos_nuevo --landmarks-dir landmarks_nuevo --filter "1_*"
python review.py --photos photos_nuevo --landmarks-dir landmarks_nuevo --filter "*_2*"

# Con tamaño de display personalizado
python review.py --photos photos --landmarks-dir landmarks --display-width 500
```

**Filtros disponibles (glob patterns):**
- `"1_*"` — todos los pares donde la imagen A es "1" (1_2, 1_3, 1_4, ...)
- `"*_3*"` — todos los pares donde aparece imagen 3 (1_3, 2_3, 3_1, 3_2, ...)
- `"2_?.json"` — pares de dos dígitos partiendo de 2

### Revisar un par específico

Para abrir el editor directamente en un par ya editado:

```bash
python landmark_editor.py --image-a photos_nuevo/1.png --image-b photos_nuevo/2.png
```

El editor cargará automáticamente el JSON existente si lo encuentra en `landmarks_nuevo/1_2.json`.

### Workflow de ajuste fino (par ya editado)

1. Abrir `review.py` o el editor directamente
2. El editor carga los puntos guardados
3. Hacer zoom en zonas problemáticas (`Ctrl+scroll`)
4. **Mover un punto:** clic izquierdo sobre el punto → arrastrar → soltar
5. **Borrar un punto malo:** clic derecho para seleccionar → `D`
6. **Añadir un punto nuevo:** clic en zona A → clic en zona correspondiente B
7. `S` para guardar — los cambios se reflejan en el siguiente render

---

## ⏱️ Control de tiempos y frames

### 🎚️ Editor visual de tiempos

Se lanza automáticamente desde el pipeline (paso 5), o manualmente:

```bash
python timing_editor.py
```

Muestra tres trackbars:
- **Duration** — Duración de la transición entre dos caras (0.1–10.0 segundos)
- **Hold** — Tiempo que permanece estática cada imagen (0.0–5.0 segundos)
- **FPS** — Fotogramas por segundo (12–60)

Presiona `S` para guardar en `morph_config.json`, `Q` para salir.

### 📄 Configuración de tiempos (morph_config.json)

```json
{
  "duration": 1.4,
  "hold": 0.4,
  "fps": 60
}
```

| Campo | Descripción | Impacto |
|-------|-------------|---------|
| `duration` | Segundos de transición morfing | `duration × fps` = frames de transición |
| `hold` | Segundos estático por imagen | `hold × fps` = frames de hold |
| `fps` | Fotogramas por segundo | Calidad de movimiento y tamaño del video |

**Ejemplo con valores por defecto:**
- Hold frames: `0.4 × 60 = 24 frames`
- Transition frames: `1.4 × 60 = 84 frames`
- Frames por par: `24 + 84 = 108 frames`
- Video de 5 imágenes (sequential): `5 × 108 = 540 frames` → 9 segundos

### ⚖️ Prioridad de configuración

```
Argumentos CLI  >  morph_config.json  >  perfil (--profile)
```

Los argumentos de línea de comandos siempre tienen prioridad sobre el archivo de configuración y los perfiles.

### 🎭 Perfiles predefinidos

| Parámetro | `--profile preview` | `--profile final` |
|-----------|--------------------|--------------------|
| FPS | 24 | 30 |
| Duration | 1.0 s | 2.0 s |
| Hold | 0.5 s | 0.8 s |
| CRF | 24 | 18 |
| Preset ffmpeg | medium | slow |
| Downscale landmarks | 2× | 1× (full res) |

```bash
# Render rápido para revisar
python pipeline.py --profile preview --skip-timing

# Render de alta calidad final
python pipeline.py --profile final --skip-timing
```

---

## 🤖 Generación automática de landmarks

`auto_landmarks.py` detecta correspondencias con MediaPipe sin intervención manual:

```bash
# Genera JSONs para todas las imágenes en photos_nuevo/
# (solo una dirección A→B; el pipeline genera la inversa)
python auto_landmarks.py
```

**Características:**
- Escanea el directorio `photos_nuevo/`
- Genera pares en `landmarks_nuevo/`
- Para N imágenes: genera `C(N,2) = N(N-1)/2` archivos JSON
- Usa 30 puntos semánticos clave (nariz, ojos, cejas, boca, mandíbula)
- Omite los pares que ya existan

Tras la generación automática, se recomienda **revisar y ajustar** los pares manualmente con `review.py` para mejor calidad, especialmente en zonas de ojos, boca y contorno facial.

---

## 🔃 Auto-inversión de pares

Esta función reduce el trabajo a la mitad en modo `all-pairs`.

**Lógica:**
- Para morphing `A→B` se necesita `A_B.json`
- Para morphing `B→A` se necesita `B_A.json`
- Si tienes `A_B.json` pero no `B_A.json`, el pipeline genera automáticamente `B_A.json` en el **Paso 3.5**

**Funcionamiento interno:**
- Intercambia `image_a` ↔ `image_b`
- Intercambia `image_a_size` ↔ `image_b_size`
- Invierte todas las coordenadas: `{ a: punto_original_b, b: punto_original_a }`

**No sobrescribe:** si el archivo ya existe, no lo toca.

**Para un dataset de 5 imágenes:**
- All-pairs necesita 20 JSONs (5×4 direcciones)
- Con auto-inversión: creas 10 (una por par), el pipeline genera los otros 10

---

## 🎥 Parámetros de calidad de video

### 🔧 Parámetros clave de render

```bash
python morph.py \
  --photos photos \
  --points-dir landmarks \
  --output output/morph_final.mp4 \
  --backend tps \
  --fps 60 \
  --duration 1.4 \
  --hold 0.4 \
  --crf 18 \
  --preset slow
```

### 📊 CRF (Constant Rate Factor)

Controla la calidad del video H.264:

| CRF | Calidad | Tamaño | Uso típico |
|-----|---------|--------|-----------|
| 0 | Sin pérdida | Muy grande | Archivado de máxima calidad |
| 18 | Alta (visual sin diferencia) | Grande | **Final showcase** |
| 23 | Estándar ffmpeg | Medio | Estándar balanceado |
| 24 | Preview rápido | Pequeño | **Preview/QA** |
| 28 | Compresión media | Pequeño | Distribución web |
| 51 | Mínima | Muy pequeño | Testing extremo |

### ⚙️ Preset ffmpeg

Controla la velocidad de codificación (a igual CRF, mejor preset = mejor compresión):

```
ultrafast → superfast → veryfast → faster → fast → medium → slow → slower → veryslow
```

**Velocidad vs compresión:**
- `ultrafast` / `superfast`: 5–10 minutos (muy rápido, menor compresión)
- `medium`: 20–40 minutos (balance)
- `slow` / `veryslow`: 1–2 horas (mejor compresión, lento)

Para uso general: `medium` (preview) o `slow` (final con máxima compresión).

---

## 🔄 Backends de morphing

### TPS (Thin Plate Splines) — Recomendado ⭐

```bash
--backend tps
```

Usa correspondencias manuales/automáticas de JSONs. Produce morphing suave y controlable. Requiere archivos JSON en el directorio de landmarks.

**Factores de calidad TPS:**
- Número de puntos de correspondencia (más puntos = más control fino)
- Distribución uniforme de puntos por toda la cara
- 8 puntos ancla de borde se añaden automáticamente para estabilizar el fondo
- RBF kernel: `thin_plate_spline` (matemáticamente óptimo)
- Interpolación por frame: suavizado con easing `smoothstep`

**Recomendación:** 30–50 puntos para faces normales, 60+ para caras complejas o rasgos muy particulares.

### Delaunay

```bash
--backend delaunay
```

Triangulación de Delaunay sobre landmarks de MediaPipe. Rápido, sin JSON necesario, automático.

**Ventajas:** Sin edición manual requerida, ejecución rápida.
**Desventajas:** Menos control fino que TPS, posibles artefactos en zonas complejas.

### Optical Flow (TVL1)

```bash
--backend opticalflow [opciones]
```

Calcula flujo óptico entre imágenes. Útil cuando no hay cara clara o se necesita morphing sin correspondencias.

| Parámetro | Por defecto | Descripción |
|-----------|-------------|-------------|
| `--flow-attachment` | 15 | Fidelidad a los datos (mayor = más adherencia) |
| `--flow-tightness` | 0.3 | Regularización (mayor = más suave) |
| `--flow-max-disp` | auto (10%) | Desplazamiento máximo en píxeles |
| `--flow-smooth` | 5 | Kernel de suavizado Gaussiano |
| `--flow-no-mask` | False | Desactivar máscara facial |

---

## 📚 Referencia de argumentos CLI

### pipeline.py

```bash
python pipeline.py [opciones]

--photos DIR              Directorio de fotos de entrada        [photos]
--landmarks-dir DIR       Directorio de JSONs de correspondencia [landmarks]
--output ARCHIVO          Ruta del video de salida              [output/morph.mp4]
--mode MODE               sequential | all-pairs
--backend BACKEND         tps | delaunay | opticalflow          [tps]
--profile PERFIL          preview | final
--skip-editor             Omitir editor de landmarks
--skip-timing             Omitir editor de tiempos
--use-cache               Usar caché de landmarks en morph.py
```

### morph.py

```bash
python morph.py [opciones]

--photos DIR              Directorio de fotos                   [photos/]
--output ARCHIVO          Video de salida                       [output/morph.mp4]
--points-dir DIR          Directorio de JSONs TPS               [landmarks]
--width N                 Ancho del video                       [1080]
--height N                Alto del video                        [1920]
--fps N                   Fotogramas por segundo
--duration SEG            Duración de la transición
--hold SEG                Tiempo estático por imagen
--crf N                   Calidad H.264 (0–51)
--preset STR              Preset ffmpeg
--backend BACKEND         tps | delaunay | opticalflow          [tps]
--mode MODE               sequential | all-pairs                [sequential]
--profile PERFIL          preview | final
--order "a,b,c"           Orden manual de imágenes
--cache-landmarks         Guardar caché de landmarks en disco
--use-cache               Cargar landmarks desde caché
```

### landmark_editor.py

```bash
python landmark_editor.py [opciones]

--image-a ARCHIVO         Imagen de origen (modo par único)
--image-b ARCHIVO         Imagen de destino (modo par único)
--session JSON            Sesión de múltiples pares
--display-width N         Ancho de display por panel en píxeles (auto si no se especifica)
```

### review.py ⭐ NUEVO

```bash
python review.py [opciones]

--photos DIR              Directorio de fotos de entrada        [photos]
--landmarks-dir DIR       Directorio de JSONs de correspondencia [landmarks]
--display-width N         Ancho de display por panel en píxeles (opcional)
--filter GLOB             Filtro glob pattern para JSONs        [*.json]
```

**Ejemplos con `--filter`:**
```bash
python review.py --landmarks-dir landmarks_nuevo --filter "1_*"     # Solo pares de imagen 1
python review.py --landmarks-dir landmarks_nuevo --filter "*_3*"    # Pares donde aparece imagen 3
```

---

## 📁 Estructura del proyecto

```
face_morpher/
├── pipeline.py              # Orquestador principal (workflow completo)
├── morph.py                 # Motor de render de video
├── landmark_editor.py       # Editor interactivo de correspondencias
├── timing_editor.py         # Editor visual de tiempos (duración/hold/fps)
├── review.py                # Revisor de lotes de landmarks (NUEVO)
├── detect.py                # Detección MediaPipe de landmarks
├── warp_tps.py              # Backend TPS (Thin Plate Splines)
├── warp.py                  # Backend Delaunay
├── warp_optical_flow.py     # Backend flujo óptico
├── auto_landmarks.py        # Generación automática en batch
├── video_writer.py          # Encoder H.264 con ffmpeg
├── validate.py              # Validación de calidad de landmarks
├── morph_config.json        # Configuración de tiempos (editable)
├── requirements.txt         # Dependencias Python
├── README.md                # Este archivo (guía completa)
├── LANDMARK_EDITOR_MANUAL.md # Manual detallado del editor (referencia)
├── photos/                  # Imágenes de entrada dataset 1 (no versionado)
├── photos_nuevo/            # Imágenes de entrada dataset 2 (no versionado)
├── landmarks/               # JSONs de correspondencias dataset 1 (versionado)
├── landmarks_nuevo/         # JSONs de correspondencias dataset 2 (versionado)
├── output/                  # Videos generados (no versionado)
└── .venv/                   # Entorno virtual (no versionado)
```

---

## 🧬 Dependencias

| Librería | Versión mínima | Uso |
|----------|----------------|-----|
| `mediapipe` | 0.10.11 | Detección de landmarks faciales |
| `opencv-contrib-python` | 4.8.0 | Procesamiento de imagen y UI |
| `numpy` | 1.24.0 | Operaciones matriciales |
| `scipy` | 1.11.0 | Interpolación RBF para TPS |
| `scikit-image` | 0.21.0 | Flujo óptico TVL1 |
| `imageio-ffmpeg` | 0.4.10 | Codificación H.264 MP4 |
| `Pillow` | 10.0.0 | I/O de imágenes |

---

## 📝 Ejemplos completos

### Ejemplo 1: Crear nuevo morphing con dataset nuevo

```bash
# 1. Generar landmarks automáticamente
python auto_landmarks.py

# 2. Revisar y ajustar en lote
python review.py --photos photos_nuevo --landmarks-dir landmarks_nuevo

# 3. Render final
python pipeline.py \
  --photos photos_nuevo \
  --landmarks-dir landmarks_nuevo \
  --output output/morph_nuevo_final.mp4 \
  --mode all-pairs \
  --profile final \
  --skip-editor \
  --skip-timing
```

### Ejemplo 2: Ajuste fino de un par específico

```bash
# Revisar solo los pares de imagen 1
python review.py --landmarks-dir landmarks_nuevo --filter "1_*"

# O abrir un par específico directamente
python landmark_editor.py --image-a photos_nuevo/1.png --image-b photos_nuevo/2.png
```

### Ejemplo 3: Render rápido para QA

```bash
python pipeline.py \
  --photos photos \
  --landmarks-dir landmarks \
  --output output/morph_preview.mp4 \
  --mode sequential \
  --profile preview \
  --skip-editor \
  --skip-timing
```

---

## 🔧 Solución de problemas

| Problema | Solución |
|----------|----------|
| **Editor no carga las imágenes** | Verificar rutas en session.json o argumentos --image-a/--image-b. Usar rutas absolutas si es necesario. |
| **Puntos guardados no aparecen en el siguiente render** | Verificar que el archivo JSON se guardó (presionar `S`). Revisar que el landmarks-dir es correcto. |
| **Video sale pixelado** | Aumentar CRF (bajar de 24 a 18) o usar `--preset slow`. Revisar que los puntos de correspondencia son precisos. |
| **Render muy lento** | Reducir FPS (ej: 30 en lugar de 60), aumentar `--crf` (24 en lugar de 18), usar `--preset medium`. |
| **MediaPipe detecta mal las caras** | Revisar que las imágenes tienen cara clara y centrada. Usar `auto_landmarks.py` solo como base, luego ajustar con `review.py`. |
| **Error de permisos en PowerShell** | Ejecutar: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned` |

---

**Creado:** Mayo 2026  
**Última actualización:** Mayo 27, 2026  
**Versión:** 1.1 (con review.py, auto-inversión y manual completo)
