import yaml
import requests

    # ==================== CLASES =====================

class Alumno:
    def __init__(self, nombre, codigo, mac):
        self.nombre = nombre
        self.codigo = codigo
        self.mac = mac

class Curso:
    def __init__(self, codigo, estado, nombre, alumnos=None, servidores=None):
        self.codigo = codigo
        self.estado = estado
        self.nombre = nombre
        self.alumnos = alumnos if alumnos else []
        self.servidores = servidores if servidores else []

class Servicio:
    def __init__(self, nombre, protocolo, puerto):
        self.nombre = nombre
        self.protocolo = protocolo
        self.puerto = puerto

class Servidor:
    def __init__(self, nombre, ip, servicios):
        self.nombre = nombre
        self.ip = ip
        self.servicios = servicios

# ==================== BASE DE DATOS =====================
base_datos = {
    "alumnos": [],
    "cursos": [],
    "servidores": [],
    "conexiones": []
}

# ==================== FUNCIONES API =====================

CONTROLLER_IP = "10.20.12.86"
CONTROLLER_PORT = "5800"
BASE_URL = f"http://{CONTROLLER_IP}:{CONTROLLER_PORT}"

def get_attachment_point(mac):
    url = f"{BASE_URL}/wm/device/"
    r = requests.get(url)
    if r.status_code == 200:
        devices = r.json()
        for device in devices:
            if mac.lower() in [m.lower() for m in device.get("mac", [])]:
                ap = device.get("attachmentPoint", [])
                if ap:
                    return ap[0]["switchDPID"], ap[0]["port"]
    return None

def get_route(dpid1, port1, dpid2, port2):
    url = f"{BASE_URL}/wm/topology/route/{dpid1}/{port1}/{dpid2}/{port2}/json"
    r = requests.get(url)
    if r.status_code != 200:
        return []
    path = r.json()
    if not isinstance(path, list):
        return []
    ruta = []
    for hop in path:
        if all(k in hop for k in ("src-switch", "src-port", "dst-switch", "dst-port")):
            ruta.append((hop["src-switch"], hop["src-port"]))
            ruta.append((hop["dst-switch"], hop["dst-port"]))
    return ruta

# ==================== FUNCIONES I/O =====================

def importar_archivo(nombre_archivo):
    try:
        with open(nombre_archivo, 'r') as file:
            data = yaml.safe_load(file)
            base_datos["alumnos"] = [Alumno(a["nombre"], a["codigo"], a["mac"]) for a in data.get("alumnos", [])]
            base_datos["cursos"] = [Curso(c["codigo"], c["estado"], c["nombre"], c.get("alumnos", []), c.get("servidores", [])) for c in data.get("cursos", [])]
            base_datos["servidores"] = []
            for s in data.get("servidores", []):
                servicios = [Servicio(svc["nombre"], svc["protocolo"], svc["puerto"]) for svc in s["servicios"]]
                base_datos["servidores"].append(Servidor(s["nombre"], s["ip"], servicios))
            print(f"✅ Archivo '{nombre_archivo}' importado correctamente.")
    except Exception as e:
        print(f"❌ Error al importar archivo: {e}")


def menu_conexiones():
    while True:
        print("\n🔁 SUBMENÚ - CONEXIONES")
        print("1) Crear conexión")
        print("2) Listar conexiones")
        print("3) Eliminar conexión")
        print("4) Volver al menú principal")
        subop = input(">>> ").strip()

        if subop == "1":
            print("\n📡 Crear nueva conexión")
            cod_al = input("Código de alumno: ").strip()
            alumno = next((a for a in base_datos["alumnos"] if a.codigo == cod_al), None)
            if not alumno:
                print("❌ Alumno no encontrado.")
                continue

            print("Cursos disponibles:")
            for c in base_datos["cursos"]:
                print(f"- {c.codigo} ({c.nombre})")
            cod_curso = input("Código del curso: ").strip()
            curso = next((c for c in base_datos["cursos"] if c.codigo == cod_curso), None)
            if not curso or cod_al not in curso.alumnos:
                print("❌ Curso no válido o alumno no inscrito.")
                continue

            if not curso.servidores:
                print("❌ El curso no tiene servidores asociados.")
                continue

            print("Seleccione servidor y servicio:")
            for i, nom_srv in enumerate(curso.servidores):
                srv = next((s for s in base_datos["servidores"] if s.nombre == nom_srv), None)
                if srv:
                    print(f"[{i}] {srv.nombre} - {srv.ip}")
                    for j, svc in enumerate(srv.servicios):
                        print(f"   ({j}) {svc.nombre} {svc.protocolo}/{svc.puerto}")

            try:
                idx_srv = int(input("Servidor #: "))
                srv_sel = next((s for s in base_datos["servidores"] if s.nombre == curso.servidores[idx_srv]), None)
                idx_svc = int(input("Servicio #: "))
                svc_sel = srv_sel.servicios[idx_svc]
            except:
                print("❌ Error en la selección.")
                continue

            ap_al = get_attachment_point(alumno.mac)
            ap_srv = get_attachment_point(srv_sel.ip)

            if not ap_al or not ap_srv:
                print("❌ No se pudo obtener punto de conexión.")
                continue

            ruta = get_route(ap_al[0], ap_al[1], ap_srv[0], ap_srv[1])

            if not ruta:
                print("❌ No se encontró ruta entre alumno y servidor.")
                continue

            handler = f"conn_{len(base_datos['conexiones'])+1}"
            base_datos["conexiones"].append({
                "handler": handler,
                "alumno": cod_al,
                "servidor": srv_sel.nombre,
                "servicio": svc_sel.nombre,
                "ruta": ruta
            })
            print(f"✅ Conexión '{handler}' creada.")

        elif subop == "2":
            print("\n🔗 Lista de conexiones")
            if not base_datos["conexiones"]:
                print("⚠ No hay conexiones registradas.")
            else:
                for c in base_datos["conexiones"]:
                    print(f"- Handler: {c['handler']} | Alumno: {c['alumno']} | Servidor: {c['servidor']} | Servicio: {c['servicio']}")

        elif subop == "3":
            hnd = input("Ingrese el handler de la conexión a eliminar: ").strip()
            prev = len(base_datos["conexiones"])
            base_datos["conexiones"] = [c for c in base_datos["conexiones"] if c["handler"] != hnd]
            if len(base_datos["conexiones"]) < prev:
                print("🗑️ Conexión eliminada.")
            else:
                print("❌ Conexión no encontrada.")

        elif subop == "4":
            break

        else:
            print("❌ Opción inválida.")


