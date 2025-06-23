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


class Conexion:
    def __init__(self, handler, alumno, servidor, servicio):
        self.handler = handler
        self.alumno = alumno
        self.servidor = servidor
        self.servicio = servicio


# ==================== BASE DE DATOS =====================
base_datos = {
    "alumnos": [],
    "cursos": [],
    "servidores": [],
    "conexiones": []
}

# ==================== FUNCIONES API =====================

CONTROLLER_IP = "10.20.12.86"
CONTROLLER_PORT = "8080"
BASE_URL = f"http://{CONTROLLER_IP}:{CONTROLLER_PORT}"


def get_attachment_points(mac_address):
    if mac_address is None:
        print("❌ La dirección MAC proporcionada es None.")
        return None, None

    url = f"{BASE_URL}/wm/device/"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        for host in data:
            if mac_address.lower() in [m.lower() for m in host.get("mac", []) if m]:
                aps = host.get("attachmentPoint", [])
                if aps:
                    punto = aps[0]
                    return punto["switchDPID"], punto["port"]
                else:
                    print(f"⚠️ La MAC {mac_address} no tiene attachmentPoint.")
        print(f"⚠️ La MAC {mac_address} no fue encontrada.")
    else:
        print(f"[{response.status_code}] Error al obtener dispositivos.")
        print(f"Respuesta: {response.text}")
    
    return None, None

def get_route(src_dpid, src_port, dst_dpid, dst_port):
    url = f"{BASE_URL}/wm/topology/route/{src_dpid}/{src_port}/{dst_dpid}/{dst_port}/json"
    print(f"Obteniendo ruta de {src_dpid}:{src_port} a {dst_dpid}:{dst_port}...")
    response = requests.get(url)
    if response.status_code == 200:
        ruta = response.json()
        return [(hop["switch"], hop["port"]["portNumber"]) for hop in ruta]
    return []

def procesar_ruta(route):
    hops_procesados = []
    for i in range(0, len(route) - 1, 2):
        dpid = route[i][0]
        in_port = route[i][1]
        out_port = route[i + 1][1]
        hops_procesados.append((dpid, in_port, out_port))
    return hops_procesados

def build_route(route, alumno, servidor, servicio, handler):
    protocolo = servicio.protocolo.lower()
    puerto = servicio.puerto
    mac_src = alumno.mac
    ip_dst = servidor.ip
    mac_dst = get_mac_from_ip(ip_dst)
    print(f"MAC destino para {ip_dst}: {mac_dst}")

    ip_proto = "0x06" if protocolo == "tcp" else "0x11"
    hops = procesar_ruta(route)

    for i, (dpid, in_port, out_port) in enumerate(hops):
        # Ida: host -> servidor
        flow_fwd = {
            "switch": dpid,
            "name": f"{handler}_fwd_{i}",
            "priority": "100",
            "eth_type": "0x0800",
            "ipv4_dst": ip_dst,
            "eth_src": mac_src,
            "ip_proto": ip_proto,
            "tp_dst": str(puerto),
            "in_port": in_port,
            "active": "true",
            "actions": f"output={out_port}"
        }

        # Retorno: servidor -> host
        flow_rev = {
            "switch": dpid,
            "name": f"{handler}_rev_{i}",
            "priority": "100",
            "eth_type": "0x0800",
            "ipv4_src": ip_dst,
            "eth_dst": mac_src,
            "ip_proto": ip_proto,
            "tp_src": str(puerto),
            "in_port": out_port,
            "active": "true",
            "actions": f"output={in_port}"
        }

        # Eliminar ARP anterior
        requests.delete(f"{BASE_URL}/wm/staticflowpusher/json", json={"name": f"{handler}_arp_{i}"})

        # ARP
        flow_arp = {
            "switch": dpid,
            "name": f"{handler}_arp_{i}",
            "priority": "300",
            "eth_type": "0x0806",
            "active": "true",
            "actions": "normal"
        }

        # Instalar todos
        for flow in [flow_fwd, flow_rev, flow_arp]:
            r = requests.post(f"{BASE_URL}/wm/staticflowpusher/json", json=flow)
            if r.status_code != 200:
                print(f"❌ Error al instalar flow {flow['name']} en {dpid}: {r.status_code} - {r.text}")
            else:
                print(f"✅ Flow {flow['name']} instalado correctamente en {dpid}")





