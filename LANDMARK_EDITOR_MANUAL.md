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