# ==================== MENÚ FINAL =====================

def menu():
    while True:
        print("\n" + "#" * 60)
        print("Network Policy manager de la UPSM")
        print("#" * 60)
        print("\nSeleccione una opción:\n")
        print("1) Importar")
        print("2) Exportar")
        print("3) Cursos")
        print("4) Alumnos")
        print("5) Servidores")
        print("6) Políticas")
        print("7) Conexiones")
        print("8) Salir")
        opcion = input(">>> ").strip()

        if opcion == "1":
            nombre_archivo = input("Ingrese el nombre del archivo YAML (ej. datos.yaml): ").strip()
            importar_archivo(nombre_archivo)

        elif opcion == "3":
            while True:
                print("\n📘 SUBMENÚ - CURSOS")
                print("1) Listar todos")
                print("2) Ver detalle de un curso")
                print("3) Crear nuevo curso")
                print("4) Actualizar curso (agregar/eliminar alumno)")
                print("5) Borrar curso")
                print("6) Volver al menú principal")
                subop = input(">>> ").strip()

                if subop == "1":
                    if not base_datos["cursos"]:
                        print("⚠ No hay cursos registrados.")
                    else:
                        for c in base_datos["cursos"]:
                            print(f"- {c.codigo} | {c.nombre} | Estado: {c.estado}")

                elif subop == "2":
                    cod = input("Ingrese el código del curso: ")
                    curso = next((c for c in base_datos["cursos"] if c.codigo == cod), None)
                    if curso:
                        print(f"\n📘 {curso.codigo} - {curso.nombre} [{curso.estado}]")
                        print("👥 Alumnos:")
                        for cod in curso.alumnos:
                            alumno = next((a for a in base_datos["alumnos"] if a.codigo == cod), None)
                            if alumno:
                                print(f"  - {alumno.codigo} | {alumno.nombre}")
                    else:
                        print("❌ Curso no encontrado.")

                elif subop == "3":
                    codigo = input("Código: ")
                    nombre = input("Nombre: ")
                    estado = input("Estado (ej. DICTANDO): ")
                    nuevo = Curso(codigo, estado, nombre)
                    base_datos["cursos"].append(nuevo)
                    print("✅ Curso creado.")

                elif subop == "4":
                    cod = input("Código del curso a actualizar: ")
                    curso = next((c for c in base_datos["cursos"] if c.codigo == cod), None)
                    if curso:
                        acc = input("¿Desea agregar (a) o eliminar (e) un alumno?: ").strip().lower()
                        cod_al = input("Código del alumno: ").strip()
                        if acc == "a":
                            if cod_al not in curso.alumnos:
                                curso.alumnos.append(cod_al)
                                print("✅ Alumno agregado.")
                            else:
                                print("⚠️ Ya estaba registrado.")
                        elif acc == "e":
                            if cod_al in curso.alumnos:
                                curso.alumnos.remove(cod_al)
                                print("🗑️ Alumno eliminado.")
                            else:
                                print("⚠️ Alumno no estaba registrado.")
                    else:
                        print("❌ Curso no encontrado.")

                elif subop == "5":
                    cod = input("Código del curso a eliminar: ")
                    base_datos["cursos"] = [c for c in base_datos["cursos"] if c.codigo != cod]
                    print("🗑️ Curso eliminado (si existía).")

                elif subop == "6":
                    break

                else:
                    print("❌ Opción inválida.")

        elif opcion == "5":
            print("🖥️ SERVIDORES:")
            if not base_datos["servidores"]:
                print("⚠ No hay servidores registrados.")
            else:
                for s in base_datos["servidores"]:
                    print(f"- {s.nombre} | IP: {s.ip}")
                    for svc in s.servicios:
                        print(f"   > Servicio: {svc.nombre} - {svc.protocolo}/{svc.puerto}")

        elif opcion == "7":
            menu_conexiones()

        
        elif opcion == "8":
            print("👋 Saliendo del programa.")
            break

        else:
            print("❌ Opción inválida.")

# ==================== MAIN =====================

def main():
    menu()

if __name__ == "__main__":
    main()