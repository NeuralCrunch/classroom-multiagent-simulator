"""
genera_agentes.py
Simulador de Aula Multi-Agente — Módulo 1
Genera los perfiles de agentes (alumnos + docente) a partir del JSON de configuración.
"""

import json
import sqlite3
import asyncio
import uuid
import os
import sys
from datetime import datetime
from pathlib import Path
import anthropic

# ── CONFIGURACIÓN ────────────────────────────────────────────────────────────

DB_PATH = "data/simulador.db"
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# ── BASE DE DATOS ─────────────────────────────────────────────────────────────

def init_db():
    """Crea las tablas necesarias si no existen."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS sesiones (
            id TEXT PRIMARY KEY,
            nombre TEXT,
            seed TEXT,
            config_json TEXT,
            estado TEXT DEFAULT 'inicializada',
            turno_actual INTEGER DEFAULT 0,
            fase_actual INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS agentes (
            id TEXT PRIMARY KEY,
            sesion_id TEXT,
            rol TEXT,           -- 'teacher' | 'student'
            nombre TEXT,
            emoji TEXT,
            edad INTEGER,
            descripcion TEXT,
            perfil_especial TEXT,
            -- CVT
            control REAL,
            valor REAL,
            -- SDT
            autonomia REAL,
            competencia REAL,
            relacion REAL,
            -- Estado emocional calculado
            emocion_dominante TEXT,
            -- SDT docente (solo para rol=teacher)
            sdt_autonomia_docente REAL,
            sdt_estructura_docente REAL,
            sdt_implicacion_docente REAL,
            -- Estado emocional docente
            motivacion REAL,
            estres REAL,
            confianza REAL,
            -- Metadatos
            config_json TEXT,
            created_at TEXT,
            FOREIGN KEY (sesion_id) REFERENCES sesiones(id)
        );

        CREATE TABLE IF NOT EXISTS turnos (
            id TEXT PRIMARY KEY,
            sesion_id TEXT,
            agente_id TEXT,
            fase INTEGER,
            turno INTEGER,
            tipo_interaccion TEXT,
            speech TEXT,
            emotion_note TEXT,
            -- Deltas CVT
            delta_control REAL,
            delta_valor REAL,
            -- Deltas SDT
            delta_autonomia REAL,
            delta_competencia REAL,
            delta_relacion REAL,
            -- Estado post-turno
            control_post REAL,
            valor_post REAL,
            emocion_post TEXT,
            -- Metadatos
            es_activo INTEGER DEFAULT 1,
            created_at TEXT,
            FOREIGN KEY (sesion_id) REFERENCES sesiones(id),
            FOREIGN KEY (agente_id) REFERENCES agentes(id)
        );

        CREATE TABLE IF NOT EXISTS decisiones_docente (
            id TEXT PRIMARY KEY,
            sesion_id TEXT,
            agente_id TEXT,
            turno INTEGER,
            alerta_tipo TEXT,
            alerta_descripcion TEXT,
            propuesta_tipo TEXT,
            propuesta_descripcion TEXT,
            propuesta_fundamento TEXT,
            prior_sesgo REAL,
            decision TEXT,          -- 'acepta' | 'rechaza' | 'modifica'
            modificacion TEXT,
            justificacion TEXT,
            emocion_docente TEXT,
            delta_sdt_json TEXT,
            emo_clase_pre_json TEXT,
            emo_clase_post_json TEXT,
            created_at TEXT,
            FOREIGN KEY (sesion_id) REFERENCES sesiones(id)
        );
    """)

    conn.commit()
    conn.close()
    print("✓ Base de datos inicializada")


# ── CÁLCULO DE EMOCIÓN DOMINANTE ─────────────────────────────────────────────

def calcular_emocion_dominante(control: float, valor: float) -> str:
    """
    Calcula la emoción dominante según Control-Value Theory (Pekrun, 2006).
    Supuesto simplificador fundamentado en la dirección de los efectos (postura B).
    """
    if control >= 55 and valor >= 55:
        return "disfrute"
    elif control >= 60 and valor < 40:
        return "aburrimiento"
    elif control < 45 and valor >= 55:
        return "ansiedad"
    elif control < 35 and valor < 35:
        return "desesperanza"
    elif control >= 60:
        return "orgullo"
    else:
        return "neutro"


# ── GENERACIÓN DE AGENTES VIA LLM ─────────────────────────────────────────────

