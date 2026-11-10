# Curry Launcher — CLAUDE.md

Guía de contexto para cualquier Claude que trabaje en este repo. Léela completa antes de tocar código.

## Qué es esto
Launcher personalizado para Roblox, hecho en Java. Permite lanzar el juego con
configuraciones guardadas (cuenta, resolución, flags de lanzamiento, etc.) desde
una interfaz propia en vez del launcher oficial.

## Quiénes trabajan aquí
- Eduardo (Brandon Eduardo Sustaita Ramos) — repo owner.
- Su compañero (por confirmar usuario de GitHub) — colaborador.

## Arquitectura (mientras crece el proyecto)
- `src/main/java/com/curry/launcher/core/`   → lógica de lanzamiento, procesos, detección de Roblox instalado
- `src/main/java/com/curry/launcher/ui/`     → interfaz (Swing/JavaFX, por decidir)
- `src/main/java/com/curry/launcher/config/` → manejo de configuración (perfiles, JSON/propiedades)
- `src/main/resources/`                      → iconos, assets, archivos de config por defecto

Si agregan un módulo nuevo, créenlo como paquete dentro de `com.curry.launcher`
y documéntenlo aquí mismo en una línea.

## Convenciones de código (Java)
- Encabezado de clase al inicio del archivo (después del `package`, antes de los `import`):
  ```java
  /**
   * Clase: NombreDeLaClase
   * Descripción: qué hace esta clase.
   *
   * Métodos:
   *  - metodoUno(int param): qué hace
   *  - metodoDos(String param): qué hace
   *
   * @author Brandon Eduardo Sustaita
   * @version 1.0
   * @date AAAA-MM-DD
   */
  ```
- Cada método debe tener su Javadoc.
- Scanner para entrada de usuario se llama `teclado`.
- Para imprimir: un solo `print` con `\n` al final, en vez de `println`.

## Ramas
- `main` — estable, solo se mergea vía PR.
- `dev` — integración de features.
- `feature/<nombre>` — una rama por feature/persona, ej. `feature/ui-eduardo`.

## Flujo de trabajo sugerido
1. Crear rama desde `dev`: `git checkout -b feature/lo-que-sea dev`
2. Commits chicos y descriptivos.
3. Push y abrir PR hacia `dev`.
4. Cuando `dev` esté estable, PR de `dev` → `main`.

## Estado actual
- Estructura base creada (sin lógica todavía). Pendiente: decidir UI (Swing vs JavaFX),
  cómo detectar la instalación de Roblox, y el formato de los perfiles de configuración.
