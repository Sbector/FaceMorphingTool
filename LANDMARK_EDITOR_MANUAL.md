# Manual del Editor de Landmarks

---

## Arranque

**Modo normal** (un par de imágenes):
```bash
python landmark_editor.py --image-a photos/Hermana.jpg --image-b photos/Hermano.jpg
```

**Modo sesión** (varios pares en cadena, lo lanza el pipeline automáticamente):
```bash
python landmark_editor.py --session session.json
```

**Tamaño de ventana personalizado** (opcional):
```bash
python landmark_editor.py --session session.json --display-width 380
```

---

## Interfaz

```
┌─────────────────────────────────────────────────────────────────┐
│  [Barra de sesión — solo en modo sesión]  Par 3/15 | p=Prev n=Next │
├───────────────────────┬─┬───────────────────────┤
│                       │ │                       │
│      Imagen A         │▌│      Imagen B          │
│      (origen)         │ │      (destino)         │
│                       │ │                       │
├───────────────────────┴─┴───────────────────────┤
│  [Barra de ayuda con atajos]                    │
│  [Barra de estado: pares / zoom / cambios]      │
└─────────────────────────────────────────────────┘
```

---

## Flujo de trabajo básico

**Para crear un par de puntos:**
1. Clic izquierdo en imagen A → coloca el punto A (parpadea en amarillo)
2. Clic izquierdo en imagen B → completa el par

**Para mover un punto existente:**
1. Clic izquierdo sobre el punto (o cerca — radio 20px) → se selecciona (anillo blanco al pasar el cursor indica cuál se seleccionará)
2. Mantener pulsado y arrastrar → mueve el punto
3. Soltar → confirma la posición

**Para seleccionar sin mover:**
- Clic derecho sobre el punto → lo selecciona (naranja) sin mover

---

## Teclado

| Tecla | Acción |
|-------|--------|
| `A` | Auto-seed: coloca 30 puntos semánticos desde MediaPipe (borra los existentes) |
| `S` | Guardar al archivo JSON |
| `U` | Deshacer el último par añadido |
| `D` o `Delete` | Eliminar el par seleccionado (primero seleccionar con clic derecho) |
| `R` + `R` | Reset: borrar todos los pares (pide confirmación) |
| `L` | Recargar desde el JSON guardado (descarta cambios) |
| `Z` o `0` | Reset de zoom — vuelve a vista completa en ambos paneles |
| `N` | Siguiente par (modo sesión) — guarda si hay cambios pendientes |
| `P` | Par anterior (modo sesión) |
| `Q` | Salir |

---

## Zoom y encuadre

| Gesto | Acción |
|-------|--------|
| `Ctrl` + scroll arriba | Zoom in centrado en el cursor |
| `Ctrl` + scroll abajo | Zoom out |
| Clic botón del medio + arrastrar | Pan (desplazar la vista) |
| `Z` o `0` | Resetear zoom y pan a 1× |

- El zoom funciona de forma **independiente** en panel A y panel B
- Las coordenadas guardadas en JSON **no cambian** al hacer zoom — solo cambia la vista
- La barra de estado muestra `Zoom A:2.3× B:1.0×` cuando el zoom está activo

---

## Workflow recomendado para un par nuevo

1. Abrir el editor (vía pipeline o directamente)
2. Presionar `A` → auto-seed con 30 puntos de MediaPipe
3. Revisar visualmente que los puntos coincidan bien entre A y B
4. Hacer `Ctrl+scroll` sobre zonas problemáticas (ojos, boca, contorno) para acercar
5. Corregir puntos mal ubicados: clic izquierdo sobre el punto → arrastrar a posición correcta
6. Añadir puntos extra si se necesita más control: clic en A → clic en B
7. Presionar `S` para guardar
8. En modo sesión: presionar `N` para pasar al siguiente par

---

## Indicadores visuales

| Visual | Significado |
|--------|-------------|
| Punto **parpadeante amarillo** | Punto A colocado, esperando clic en imagen B |
| **Anillo blanco** alrededor de un punto | Ese punto se seleccionará si haces clic |
| Punto **naranja** | Punto seleccionado actualmente |
| `[*unsaved*]` en barra de estado | Hay cambios sin guardar |
| `Zoom A:2.0× B:1.0×` en estado | Vista ampliada activa |

---

---

## Configuración de tiempos y frames

Los **tiempos de transición**, **hold** y **FPS** determinan cuántos frames se generan en el vídeo. Existen múltiples formas de configurarlos:

### Conceptos principales

| Parámetro | Rango | Explicación |
|-----------|-------|-------------|
| **Duration** (Duración) | 0.1 - 10.0 s | Tiempo de transición entre dos caras (morfing) |
| **Hold** (Pausa) | 0.0 - 5.0 s | Tiempo que se mantiene la imagen estática antes de transicionar |
| **FPS** | 12 - 60 fps | Fotogramas por segundo del vídeo |
| **Frames calculados** | — | `hold_frames = hold × fps`; `transition_frames = duration × fps` |

**Ejemplo**: Con `duration=2.0s`, `hold=0.8s`, `fps=30`:
- Cada pausa ocupa: 0.8 × 30 = **24 frames**
- Cada transición ocupa: 2.0 × 30 = **60 frames**
- Cada ciclo (pausa + transición): 84 frames ≈ 2.8 segundos

---