def construir_prompt_agentes(config: dict) -> str:
    """Construye el prompt para la generación de agentes."""
    aula = config["aula"]
    ctx = config["contexto"]
    doc = config["docente"]
    afecto = config["afecto_inicial"]
    cvt = afecto["cvt"]
    sdt = afecto["sdt"]

    perfiles = ", ".join(aula.get("perfiles_garantizados", [])) or "ninguno específico"

    return f"""Genera exactamente {aula['n_alumnos']} perfiles de alumnos y 1 perfil de docente para una simulación de aula con affective computing basada en Control-Value Theory (CVT, Pekrun 2006) y Self-Determination Theory (SDT, Deci & Ryan).

CONTEXTO DEL AULA:
- Etapa ISCED: {aula['etapa']} · Edad media: {aula['edad_media']} años (±2 años de variación)
- Materia QS: {aula['qs_subject']} (área: {aula['qs_area']})
- País: {ctx['pais']} · Lengua vehicular: {ctx['lengua']}
- Centro: {ctx['centro']} · Entorno: {ctx['entorno']} · NSE ESCS: {ctx['escs_quintil']}
- Diversidad funcional: {aula['nee']}
- Perfiles garantizados (deben aparecer): {perfiles}

DOCENTE:
- Nombre: {doc['nombre']} · Experiencia: {doc['experiencia']}
- Estilo pedagógico: {doc['framework_pedagogico']} → {doc['estilo_predominante']}
- Descripción: {doc.get('descripcion', '')}
- SDT: autonomía={doc['sdt']['autonomia']}, estructura={doc['sdt']['estructura']}, implicación={doc['sdt']['implicacion']}

DISTRIBUCIÓN AFECTIVA INICIAL DE LA CLASE (CVT+SDT):
- Control percibido medio: {cvt['control_medio']}/100 (varianza: {cvt['varianza']})
- Valor percibido medio: {cvt['valor_medio']}/100
- Autonomía SDT media: {sdt['autonomia_media']}/100
- Competencia SDT media: {sdt['competencia_media']}/100
- Relación social media: {sdt['relacion_media']}/100
- Cohesión grupal: {sdt['cohesion']}/100

INSTRUCCIONES:
- Los nombres deben ser verosímiles para el país/lengua indicados
- Incluye diversidad de géneros y perfiles socioeconómicos
- Los valores afectivos deben seguir distribución realista con la varianza indicada
- Los perfiles garantizados DEBEN estar presentes con sus características específicas
- La descripción debe incluir detalles contextuales realistas (familia, relación con la materia, comportamiento en clase)

Responde ÚNICAMENTE con JSON válido sin markdown ni comentarios:
{{
  "docente": {{
    "nombre": "string",
    "emoji": "un emoji que represente visualmente al docente",
    "edad": número,
    "descripcion": "3 frases de perfil narrativo realista y contextualizado",
    "sdt_autonomia": número 0-100,
    "sdt_estructura": número 0-100,
    "sdt_implicacion": número 0-100,
    "motivacion": número 0-100,
    "estres": número 0-100,
    "confianza": número 0-100
  }},
  "alumnos": [
    {{
      "nombre": "string",
      "emoji": "un emoji que represente al alumno",
      "edad": número entre {aula['edad_media']-2} y {aula['edad_media']+2},
      "descripcion": "2-3 frases: personalidad, contexto familiar breve, relación con la materia",
      "perfil_especial": "string con el perfil especial o 'ninguno'",
      "control": número 0-100,
      "valor": número 0-100,
      "autonomia": número 0-100,
      "competencia": número 0-100,
      "relacion": número 0-100
    }}
  ]
}}"""


