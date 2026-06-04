# RPG-Maker-Scripts-Manager
Una herramienta escrita en Python diseñada para extraer y compilar el archivo de scripts (`Scripts.rxdata`) en proyectos de RPG Maker XP (comúnmente utilizados en fangames como Pokémon Essentials). Permite la edición directa del código fuente en formato de texto plano (`.rb`) sin necesidad de tener instalado el motor de RPG Maker XP.

## Características

* **Extracción Binaria:** Convierte el archivo `Scripts.rxdata` comprimido en una estructura de carpetas ordenada con archivos Ruby individuales (`.rb`).
* **Soporte de Símbolos:** Compatible con formatos de codificación modernos y optimizaciones de serialización de Ruby Marshal (Symbol Links `;`).
* **Compilación Inversa:** Reempaqueta la carpeta de scripts modificados de vuelta al archivo binario `Scripts.rxdata` compatible con el juego.
* **Sin Dependencias Externas:** Funciona únicamente con la biblioteca estándar de Python 3.

## Requisitos

* **Python 3.x** instalado en el sistema.

## Instrucciones de Uso

### Configuración Inicial

1. Descarga el archivo `scripts_manager.py` de este repositorio.
2. Crea la carpeta `Data/` como en el repositorio.
3. Coloca el archivo `Scripts.rxdata` en la carpeta `Data/` creada previamente.

### Operaciones

Puedes interactuar con la herramienta de dos formas:

#### A. Menú Interactivo (Doble clic)
Ejecuta el archivo `scripts_manager.py` directamente haciendo doble clic sobre él. Se abrirá una interfaz de consola con las opciones principales:
* Selección `1` para extraer los scripts.
* Selección `2` para combinarlos nuevamente.

#### B. Línea de Comandos (CLI)
Abre una terminal en el directorio del proyecto y ejecuta los siguientes comandos según corresponda:

* **Para extraer los scripts:**
  ```bash
  python scripts_manager.py extraer
  ```
  Esto creará una copia de seguridad en Data/ScriptsBackup.rxdata y extraerá el código fuente en la ruta Data/Scripts/.

* **Para compilar los cambios:**
  ```bash
  python scripts_manager.py combinar
  ```
  Esto leerá la carpeta de texto plano Data/Scripts/ y regenerará el archivo binario Data/Scripts.rxdata para aplicar los cambios en el juego.

## Notas y Precauciones
* Copias de Seguridad: El script realiza automáticamente una copia del archivo original como ScriptsBackup.rxdata durante la extracción. Sin embargo, se recomienda hacer un respaldo manual externo de toda la carpeta del juego antes de realizar cambios estructurales en el código.
* Sintaxis de Ruby: Dado que los scripts modificados se guardan en formato .rb, asegúrate de respetar la sintaxis de Ruby al editar los archivos de texto para evitar fallos de ejecución al iniciar el juego.

## Licencia
Este proyecto está bajo la Licencia MIT. Consulta el archivo LICENSE para más detalles.