### Método 1: UI interactiva (Timing Editor)

**Opción A - Modo normal (un par de imágenes):**
```bash
python morph.py --photos photos/ --width 1080 --height 1920
```
Se abrirá automáticamente el timing editor si la config aún no existe.

**Opción B - Modo sesión (pipeline automático):**
```bash
python pipeline.py --photos photos_nuevo --landmarks-dir landmarks_nuevo --output output/morph_nuevo.mp4
```
El pipeline te preguntará si quieres configurar los tiempos en el paso 5.

**Opción C - Lanzar el editor directamente:**
```bash
python timing_editor.py --load
```
- `--load` carga los valores existentes de `morph_config.json` (si existen)
- **Ajusta los sliders** con el ratón
- **Presiona `s`** para guardar
- **Presiona `q`** para salir

**Interfaz del timing_editor:**

```
┌──────────────────────────────────────────┐
│      Timing Configuration                │
│                                          │
│  Duration: 2.0s   [====●=======]         │
│  Hold: 0.8s       [===●========]         │
│  FPS: 30          [======●====]          │
│                                          │
│  Press 's' to Save  |  'q' to Quit       │
└──────────────────────────────────────────┘
```

---

### Método 2: Edición directa (JSON)

Si prefieres no usar GUI, edita directamente `morph_config.json`:

```json
{
  "duration": 2.0,
  "hold": 0.8,
  "fps": 30
}
```

**Guardar el archivo y usar en el siguiente render:**
```bash
python morph.py --photos photos/ --width 1080 --height 1920
# Usará automáticamente los valores de morph_config.json
```

---

### Método 3: CLI (Argumentos de línea de comandos)

Puedes sobrescribir los tiempos directamente sin editar archivos:

```bash
# Cambiar duración de transición a 3 segundos
python morph.py --photos photos/ --duration 3.0 --width 1080 --height 1920

# Cambiar hold a 1.5 segundos y FPS a 60
python morph.py --photos photos/ --hold 1.5 --fps 60 --width 1080 --height 1920

# Cambiar todos los tiempos
python morph.py --photos photos/ --duration 2.5 --hold 1.0 --fps 24 --width 1080 --height 1920
```

**Argumentos disponibles:**
```
--fps INTEGER              Frames per second (12-60)
--duration FLOAT           Transition duration in seconds (0.1-10.0)
--hold FLOAT               Static hold duration in seconds (0.0-5.0)
```

---

### Prioridad de configuración

Si especificas valores en múltiples formas, se aplica este **orden de prioridad**:

1. **CLI arguments** (máxima prioridad) → `--fps 60 --duration 2.0`
2. **morph_config.json** → valores guardados del timing editor
3. **Profile defaults** (mínima prioridad) → `preview` o `final`

**Ejemplo de precedencia:**
```bash
# morph_config.json tiene: duration=2.0, hold=0.8, fps=30
# Comando:
python morph.py --photos photos/ --fps 60 --width 1080 --height 1920

# Resultado:
# fps=60 (de CLI), duration=2.0 (de config.json), hold=0.8 (de config.json)
```

---

### Perfiles preestablecidos

**Preview** (rápido, calidad media):
```json
{
  "fps": 24,
  "duration": 1.0,
  "hold": 0.5
}
```
→ Cada transición: 24 frames (1 segundo)
→ Cada pausa: 12 frames (0.5 segundos)

**Final** (lento, máxima calidad):
```json
{
  "fps": 30,
  "duration": 2.0,
  "hold": 0.8
}
```
→ Cada transición: 60 frames (2 segundos)
→ Cada pausa: 24 frames (0.8 segundos)

---

### Ejemplos prácticos

| Objetivo | Comando |
|----------|---------|
| Vídeo rápido (6 segundos por ciclo) | `--duration 1.0 --hold 0.4 --fps 24` |
| Vídeo lento (12 segundos por ciclo) | `--duration 3.0 --hold 1.0 --fps 30` |
| Ultra fluido (60 fps) | `--fps 60 --duration 2.0 --hold 0.8` |
| Muy suave (pausa larga) | `--duration 2.0 --hold 3.0 --fps 30` |
| Cine (24 fps) | `--fps 24 --duration 2.5 --hold 1.0` |

---

## Mejoras implementadas

### Etapa 1: Bug de arrastre (CORREGIDO)
- **Problema anterior**: Al hacer clic en un punto para arrastrarlo, a veces creaba un nuevo punto en lugar de seleccionar el existente
- **Causa**: La barra de navegación desplazaba visualmente los puntos 40px hacia abajo, pero las coordenadas del mouse no se compensaban
- **Solución**: Ahora se compensa automáticamente el offset de la barra de navegación

### Etapa 2: Ventana más pequeña y adaptable
- **Antes**: Tamaño fijo de 700px por panel → demasiado grande para pantallas normales
- **Ahora**: Auto-ajusta a ~450px por panel (cabe en monitor 1080p) cuando no se especifica `--display-width`
- Puedes personalizar con `--display-width N` si lo necesitas

### Etapa 3: Zoom interactivo
- Hace zoom sin afectar las coordenadas guardadas en JSON
- Ideal para ajustar puntos con precisión en zonas complicadas (ojos, boca, mandíbula)
- Radio de detección aumentado a 20px para facilitar la selección
- Anillo blanco de hover te indica cuál es el punto más cercano antes de hacer clic