def get_mac_from_ip(ip_destino):
    url = f"{BASE_URL}/wm/device/"
    response = requests.get(url)
    if response.status_code == 200:
        devices = response.json()
        for device in devices:
            if ip_destino in device.get("ipv4", []):
                return device.get("mac", [])[0]
    return None


def menuConexiones():
    while True:
        print("\n--- GESTIÓN DE CONEXIONES ---")
        print("1) Crear conexión")
        print("2) Listar conexiones")
        print("3) Borrar conexión")
        print("4) Volver al menú principal")

        opcion = input(">>> ").strip()

        if opcion == "1":
            cod_alumno = input("Código del alumno: ").strip()
            nombre_servidor = input("Nombre del servidor: ").strip()
            nombre_servicio = input("Servicio a usar (ej. ssh): ").lower().strip()
            
            alumno = next((a for a in base_datos["alumnos"] if str(a.codigo) == cod_alumno), None)
            servidor = next((s for s in base_datos["servidores"] if s.nombre == nombre_servidor), None)

            if not alumno or not servidor:
                print("❌ Alumno o servidor no encontrado.")
                continue

            autorizado = False
            for curso in base_datos["cursos"]:
                if curso.estado == "DICTANDO" and int(cod_alumno) in curso.alumnos:
                    for srv in curso.servidores:
                        if srv["nombre"] == nombre_servidor and nombre_servicio in srv["servicios_permitidos"]:
                            autorizado = True
                            break
            if not autorizado:
                print("Alumno NO autorizado.")
                continue

            servicio = next((s for s in servidor.servicios if s.nombre.lower() == nombre_servicio), None)
            if not servicio:
                print("Servicio no encontrado.")
                continue

            ap1 = get_attachment_points(alumno.mac)
            ap2 = get_attachment_points(get_mac_from_ip(servidor.ip))
            if not ap1 or not ap2:
                print("No se pudieron obtener puntos de conexión.")
                continue

            ruta = get_route(ap1[0], ap1[1], ap2[0], ap2[1])
            
            if not ruta:
                print("Ruta no encontrada.")
            else:
                print(f"Ruta: {ruta}")
                

            handler = f"{alumno.codigo}_{servidor.nombre}_{servicio.nombre}"
            build_route(ruta, alumno, servidor, servicio, handler)
            """
            dpid_origen, _ = ruta[0]
            arp_flow = {
                "switch": dpid_origen,
                "name": f"{handler}_arp_flood",
                "priority": "32768",
                "eth_type": "0x0806",
                "active": "true",
                "actions": "FLOOD"
            }
            requests.post(f"{BASE_URL}/wm/staticflowpusher/json", json=arp_flow)
            """

            

            base_datos["conexiones"].append(Conexion(handler, alumno, servidor, servicio))
            print(f"Conexión creada con handler: {handler}")

        elif opcion == "2":
            if not base_datos["conexiones"]:
                print("📭 No hay conexiones registradas.")
            else:
                for c in base_datos["conexiones"]:
                    print(f"- Handler: {c.handler} | Alumno: {c.alumno.nombre} | Servidor: {c.servidor.nombre} | Servicio: {c.servicio.nombre}")

        elif opcion == "3":
            handler = input("Ingrese handler a eliminar: ")
            conexion = next((c for c in base_datos["conexiones"] if c.handler == handler), None)
            if not conexion:
                print("Conexión no encontrada.")
                continue

            for i in range(0, 10):
                for suf in ["_fwd_", "_rev_"]:
                    nombre_flow = f"{handler}{suf}{i}"
                    requests.delete(f"{BASE_URL}/wm/staticflowpusher/json", json={"name": nombre_flow})

            base_datos["conexiones"].remove(conexion)
            print("Conexión eliminada correctamente.")

        elif opcion == "4":
            break
        else:
            print("Opción inválida.")

