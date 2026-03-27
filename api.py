"""
api.py
Simulador de Aula Multi-Agente — Servidor API
Servidor Flask que expone los datos de SQLite al dashboard en tiempo real.
Corre en paralelo con run_sesion.py.

Uso:
    python api.py                    # puerto 5000 por defecto
    python api.py --port 8080        # puerto personalizado
    python api.py --host 0.0.0.0     # accesible desde red local
"""

import json
import sqlite3
import sys
import os
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory, Response

app = Flask(__name__, static_folder=".")
DB_PATH = "data/simulador.db"


# ── UTILIDADES BD ─────────────────────────────────────────────────────────────

def query_db(sql: str, params: tuple = ()) -> list[dict]:
    """Ejecuta una consulta y devuelve lista de dicts."""
    if not Path(DB_PATH).exists():
        return []
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"DB error: {e}")
        return []


def get_ultima_sesion_id() -> str | None:
    """Obtiene el ID de la sesión más reciente."""
    sesion_file = Path("data/ultima_sesion.txt")
    if sesion_file.exists():
        sid = sesion_file.read_text().strip()
        if sid:
            return sid
    # Fallback: última sesión en BD
    rows = query_db(
        "SELECT id FROM sesiones ORDER BY created_at DESC LIMIT 1"
    )
    return rows[0]["id"] if rows else None


def cors_response(data):
    """Respuesta JSON con cabeceras CORS para acceso desde cualquier origen."""
    response = jsonify(data)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


# ── ENDPOINTS ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Sirve el dashboard principal."""
    return send_from_directory(".", "dashboard.html")


@app.route("/api/sesiones")
def listar_sesiones():
    """Lista todas las sesiones disponibles."""
    rows = query_db("""
        SELECT id, nombre, seed, estado, turno_actual, fase_actual, created_at
        FROM sesiones
        ORDER BY created_at DESC
        LIMIT 20
    """)
    return cors_response({"sesiones": rows})


@app.route("/api/sesion/actual")
def sesion_actual():
    """Devuelve el estado completo de la sesión activa."""
    sesion_id = request.args.get("id") or get_ultima_sesion_id()
    if not sesion_id:
        return cors_response({"error": "No hay sesión activa"})

    rows = query_db(
        "SELECT * FROM sesiones WHERE id = ?", (sesion_id,)
    )
    if not rows:
        return cors_response({"error": "Sesión no encontrada"})

    sesion = rows[0]
    # No devolver el JSON completo de config (muy grande)
    config = json.loads(sesion.get("config_json", "{}"))
    sesion["config_resumen"] = {
        "nombre": config.get("experimento", {}).get("nombre", ""),
        "etapa": config.get("aula", {}).get("etapa", ""),
        "materia": config.get("aula", {}).get("qs_subject", ""),
        "n_alumnos": config.get("aula", {}).get("n_alumnos", 0),
        "docente_nombre": config.get("docente", {}).get("nombre", ""),
        "estilo": config.get("docente", {}).get("estilo_predominante", ""),
        "fases": len(config.get("sesion", {}).get("fases", []))
    }
    sesion["config_json"] = sesion.get("config_json", "{}")

    return cors_response(sesion)


@app.route("/api/agentes")
def listar_agentes():
    """Devuelve todos los agentes con su estado emocional actual."""
    sesion_id = request.args.get("id") or get_ultima_sesion_id()
    if not sesion_id:
        return cors_response({"agentes": []})

    rows = query_db("""
        SELECT
            id, rol, nombre, emoji, edad,
            descripcion, perfil_especial,
            control, valor,
            autonomia, competencia, relacion,
            emocion_dominante,
            sdt_autonomia_docente, sdt_estructura_docente, sdt_implicacion_docente,
            motivacion, estres, confianza
        FROM agentes
        WHERE sesion_id = ?
        ORDER BY rol DESC, nombre
    """, (sesion_id,))

    return cors_response({
        "agentes": rows,
        "resumen_emocional": _calcular_resumen_emocional(rows)
    })


def _calcular_resumen_emocional(agentes: list[dict]) -> dict:
    """Calcula estadísticas agregadas del estado emocional."""
    alumnos = [a for a in agentes if a["rol"] == "student"]
    if not alumnos:
        return {}

    emociones = {}
    for al in alumnos:
        emo = al.get("emocion_dominante", "neutro")
        emociones[emo] = emociones.get(emo, 0) + 1

    return {
        "distribucion": emociones,
        "control_medio": round(
            sum(a.get("control", 50) for a in alumnos) / len(alumnos), 1
        ),
        "valor_medio": round(
            sum(a.get("valor", 50) for a in alumnos) / len(alumnos), 1
        ),
        "relacion_media": round(
            sum(a.get("relacion", 50) for a in alumnos) / len(alumnos), 1
        ),
        "n_alumnos": len(alumnos)
    }


