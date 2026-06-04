__author__ = "David Escri"
__module__ = "scripts_manager.py"
__version__ = "1.0.0"
__info__ = {"author": __author__, "module_name": __module__, "version": __version__}

import os
import re
import zlib
import random
import codecs
import argparse


# =====================================================================
# LECTOR Y ESCRITOR DE RUBY MARSHAL
# =====================================================================

class RubyMarshalReader:
    def __init__(self, data):
        self.data = data
        self.pos = 0
        self.symbols = []  # Caché para resolver referencias de símbolos (;)

    def read_byte(self):
        b = self.data[self.pos]
        self.pos += 1
        return b

    def read_bytes(self, n):
        b = self.data[self.pos:self.pos + n]
        self.pos += n
        return b

    def read_fixnum(self):
        b = self.read_byte()
        if b == 0:
            return 0
        sb = b if b < 128 else b - 256
        if 4 < sb < 128:
            return sb - 5
        if -128 <= sb < -4:
            return sb + 5

        size = abs(sb)
        val = 0
        for i in range(size):
            val |= (self.read_byte() << (8 * i))
        if sb < 0:
            val -= (1 << (8 * size))
        return val

    def read_string(self):
        b = self.read_byte()
        if b == ord('"'):
            length = self.read_fixnum()
            return self.read_bytes(length)
        elif b == ord('I'):  # IVAR (Asociado a codificación en Ruby 1.9+)
            val = self.read_object()
            num_ivars = self.read_fixnum()
            for _ in range(num_ivars):
                self.read_object()  # Nombre del atributo (símbolo o enlace)
                self.read_object()  # Valor del atributo
            return val
        elif b == ord(':'):  # Registro de nuevo Símbolo
            length = self.read_fixnum()
            sym = self.read_bytes(length)
            self.symbols.append(sym)  # Se añade al caché
            return sym
        elif b == ord(';'):  # Enlace a un Símbolo ya registrado
            index = self.read_fixnum()
            return self.symbols[index]  # Se recupera del caché
        else:
            raise ValueError(f"Tipo de string inesperado: {chr(b)} en offset {self.pos - 1}")

    def read_object(self):
        b = self.read_byte()
        if b == ord('['):
            length = self.read_fixnum()
            return [self.read_object() for _ in range(length)]
        elif b in (ord('"'), ord('I'), ord(':'), ord(';')):
            self.pos -= 1
            return self.read_string()
        elif b == ord('T'):
            return True
        elif b == ord('F'):
            return False
        elif b == ord('0'):
            return None
        elif b == ord('i'):
            return self.read_fixnum()
        else:
            raise ValueError(f"Objeto no soportado: {chr(b)} en offset {self.pos - 1}")

    def parse(self):
        magic = self.read_bytes(2)
        if magic != b'\x04\x08':
            raise ValueError("No es un archivo binario válido de Ruby Marshal (Magic bytes inválidos)")
        return self.read_object()


class RubyMarshalWriter:
    def __init__(self):
        self.data = bytearray(b'\x04\x08')

    def write_byte(self, b):
        self.data.append(b)

    def write_bytes(self, b):
        self.data.extend(b)

    def write_fixnum(self, val):
        if 0 <= val < 123:
            self.write_byte(val + 5)
        elif -123 < val < 0:
            self.write_byte((val - 5) & 0xff)
        else:
            bytes_needed = []
            if val >= 0:
                temp = val
                while temp > 0:
                    bytes_needed.append(temp & 0xff)
                    temp >>= 8
                self.write_byte(len(bytes_needed))
                self.write_bytes(bytes_needed)
            else:
                temp = val & 0xffffffff
                bytes_needed = [(temp >> (8 * i)) & 0xff for i in range(4)]
                self.write_byte(0xfc)
                self.write_bytes(bytes_needed)

    def write_string_raw(self, s_bytes):
        self.write_byte(ord('"'))
        self.write_fixnum(len(s_bytes))
        self.write_bytes(s_bytes)

    def write_object(self, obj):
        if isinstance(obj, list):
            self.write_byte(ord('['))
            self.write_fixnum(len(obj))
            for item in obj:
                self.write_object(item)
        elif isinstance(obj, bytes):
            self.write_string_raw(obj)
        elif isinstance(obj, str):
            self.write_string_raw(obj.encode('utf-8', errors='replace'))
        elif isinstance(obj, int):
            self.write_byte(ord('i'))
            self.write_fixnum(obj)
        elif obj is True:
            self.write_byte(ord('T'))
        elif obj is False:
            self.write_byte(ord('F'))
        elif obj is None:
            self.write_byte(ord('0'))
        else:
            raise ValueError(f"Tipo no soportado para escritura: {type(obj)}")

    def get_bytes(self):
        return bytes(self.data)