def opcion1():
    nombre_archivo = input("Ingrese el nombre del archivo YAML (ej. datos.yaml): ").strip()
    importar_archivo(nombre_archivo)

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
            print(f" Archivo '{nombre_archivo}' importado correctamente.")
    except Exception as e:
        print(f" Error al importar archivo: {e}")


def opcion2():
    nombre_archivo = input("Ingrese el nombre del archivo YAML a exportar (ej. salida.yaml): ").strip()
    exportar_archivo(nombre_archivo)    

def exportar_archivo(nombre_archivo):
    try:
        data = {
            "alumnos": [
                {"nombre": a.nombre, "codigo": a.codigo, "mac": a.mac}
                for a in base_datos["alumnos"]
            ],
            "cursos": [
                {
                    "codigo": c.codigo,
                    "estado": c.estado,
                    "nombre": c.nombre,
                    "alumnos": c.alumnos,
                    "servidores": c.servidores,
                }
                for c in base_datos["cursos"]
            ],
            "servidores": [
                {
                    "nombre": s.nombre,
                    "ip": s.ip,
                    "servicios": [
                        {
                            "nombre": svc.nombre,
                            "protocolo": svc.protocolo,
                            "puerto": svc.puerto
                        }
                        for svc in s.servicios
                    ]
                }
                for s in base_datos["servidores"]
            ]
        }
        with open(nombre_archivo, 'w') as file:
            yaml.dump(data, file)
        print(f"Archivo '{nombre_archivo}' exportado correctamente.")
    except Exception as e:
        print(f"Error al exportar archivo: {e}")


# ==================== MENÚ PRINCIPAL =====================