@app.route("/api/chat")
def historial_chat():
    """Devuelve el historial de intervenciones (solo activos con speech)."""
    sesion_id = request.args.get("id") or get_ultima_sesion_id()
    desde_turno = int(request.args.get("desde", 0))
    limite = int(request.args.get("limite", 50))

    if not sesion_id:
        return cors_response({"turnos": []})

    rows = query_db("""
        SELECT
            t.agente_id,
            t.fase, t.turno, t.tipo_interaccion,
            a.nombre, a.rol, a.emoji, a.perfil_especial,
            t.speech, t.emotion_note,
            t.delta_control, t.delta_valor,
            t.control_post, t.valor_post, t.emocion_post,
            t.created_at, t.agente_id, a.id as agente_id_join
        FROM turnos t
        JOIN agentes a ON t.agente_id = a.id
        WHERE t.sesion_id = ?
          AND t.es_activo = 1
          AND (t.speech != '' OR t.emotion_note != '')
          AND t.turno >= ?
        ORDER BY t.fase, t.turno, a.rol DESC
        LIMIT ?
    """, (sesion_id, desde_turno, limite))

    return cors_response({
        "turnos": rows,
        "total": len(rows),
        "desde_turno": desde_turno
    })


@app.route("/api/emociones/evolucion")
def evolucion_emocional():
    """
    Devuelve la evolución del estado emocional medio de la clase
    turno a turno. Útil para el gráfico de líneas del dashboard.
    """
    sesion_id = request.args.get("id") or get_ultima_sesion_id()
    if not sesion_id:
        return cors_response({"puntos": []})

    # Calcular media por turno (solo alumnos activos)
    rows = query_db("""
        SELECT
            t.turno,
            t.fase,
            AVG(t.control_post) as control_medio,
            AVG(t.valor_post) as valor_medio,
            COUNT(*) as n_intervenciones
        FROM turnos t
        JOIN agentes a ON t.agente_id = a.id
        WHERE t.sesion_id = ?
          AND a.rol = 'student'
          AND t.es_activo = 1
        GROUP BY t.turno, t.fase
        ORDER BY t.fase, t.turno
    """, (sesion_id,))

    # Añadir distribución emocional por turno
    puntos = []
    for row in rows:
        emo_rows = query_db("""
            SELECT t.emocion_post, COUNT(*) as n
            FROM turnos t
            JOIN agentes a ON t.agente_id = a.id
            WHERE t.sesion_id = ?
              AND t.turno = ?
              AND t.fase = ?
              AND a.rol = 'student'
            GROUP BY t.emocion_post
        """, (sesion_id, row["turno"], row["fase"]))

        distribucion = {r["emocion_post"]: r["n"] for r in emo_rows}
        puntos.append({**row, "distribucion_emo": distribucion})

    return cors_response({"puntos": puntos})


@app.route("/api/docente")
def estado_docente():
    """Devuelve el estado completo del agente-docente y su perfil evolutivo."""
    sesion_id = request.args.get("id") or get_ultima_sesion_id()
    if not sesion_id:
        return cors_response({"docente": None})

    # Estado actual del docente
    docente_rows = query_db("""
        SELECT * FROM agentes
        WHERE sesion_id = ? AND rol = 'teacher'
        LIMIT 1
    """, (sesion_id,))

    if not docente_rows:
        return cors_response({"docente": None})

    docente = docente_rows[0]

    # Historial de decisiones
    decisiones = query_db("""
        SELECT
            turno, alerta_tipo, alerta_descripcion,
            propuesta_tipo, propuesta_descripcion,
            prior_sesgo, decision, modificacion,
            justificacion, emocion_docente,
            delta_sdt_json, created_at
        FROM decisiones_docente
        WHERE sesion_id = ?
        ORDER BY created_at
    """, (sesion_id,))

    # Parsear delta_sdt_json
    for d in decisiones:
        try:
            d["delta_sdt"] = json.loads(d.get("delta_sdt_json") or "{}")
        except Exception:
            d["delta_sdt"] = {}

    # Métricas del perfil (si ya se calcularon)
    perfil_rows = query_db("""
        SELECT * FROM teacher_profiles
        WHERE sesion_id = ? AND teacher_id = ?
        ORDER BY created_at DESC LIMIT 1
    """, (sesion_id, docente["id"]))

    perfil = None
    if perfil_rows:
        perfil = perfil_rows[0]
        for campo in ["sdt_initial", "sdt_emergent", "teaching_signature", "sdt_drift"]:
            try:
                perfil[campo] = json.loads(perfil.get(campo) or "{}")
            except Exception:
                perfil[campo] = {}

    # Calcular métricas en tiempo real si no hay perfil guardado
    if not perfil and decisiones:
        total = len(decisiones)
        aceptadas = sum(1 for d in decisiones if d["decision"] == "acepta")
        modificadas = sum(1 for d in decisiones if d["decision"] == "modifica")
        perfil_rt = {
            "acceptance_rate": round(aceptadas / total, 2) if total else 0,
            "modification_rate": round(modificadas / total, 2) if total else 0,
            "total_propuestas": total,
        }
    else:
        perfil_rt = None

    return cors_response({
        "docente": docente,
        "decisiones": decisiones,
        "perfil": perfil,
        "perfil_tiempo_real": perfil_rt
    })