def guardar_agentes(sesion_id: str, data: dict, config: dict) -> list:
    """Guarda los agentes generados en SQLite y devuelve la lista de agentes."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    ahora = datetime.now().isoformat()
    agentes = []

    # Guardar docente
    doc_raw = data["docente"]
    doc_id = str(uuid.uuid4())
    emocion_doc = "neutro"  # El docente empieza en estado neutro por defecto

    c.execute("""
        INSERT INTO agentes VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?
        )
    """, (
        doc_id, sesion_id, "teacher",
        doc_raw["nombre"], doc_raw["emoji"], doc_raw.get("edad", 38),
        doc_raw["descripcion"], "ninguno",
        # CVT (docente usa sus propias métricas)
        float(doc_raw.get("motivacion", 65)),
        float(doc_raw.get("confianza", 68)),
        # SDT del docente como alumno (no aplica, ponemos 0)
        float(doc_raw.get("sdt_autonomia", 50)),
        float(doc_raw.get("sdt_estructura", 65)),
        float(doc_raw.get("sdt_implicacion", 60)),
        emocion_doc,
        # SDT docente
        float(doc_raw.get("sdt_autonomia", 50)),
        float(doc_raw.get("sdt_estructura", 65)),
        float(doc_raw.get("sdt_implicacion", 60)),
        # Estado emocional docente
        float(doc_raw.get("motivacion", 65)),
        float(doc_raw.get("estres", 40)),
        float(doc_raw.get("confianza", 68)),
        json.dumps(doc_raw), ahora
    ))

    agentes.append({
        "id": doc_id,
        "rol": "teacher",
        "nombre": doc_raw["nombre"],
        "emoji": doc_raw["emoji"],
        "descripcion": doc_raw["descripcion"]
    })
    print(f"  👩‍🏫 {doc_raw['nombre']} · estilo {config['docente']['estilo_predominante']}")

    # Guardar alumnos
    for alumno in data["alumnos"]:
        al_id = str(uuid.uuid4())
        control = float(alumno.get("control", 50))
        valor = float(alumno.get("valor", 50))
        emocion = calcular_emocion_dominante(control, valor)

        c.execute("""
            INSERT INTO agentes VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?
            )
        """, (
            al_id, sesion_id, "student",
            alumno["nombre"], alumno["emoji"], alumno.get("edad", 14),
            alumno["descripcion"], alumno.get("perfil_especial", "ninguno"),
            control, valor,
            float(alumno.get("autonomia", 50)),
            float(alumno.get("competencia", 50)),
            float(alumno.get("relacion", 50)),
            emocion,
            None, None, None,  # SDT docente no aplica
            None, None, None,  # Estado emocional docente no aplica
            json.dumps(alumno), ahora
        ))

        agentes.append({
            "id": al_id,
            "rol": "student",
            "nombre": alumno["nombre"],
            "emoji": alumno["emoji"],
            "edad": alumno.get("edad", 14),
            "emocion": emocion,
            "control": control,
            "valor": valor,
            "perfil_especial": alumno.get("perfil_especial", "ninguno")
        })

        especial = f" ⚑ {alumno['perfil_especial']}" if alumno.get("perfil_especial", "ninguno") != "ninguno" else ""
        print(f"  {alumno['emoji']} {alumno['nombre']} ({alumno.get('edad', 14)}a) · {emocion}{especial}")

    conn.commit()
    conn.close()
    return agentes


# ── FUNCIÓN PRINCIPAL ─────────────────────────────────────────────────────────

async def generar_agentes(config_path: str) -> tuple[str, list]:
    """
    Función principal. Carga la config, crea la sesión en BD,
    genera los agentes con el LLM y los guarda.
    Devuelve (sesion_id, lista_agentes).
    """
    # Cargar configuración
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    print(f"\n{'='*60}")
    print(f"  Simulador de Aula Multi-Agente")
    print(f"  Módulo 1: Generación de agentes")
    print(f"{'='*60}")
    print(f"  Experimento: {config['experimento']['nombre']}")
    print(f"  Etapa: {config['aula']['etapa']} · Materia: {config['aula']['qs_subject']}")
    print(f"  Alumnos: {config['aula']['n_alumnos']} · Docente: {config['docente']['nombre']}")
    print(f"{'='*60}\n")

    # Inicializar BD
    Path("data").mkdir(exist_ok=True)
    init_db()

    # Crear sesión en BD
    sesion_id = str(uuid.uuid4())
    ahora = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO sesiones (id, nombre, seed, config_json, estado, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        sesion_id,
        config["experimento"]["nombre"],
        config["experimento"]["seed"],
        json.dumps(config),
        "generando_agentes",
        ahora, ahora
    ))
    conn.commit()
    conn.close()
    print(f"✓ Sesión creada: {sesion_id[:8]}...")

    # Generar agentes con LLM
    print(f"\n⟳ Llamando a la API para generar {config['aula']['n_alumnos']} alumnos + 1 docente...")
    prompt = construir_prompt_agentes(config)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    text = response.content[0].text.strip()

    # Limpiar posibles backticks de markdown
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"\n✗ Error al parsear JSON: {e}")
        print(f"Respuesta recibida:\n{text[:500]}...")
        raise

    n_alumnos = len(data.get("alumnos", []))
    print(f"✓ API respondió: {n_alumnos} alumnos + 1 docente\n")

    # Guardar en BD
    print("Agentes generados:")
    agentes = guardar_agentes(sesion_id, data, config)

    # Actualizar estado de sesión
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        UPDATE sesiones SET estado = 'agentes_listos', updated_at = ?
        WHERE id = ?
    """, (datetime.now().isoformat(), sesion_id))
    conn.commit()
    conn.close()

    # Resumen
    emociones = {}
    for ag in agentes:
        if ag["rol"] == "student":
            emo = ag.get("emocion", "neutro")
            emociones[emo] = emociones.get(emo, 0) + 1

    print(f"\n{'='*60}")
    print(f"  ✓ {len(agentes)} agentes guardados en base de datos")
    print(f"  Distribución emocional inicial:")
    for emo, n in sorted(emociones.items(), key=lambda x: -x[1]):
        barra = "█" * n
        print(f"    {emo:<15} {barra} ({n})")
    print(f"\n  Sesión ID: {sesion_id}")
    print(f"  Guarda este ID para continuar con motor.py")
    print(f"{'='*60}\n")

    # Guardar sesion_id en archivo para uso posterior
    with open("data/ultima_sesion.txt", "w") as f:
        f.write(sesion_id)

    return sesion_id, agentes


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config/experimento_01.json"

    if not Path(config_path).exists():
        print(f"✗ No se encuentra el archivo de configuración: {config_path}")
        sys.exit(1)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("✗ Falta la variable de entorno ANTHROPIC_API_KEY")
        print("  Ejecuta: export ANTHROPIC_API_KEY='sk-ant-...'")
        sys.exit(1)

    sesion_id, agentes = asyncio.run(generar_agentes(config_path))