# =====================================================================
# AUXILIARES DE CAMBIO DE FORMATO
# =====================================================================

def title_to_filename(title):
    replacements = {
        '\\': '&bs;', '/': '&fs;', ':': '&cn;', '*': '&as;',
        '?': '&qm;', '"': '&dq;', '<': '&lt;', '>': '&gt;', '|': '&po;'
    }
    for char, repl in replacements.items():
        title = title.replace(char, repl)
    return title


def filename_to_title(filename):
    match = re.match(r'^[^_]*_(.+)$', filename)
    if match:
        title = match.group(1)
        if title.endswith('.rb'):
            title = title[:-3]
        title = title.strip()
    else:
        title = "unnamed"

    replacements = {
        '&bs;': '\\', '&fs;': '/', '&cn;': ':', '&as;': '*',
        '&qm;': '?', '&dq;': '"', '&lt;': '<', '&gt;': '>', '&po;': '|'
    }
    for repl, char in replacements.items():
        title = title.replace(repl, char)
    return title


def clear_directory(path):
    import shutil
    if os.path.exists(path):
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
            else:
                os.remove(item_path)


# =====================================================================
# OPERACIONES DE EXTRACCIÓN Y COMPRESIÓN
# =====================================================================

def dump_scripts(path="Data/Scripts", rxdata="Data/Scripts.rxdata"):
    if not os.path.exists(rxdata):
        print(f"Error: No se encontró {rxdata}")
        return

    with open(rxdata, 'rb') as f:
        data = f.read()

    reader = RubyMarshalReader(data)
    try:
        scripts = reader.parse()
    except Exception as e:
        print(f"Error al analizar rxdata: {e}")
        return

    if len(scripts) < 10:
        print("Los scripts parecen estar ya extraídos. Proceso omitido.")
        return

    if not os.path.exists(path):
        os.makedirs(path)
    else:
        clear_directory(path)

    folder_id = [1, 1]
    file_id = 1
    level = 0
    folder_path = path
    folder_name = None

    for i, e in enumerate(scripts):
        _, title_bytes, script_compressed = e
        title = title_bytes.decode('utf-8', errors='replace')

        try:
            script = zlib.decompress(script_compressed).replace(b'\r', b'')
        except Exception:
            script = b''

        title_fn = title_to_filename(title).strip()
        if not title_fn and not script:
            continue

        section_name = None
        folder_match = re.search(r'\[\[\s*(.+)\s*\]\]$', title_fn)
        if folder_match:
            section_name = folder_match.group(1).strip()
            if not section_name:
                section_name = "unnamed"

            folder_num = f"{folder_id[level]:03d}" if i < len(scripts) - 2 else "999"
            folder_name = f"{folder_num}_{section_name}"

            new_dir = os.path.join(folder_path, folder_name)
            if not os.path.exists(new_dir):
                os.makedirs(new_dir)

            folder_id[level] += 1
            if level < len(folder_id) - 1:
                level += 1
                folder_id[level] = 1
                folder_path = os.path.join(folder_path, folder_name)
                folder_name = None

            file_id = 1
        elif title_fn.startswith("====="):
            level = 0
            folder_path = path
            folder_name = None

        if not script:
            continue

        this_folder = folder_path
        if folder_name:
            this_folder = os.path.join(this_folder, folder_name)

        if not section_name:
            section_name = title_fn.strip()
        if not section_name:
            section_name = "unnamed"

        file_num = f"{file_id:03d}" if i < len(scripts) - 1 else "999"
        file_name = f"{file_num}_{section_name}.rb"

        script_file_path = os.path.join(this_folder, file_name)
        os.makedirs(os.path.dirname(script_file_path), exist_ok=True)

        with open(script_file_path, "wb") as sf:
            sf.write(script)

        file_id += 1

    # Copia de seguridad
    backup_path = rxdata.replace(".rxdata", "Backup.rxdata")
    with open(backup_path, "wb") as bf:
        bf.write(data)

    # Crear cargador local
    create_loader_scripts(rxdata)
    print("Extracción completada con éxito. Archivos guardados en:", path)