@app.route("/api/evento", methods=["POST", "OPTIONS"])
def inyectar_evento():
    """
    Inyecta un factor externo en la sesión activa.
    El motor lo incorporará en el siguiente turno.
    """
    if request.method == "OPTIONS":
        response = Response()
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    datos = request.get_json()
    descripcion = datos.get("descripcion", "")
    sesion_id = datos.get("sesion_id") or get_ultima_sesion_id()

    if not descripcion or not sesion_id:
        return cors_response({"error": "Faltan datos"}), 400

    # Guardar el evento en un archivo temporal que el motor puede leer
    evento_path = Path("data/evento_pendiente.json")
    evento = {
        "sesion_id": sesion_id,
        "descripcion": descripcion,
        "created_at": datetime.now().isoformat()
    }
    evento_path.write_text(json.dumps(evento, ensure_ascii=False))

    print(f"\n  🎲 Evento inyectado: {descripcion}")
    return cors_response({
        "ok": True,
        "mensaje": f"Evento registrado: {descripcion}"
    })


@app.route("/api/control", methods=["POST", "OPTIONS"])
def control_simulacion():
    """
    Controla el estado de la simulación: pausa, continúa, velocidad.
    """
    if request.method == "OPTIONS":
        response = Response()
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    datos = request.get_json()
    accion = datos.get("accion", "")  # "pausa" | "continua" | "velocidad"
    valor = datos.get("valor")

    control_path = Path("data/control.json")
    control = {}
    if control_path.exists():
        try:
            control = json.loads(control_path.read_text())
        except Exception:
            pass

    if accion == "pausa":
        control["pausado"] = True
    elif accion == "continua":
        control["pausado"] = False
    elif accion == "step_off":
        control["step_mode"] = False
        control["step_advance"] = True  # avanzar el turno actual
    elif accion == "velocidad" and valor is not None:
        control["pausa_segundos"] = float(valor)

    control_path.write_text(json.dumps(control))

    return cors_response({"ok": True, "control": control})


@app.route("/api/control/estado")
def estado_control():
    """Devuelve el estado actual del control de simulación."""
    control_path = Path("data/control.json")
    if control_path.exists():
        try:
            control = json.loads(control_path.read_text())
            return cors_response(control)
        except Exception:
            pass
    return cors_response({"pausado": False, "pausa_segundos": 2.0})


@app.route("/api/metricas/sesion")
def metricas_sesion():
    """Métricas agregadas de la sesión para la vista de análisis."""
    sesion_id = request.args.get("id") or get_ultima_sesion_id()
    if not sesion_id:
        return cors_response({})

    agentes = query_db(
        "SELECT * FROM agentes WHERE sesion_id = ?", (sesion_id,)
    )
    alumnos = [a for a in agentes if a["rol"] == "student"]
    docente = next((a for a in agentes if a["rol"] == "teacher"), None)

    # Estado emocional inicial (primer turno registrado)
    emo_inicial = query_db("""
        SELECT AVG(t.control_post) as ctrl, AVG(t.valor_post) as val
        FROM turnos t
        JOIN agentes a ON t.agente_id = a.id
        WHERE t.sesion_id = ? AND a.rol = 'student' AND t.turno = 0
    """, (sesion_id,))

    # Estado emocional final
    emo_final = query_db("""
        SELECT AVG(t.control_post) as ctrl, AVG(t.valor_post) as val
        FROM turnos t
        JOIN agentes a ON t.agente_id = a.id
        WHERE t.sesion_id = ? AND a.rol = 'student'
          AND t.turno = (
            SELECT MAX(turno) FROM turnos WHERE sesion_id = ?
          )
    """, (sesion_id, sesion_id))

    # Total decisiones docente
    decisiones = query_db("""
        SELECT decision, COUNT(*) as n
        FROM decisiones_docente
        WHERE sesion_id = ?
        GROUP BY decision
    """, (sesion_id,))

    decision_summary = {d["decision"]: d["n"] for d in decisiones}
    total_decisiones = sum(decision_summary.values())

    return cors_response({
        "n_alumnos": len(alumnos),
        "docente_nombre": docente["nombre"] if docente else "",
        "emo_inicial": emo_inicial[0] if emo_inicial else {},
        "emo_final": emo_final[0] if emo_final else {},
        "delta_control": round(
            (emo_final[0]["ctrl"] or 50) - (emo_inicial[0]["ctrl"] or 50), 1
        ) if emo_inicial and emo_final else 0,
        "decision_summary": decision_summary,
        "total_decisiones": total_decisiones,
        "acceptance_rate": round(
            decision_summary.get("acepta", 0) / total_decisiones, 2
        ) if total_decisiones else 0,
    })