def menu():
    while True:
        print("\n" + "#" * 40)
        print("Network Policy manager de la UPSM")
        print("#" * 40)
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
            opcion1()

        elif opcion == "2":
            opcion2() 

        elif opcion == "3":
            while True:
                print("\n SUBMENÚ - CURSOS")
                print("1) Listar todos")
                print("2) Ver detalle de un curso")
                print("3) Crear nuevo curso")
                print("4) Actualizar curso (agregar/eliminar alumno)")
                print("5) Borrar curso")
                print("6) Volver al menú principal")
                subop = input(">>> ").strip()

                if subop == "1":
                    if not base_datos["cursos"]:
                        print("No hay cursos registrados.")
                    else:
                        for c in base_datos["cursos"]:
                            print(f"- {c.codigo} | {c.nombre} | Estado: {c.estado}")

                elif subop == "2":
                    cod = input("Ingrese el código del curso: ").upper()
                    curso = next((c for c in base_datos["cursos"] if c.codigo == cod), None)
                    if curso:
                        print(f"\n{curso.codigo} - {curso.nombre} [{curso.estado}]")
                        print("Alumnos:")
                        for cod in curso.alumnos:
                            alumno = next((a for a in base_datos["alumnos"] if a.codigo == cod), None)
                            if alumno:
                                print(f"  - {alumno.codigo} | {alumno.nombre}")
                    else:
                        print("Curso no encontrado.")

                elif subop == "3":
                    codigo = input("Código: ").upper()
                    nombre = input("Nombre: ")
                    estado = input("Estado (ejemplo: DICTANDO o INACTIVO): ")
                    nuevo = Curso(codigo, estado, nombre)
                    base_datos["cursos"].append(nuevo)
                    print("Curso creado.")

                elif subop == "4":
                    cod = input("Código del curso a actualizar: ").upper()
                    curso = next((c for c in base_datos["cursos"] if c.codigo == cod), None)
                    if curso:
                        acc = input("¿Desea agregar (a) o eliminar (e) un alumno?: ").strip().lower()
                        cod_al = input("Código del alumno: ").strip()

                        # Validar que el alumno exista
                        alumno_existe = any(a.codigo == int(cod_al) for a in base_datos["alumnos"])

                        if not alumno_existe:
                            print("Alumno no encontrado.")
                        else:
                            if acc == "a":
                                if int(cod_al) not in curso.alumnos:
                                    curso.alumnos.append(int(cod_al))
                                    #print(type(curso.alumnos), curso.alumnos)
                                    print("Alumno agregado.")
                                else:
                                    print("Ya estaba registrado.")
                            elif acc == "e":
                                #print(curso.alumnos)
                                if int(cod_al) in curso.alumnos:
                                    curso.alumnos.remove(int(cod_al))
                                    print("Alumno eliminado.")
                                else:
                                    print("Alumno no estaba registrado.")
                    else:
                        print("Curso no encontrado.")

                elif subop == "5":
                    cod = input("Código del curso a eliminar: ").upper()

                    #print(cod)
                    #print(base_datos["cursos"])

                    if not any(c.codigo == cod for c in base_datos["cursos"]):
                        print("Curso no encontrado.")
                    else:   
                        base_datos["cursos"] = [c for c in base_datos["cursos"] if c.codigo != cod]
                        print("Curso eliminado ")
                    

                elif subop == "6":
                    break

                else:
                    print("Opción inválida.")

        elif opcion == "4":
            while True:
                print("\nSUBMENÚ - ALUMNOS")
                print("1) Listar todos")
                print("2) Ver detalle")
                print("3) Crear nuevo alumno")
                #print("4) Borrar alumno")
                print("4) Volver al menú principal")
                subop = input(">>> ").strip()

                if subop == "1":
                    if not base_datos["alumnos"]:
                        print("No hay alumnos registrados.")
                    else:
                        for a in base_datos["alumnos"]:
                            print(f"- {a.codigo} | {a.nombre} | MAC: {a.mac}")

                elif subop == "2":
                    cod = input("Ingrese el código del alumno: ").strip()
                    alumno = next((a for a in base_datos["alumnos"] if a.codigo == int(cod)), None)
                    if alumno:
                        print(f"Código: {alumno.codigo}")
                        print(f"Nombre: {alumno.nombre}")
                        print(f"MAC: {alumno.mac}")
                    else:
                        print("Alumno no encontrado.")
                
                elif subop == "3":
                    try:
                        nombre = input("Nombre del alumno: ").strip()
                        codigo = int(input("Código del alumno: ").strip())
                        mac = input("MAC del alumno (formato XX:XX:XX:XX:XX:XX): ").strip()

                        if any(a.codigo == codigo for a in base_datos["alumnos"]):
                            print("Ya existe un alumno con ese código.")
                        else:
                            nuevo = Alumno(nombre, codigo, mac)
                            base_datos["alumnos"].append(nuevo)
                            print(f"Alumno '{nombre}' registrado correctamente.")
                    except Exception as e:
                        print(f"Error al registrar alumno: {e}")

                elif subop == "4":
                    break
                else:
                    print("Opción inválida.")
   
        elif opcion == "5":
            while True:
                print("\nSUBMENÚ - SERVIDORES")
                print("1) Listar servidores")
                print("2) Ver detalle")
                print("3) Volver al menú principal")
                subop = input(">>> ").strip()

                if subop == "1":
                    if not base_datos["servidores"]:
                        print("No hay servidores registrados.")
                    else:
                        for s in base_datos["servidores"]:
                            print(f"- {s.nombre} | IP: {s.ip}")
                            

                elif subop == "2":
                    ipServidor = input("Ingrese la IP del servidor: ").strip()
                    server = next((a for a in base_datos["servidores"] if a.ip == ipServidor), None)
                    if server:
                        for servicio in s.servicios:
                                print(f"   > Servicio: {servicio.nombre} - {servicio.protocolo}/{servicio.puerto}")
                    else:
                        print("Servidor no encontrado.")
                
                elif subop == "3":
                    break

                else:
                    print("Opción inválida.")            
            

        elif opcion == "7":
            menuConexiones()

        
        elif opcion == "8":
            print("Saliendo del programa.")
            break

        else:
            print("Opción inválida.")

# ==================== MAIN =====================

def main():
    menu()

if __name__ == "__main__":
    main()