def create_loader_scripts(rxdata):
    raw_str = r"x\x9C}SM\x8F\x9B0\x10\xBDG\xCA\x7F\x18\xD8H\x8062\x9Bc\x0Fi\x0F\xDD\xB6\xea\xa9\xd5&7H\x11\x1FC\xE2.\xB1\x91m\x9AnC\xFE{m\b8t\xDB^\x80\xF9z3\xF3\xE6q\a\xDB\x03\x95Pp\x94\xC0\xB8\x82\x13\x17\xCF@KP\a\x84}zD\xD0Ad\xB9x\xA9\x15\x16\xCE|6\x9F\x15\xA8\xA3\"\xCD1K\xF3\xE7D`\xCD\x85\x9A\xCF\x00\x8C\xD9\xF9a\r\v\x87\x8C&\xC9+\xCEp\x92A0\xCD\x0Fgh3\xD5\x1A\xBF\x8E(\"\x9B\xCC\xF1\xC3\xF8\xEC\xC7\xC5}\x10_\xC2\x00\xCEntw^\xAC.;\xFD|\xFA\xB4\xD9$\x9B\xF7O\x9F\xBFn7\xD1bE\x14O\xE8.Z\xED.\xEE\xC5 t\x0F\x81\xAA\x11\xCC\xF4>\xA2\x94\xE9\x1E\xE1\x1E\xDC\x98\xC5\xCC\xD5\x1F\xB6\xF7wN\x99\xAF\xFDn0\x9F!+\x86\x95DJ%&v1\x14\x82\v\x03\xAB\xC9\xB0\x90D\xD2_\bo\xD7\xF0\xE6\xE1\xA1\x1F\xFD#\xAD\x90\xF0\x1A\x99\xEF\x8D\xC5\xA4\xE2{o\t\xDE\xC9\xD3[@[\xB6P\x92\x93\xA0\n\xFD\x85\x13\xF4\xC3B\xDF\x10\xBC\xEDPd\x98V\x9CCF\xF7\x04\xBE4\xAAn\x14P\x06SPS\x8A\x95\xC4\x1b\x88\xCEe\xF6\xB8Y\xA6\xE2i\x91\xC8\\\xD0Z\xC9\xA4\x14\xFC\x98\x94\xBC*P\xF8u\xAA\x0E\x81\xA9(\xF5\xD8RC\xAC!\xDAuv\x17\x97\xA3\xFDH\x05)\xB90\x87\xEA\x8B\xB4D\xCC&}c\x86?\x95!\xA6\x84\xF5\x1A<\xE2A\xDB\x0E\xDF\xC4\xEBSt\xB4\xA3\xA6\xA0\x02s\xC5\xC5\xCB\xBB\x0E\xC7\xDC$4\a)\x83>olM\xEAF\x1E\xFC20\x95N\x19\x85\xDFb\x12\xEE\xFA\x1C\xBB\xF1u\xF0\xDB\\\x9D\x1A\x13\x91-B:d\x1b\x1E\xC6W\x9F/\xB5H\x1Dk\x9A\xB5&\v\xE5\xBC0\xBA\xB5\xC7\x9C\xCE\xBA\x04W\xB8\xFD-uF\xDB\xA1\x10MN1\x1C3\xC3=e\xC3\x88\xF8#\xAD|\x83\xB8\x04F\xAB\xE5\xB8\xAA@\x997\b\x9B\xEE.\x1F\x06}Y-\xDC\x04\b\xC3\x93oe7\x01\x18\x8AnUi~\x1Ek/_\xFD\xA0\xC1\xA4\xD3\xDFd\xFE\x8A\xB7\xEBU,sW\x87\xE5\xAEs\\\t\xFC\xAF\xE2,\x91\x9D/\xF8S\xB2\xFF,v\x1FS\x95\x86=/\xD2\r~\x03\x01\xDDe\xDF"
    txt = codecs.escape_decode(raw_str.encode('utf-8'))[0]

    writer = RubyMarshalWriter()
    writer.write_object([[62054200, b"Main", txt]])
    with open(rxdata, "wb") as f:
        f.write(writer.get_bytes())