# ── DEMO: ARRANQUE Y CONTROL PASO A PASO ─────────────────────────────────────

import subprocess, threading

_demo_process = None

@app.route("/api/demo/start", methods=["POST","OPTIONS"])
def demo_start():
    """Lanza demo_mode.py como subprocess. No bloquea la API."""
    if request.method == "OPTIONS":
        r=Response(); r.headers["Access-Control-Allow-Origin"]="*"
        r.headers["Access-Control-Allow-Methods"]="POST,OPTIONS"
        r.headers["Access-Control-Allow-Headers"]="Content-Type"; return r

    global _demo_process
    datos = request.get_json() or {}
    pausa = float(datos.get("pausa", 3.5))
    step  = bool(datos.get("step_mode", False))

    # Matar proceso anterior si existe
    if _demo_process and _demo_process.poll() is None:
        _demo_process.terminate()

    # Escribir control.json inicial
    ctrl = {"pausado": False, "step_mode": step, "step_advance": False}
    Path("data").mkdir(exist_ok=True)
    Path("data/control.json").write_text(json.dumps(ctrl))

    # Limpiar BD anterior
    if Path("data/simulador.db").exists():
        Path("data/simulador.db").unlink()
    if Path("data/ultima_sesion.txt").exists():
        Path("data/ultima_sesion.txt").unlink()

    cmd = [sys.executable, "demo_mode.py", "--pausa", str(pausa)]
    _demo_process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    # Leer stdout en hilo para no bloquear
    def _reader(proc):
        for line in proc.stdout:
            print(f"[DEMO] {line}", end="")
    threading.Thread(target=_reader, args=(_demo_process,), daemon=True).start()

    print(f"\n  ▶ Demo arrancada (pid={_demo_process.pid}, pausa={pausa}s, step={step})")
    return cors_response({"ok": True, "pid": _demo_process.pid,
                          "step_mode": step, "pausa": pausa})


@app.route("/api/demo/step", methods=["POST","OPTIONS"])
def demo_step():
    """Avanza un turno en modo paso a paso."""
    if request.method == "OPTIONS":
        r=Response(); r.headers["Access-Control-Allow-Origin"]="*"
        r.headers["Access-Control-Allow-Methods"]="POST,OPTIONS"
        r.headers["Access-Control-Allow-Headers"]="Content-Type"; return r

    ctrl_path = Path("data/control.json")
    ctrl = {}
    if ctrl_path.exists():
        try: ctrl = json.loads(ctrl_path.read_text())
        except Exception: pass
    ctrl["step_advance"] = True
    ctrl_path.write_text(json.dumps(ctrl))
    return cors_response({"ok": True})


@app.route("/api/demo/status")
def demo_status():
    """Estado del proceso demo."""
    global _demo_process
    running = _demo_process is not None and _demo_process.poll() is None
    ctrl = {}
    try: ctrl = json.loads(Path("data/control.json").read_text())
    except Exception: pass
    return cors_response({"running": running,
                          "step_mode": ctrl.get("step_mode", False),
                          "pausado": ctrl.get("pausado", False)})


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    host = "0.0.0.0"
    port = 5000

    args = sys.argv[1:]
    if "--port" in args:
        idx = args.index("--port")
        if idx + 1 < len(args):
            port = int(args[idx + 1])
    if "--host" in args:
        idx = args.index("--host")
        if idx + 1 < len(args):
            host = args[idx + 1]

    print(f"\n{'='*50}")
    print(f"  Simulador de Aula · Dashboard API")
    print(f"  http://localhost:{port}")
    print(f"  Red local: http://TU_IP:{port}")
    print(f"{'='*50}\n")

    # Mostrar IP local para compartir en demos
    try:
        import socket
        ip = socket.gethostbyname(socket.gethostname())
        print(f"  Tu IP local: {ip}")
        print(f"  Comparte: http://{ip}:{port}\n")
    except Exception:
        pass

    app.run(host=host, port=port, debug=False, threaded=True)