def aggregate_from_folder(path, scripts, level=0):
    if not os.path.exists(path):
        return

    items = os.listdir(path)
    files = []
    folders = []

    for item in items:
        if item in ('.', '..'):
            continue
        full_path = os.path.join(path, item)
        if os.path.isdir(full_path):
            if not item.startswith('.'):
                folders.append(item)
        else:
            if item.lower().endswith('.rb'):
                files.append(item)

    files.sort()
    for f in files:
        section_name = filename_to_title(f)
        file_path = os.path.join(path, f)
        with open(file_path, "rb") as sf:
            content = sf.read()

        compressed = zlib.compress(content)
        rand_id = random.randint(0, 999999)
        scripts.append([rand_id, section_name.encode('utf-8'), compressed])

    folders.sort()
    for f in folders:
        section_name = filename_to_title(f)
        if level == 0:
            scripts.append([random.randint(0, 999999), b"==================", zlib.compress(b"")])
        if level == 1:
            scripts.append([random.randint(0, 999999), b"", zlib.compress(b"")])

        folder_title = f"[[ {section_name} ]]"
        scripts.append([random.randint(0, 999999), folder_title.encode('utf-8'), zlib.compress(b"")])

        aggregate_from_folder(os.path.join(path, f), scripts, level + 1)


def combine_scripts(path="Data/Scripts", rxdata="Data/Scripts.rxdata"):
    if not os.path.exists(path):
        print(f"Error: La carpeta {path} no existe.")
        return

    scripts = []
    aggregate_from_folder(path, scripts, level=0)

    writer = RubyMarshalWriter()
    writer.write_object(scripts)

    with open(rxdata, "wb") as f:
        f.write(writer.get_bytes())
    print("Compilación completada. Archivo Scripts.rxdata actualizado.")


# =====================================================================
# MENÚ PRINCIPAL
# =====================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gestor de Scripts RPG Maker (Pokémon Essentials) en Python.")
    parser.add_argument('accion', choices=['extraer', 'combinar'], nargs='?',
                        help="Acción a realizar: 'extraer' para separar los scripts, 'combinar' para unirlos.")
    args = parser.parse_args()

    if args.accion == 'extraer':
        dump_scripts()
    elif args.accion == 'combinar':
        combine_scripts()
    else:
        print("--- GESTOR DE SCRIPTS RPG MAKER (PYTHON) ---")
        print("1. Extraer Scripts (rxdata -> archivos .rb)")
        print("2. Combinar/Compilar Scripts (archivos .rb -> rxdata)")
        opcion = input("Elige una opción (1 o 2): ").strip()

        if opcion == "1":
            dump_scripts()
        elif opcion == "2":
            combine_scripts()
        else:
            print("Opción inválida.")