"""
docente.py
Simulador de Aula Multi-Agente — Módulo 3
Sistema afectivo externo: detecta alertas emocionales, genera propuestas XAI
y gestiona la decisión del agente-docente con sesgos pedagógicos.
Actualiza el perfil evolutivo del docente tras cada decisión.
"""

import json
import sqlite3
import uuid
import os
from datetime import datetime
from pathlib import Path
import anthropic

# ── CONFIGURACIÓN ─────────────────────────────────────────────────────────────

DB_PATH = "data/simulador.db"
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# ── UMBRALES DE ALERTA ────────────────────────────────────────────────────────
# Supuestos simplificadores basados en CVT (postura B metodológica)

UMBRALES_ALERTA = {
    "ansiedad_alta":       {"control_max": 35, "valor_min": 60, "n_min": 2},
    "desesperanza":        {"control_max": 30, "valor_max": 35, "n_min": 1},
    "aburrimiento_grupal": {"control_min": 60, "valor_max": 35, "n_min": 3},
    "desenganche":         {"control_max": 40, "valor_max": 40, "n_min": 3},
    "tension_social":      {"relacion_max": 30, "n_min": 2},
}

# ── MATRIZ DE SESGOS PEDAGÓGICOS ──────────────────────────────────────────────
# Prior de aceptación (0–100) por estilo docente × tipo de propuesta
# Fundamentado en SDT Teaching Style (Reeve, 2009) y Grasha (1996) — postura B

SESGOS = {
    "Controlador": {
        "aumentar_autonomia":      20,
        "aumentar_estructura":     85,
        "trabajo_cooperativo":     35,
        "reducir_ritmo":           30,
        "atencion_individual":     55,
        "cambiar_actividad":       20,
        "feedback_emocional":      25,
        "coevaluacion":            28,
    },
    "Estructurado-autónomo": {
        "aumentar_autonomia":      55,
        "aumentar_estructura":     90,
        "trabajo_cooperativo":     65,
        "reducir_ritmo":           60,
        "atencion_individual":     78,
        "cambiar_actividad":       45,
        "feedback_emocional":      55,
        "coevaluacion":            58,
    },
    "Autónomo-de-apoyo": {
        "aumentar_autonomia":      85,
        "aumentar_estructura":     60,
        "trabajo_cooperativo":     80,
        "reducir_ritmo":           75,
        "atencion_individual":     82,
        "cambiar_actividad":       65,
        "feedback_emocional":      78,
        "coevaluacion":            80,
    },
    "Experto": {
        "aumentar_autonomia":      30,
        "aumentar_estructura":     80,
        "trabajo_cooperativo":     40,
        "reducir_ritmo":           35,
        "atencion_individual":     60,
        "cambiar_actividad":       25,
        "feedback_emocional":      30,
        "coevaluacion":            35,
    },
    "Autoridad formal": {
        "aumentar_autonomia":      25,
        "aumentar_estructura":     88,
        "trabajo_cooperativo":     38,
        "reducir_ritmo":           32,
        "atencion_individual":     58,
        "cambiar_actividad":       22,
        "feedback_emocional":      28,
        "coevaluacion":            30,
    },
    "Facilitador": {
        "aumentar_autonomia":      90,
        "aumentar_estructura":     50,
        "trabajo_cooperativo":     88,
        "reducir_ritmo":           80,
        "atencion_individual":     90,
        "cambiar_actividad":       70,
        "feedback_emocional":      88,
        "coevaluacion":            85,
    },
    "Delegador": {
        "aumentar_autonomia":      95,
        "aumentar_estructura":     30,
        "trabajo_cooperativo":     92,
        "reducir_ritmo":           78,
        "atencion_individual":     65,
        "cambiar_actividad":       60,
        "feedback_emocional":      70,
        "coevaluacion":            90,
    },
}

# Propuestas por tipo de alerta
PROPUESTAS_POR_ALERTA = {
    "ansiedad_alta": [
        {
            "tipo": "reducir_ritmo",
            "descripcion": "Introduce una pausa breve y reformula la actividad con menor presión evaluativa",
            "fundamento": "Reducir el coste percibido del error baja el valor amenazante → ↓ ansiedad (Pekrun, 2006)",
            "impacto_esperado": {"control": +8, "valor": -3}
        },
        {
            "tipo": "trabajo_cooperativo",
            "descripcion": "Reorganiza en parejas para que los alumnos ansiosos cuenten con apoyo de un igual",
            "fundamento": "El apoyo entre iguales ↑ relación social percibida → ↑ control percibido (SDT, Deci & Ryan)",
            "impacto_esperado": {"control": +6, "valor": +2}
        }
    ],
    "desesperanza": [
        {
            "tipo": "atencion_individual",
            "descripcion": "Intervención individual con el alumno: reformula el objetivo de forma alcanzable",
            "fundamento": "Restablecer control percibido mediante andamiaje específico (CVT: control → esperanza)",
            "impacto_esperado": {"control": +12, "valor": +5}
        },
        {
            "tipo": "feedback_emocional",
            "descripcion": "Reconoce públicamente el esfuerzo del alumno, no solo el resultado",
            "fundamento": "Feedback de proceso ↑ autonomía y competencia percibidas → ↑ control (SDT+CVT)",
            "impacto_esperado": {"control": +8, "valor": +4}
        }
    ],
    "aburrimiento_grupal": [
        {
            "tipo": "cambiar_actividad",
            "descripcion": "Introduce un reto o pregunta abierta que aumente el valor percibido de la tarea",
            "fundamento": "Bajo valor percibido → aburrimiento (Pekrun). ↑ novedad y relevancia ↑ valor",
            "impacto_esperado": {"control": +2, "valor": +10}
        },
        {
            "tipo": "aumentar_autonomia",
            "descripcion": "Da a los alumnos elección sobre cómo resolver la siguiente tarea",
            "fundamento": "Soporte a la autonomía ↑ motivación intrínseca → ↑ valor percibido (SDT)",
            "impacto_esperado": {"control": +3, "valor": +8}
        }
    ],
    "desenganche": [
        {
            "tipo": "trabajo_cooperativo",
            "descripcion": "Activa una dinámica grupal con roles definidos para recuperar implicación",
            "fundamento": "Estructura cooperativa ↑ relación social y competencia percibidas (SDT)",
            "impacto_esperado": {"control": +5, "valor": +7}
        },
        {
            "tipo": "feedback_emocional",
            "descripcion": "Reconecta con el grupo mediante una pregunta reflexiva sobre la utilidad del contenido",
            "fundamento": "↑ valor percibido de la tarea mediante relevancia personal (CVT)",
            "impacto_esperado": {"control": +3, "valor": +9}
        }
    ],
    "tension_social": [
        {
            "tipo": "atencion_individual",
            "descripcion": "Gestiona la tensión entre alumnos con una intervención directa y mediadora",
            "fundamento": "Restablecer relación social percibida → ↑ control percibido en contexto grupal (SDT)",
            "impacto_esperado": {"control": +4, "valor": +2}
        },
        {
            "tipo": "trabajo_cooperativo",
            "descripcion": "Reorganiza los grupos para separar o mediar entre los alumnos en tensión",
            "fundamento": "Cohesión grupal modera el contagio emocional negativo (Hatfield et al., 1993)",
            "impacto_esperado": {"control": +5, "valor": +3}
        }
    ]
}


# ── DETECCIÓN DE ALERTAS ──────────────────────────────────────────────────────

def detectar_alertas(agentes: list[dict]) -> list[dict]:
    """
    Analiza el estado emocional de los agentes y devuelve
    una lista de alertas activas con los alumnos afectados.
    """
    alumnos = [a for a in agentes if a["rol"] == "student"]
    alertas = []

    # Ansiedad alta: bajo control + alto valor
    afectados_ansiedad = [
        a for a in alumnos
        if a.get("control", 50) <= UMBRALES_ALERTA["ansiedad_alta"]["control_max"]
        and a.get("valor", 50) >= UMBRALES_ALERTA["ansiedad_alta"]["valor_min"]
    ]
    if len(afectados_ansiedad) >= UMBRALES_ALERTA["ansiedad_alta"]["n_min"]:
        alertas.append({
            "tipo": "ansiedad_alta",
            "descripcion": f"{len(afectados_ansiedad)} alumnos muestran ansiedad alta "
                           f"(control < 35, valor > 60)",
            "afectados": [a["id"] for a in afectados_ansiedad],
            "nombres_afectados": [a["nombre"] for a in afectados_ansiedad],
            "severidad": "alta" if len(afectados_ansiedad) >= 4 else "media"
        })

    # Desesperanza: bajo control + bajo valor
    afectados_des = [
        a for a in alumnos
        if a.get("control", 50) <= UMBRALES_ALERTA["desesperanza"]["control_max"]
        and a.get("valor", 50) <= UMBRALES_ALERTA["desesperanza"]["valor_max"]
    ]
    if len(afectados_des) >= UMBRALES_ALERTA["desesperanza"]["n_min"]:
        alertas.append({
            "tipo": "desesperanza",
            "descripcion": f"{len(afectados_des)} alumno(s) muestran desesperanza "
                           f"(control < 30, valor < 35)",
            "afectados": [a["id"] for a in afectados_des],
            "nombres_afectados": [a["nombre"] for a in afectados_des],
            "severidad": "alta"
        })

    # Aburrimiento grupal: alto control + bajo valor
    afectados_abur = [
        a for a in alumnos
        if a.get("control", 50) >= UMBRALES_ALERTA["aburrimiento_grupal"]["control_min"]
        and a.get("valor", 50) <= UMBRALES_ALERTA["aburrimiento_grupal"]["valor_max"]
    ]
    if len(afectados_abur) >= UMBRALES_ALERTA["aburrimiento_grupal"]["n_min"]:
        alertas.append({
            "tipo": "aburrimiento_grupal",
            "descripcion": f"{len(afectados_abur)} alumnos muestran aburrimiento "
                           f"(control > 60, valor < 35)",
            "afectados": [a["id"] for a in afectados_abur],
            "nombres_afectados": [a["nombre"] for a in afectados_abur],
            "severidad": "media"
        })

    # Desenganche general: bajo control + bajo valor
    afectados_des2 = [
        a for a in alumnos
        if a.get("control", 50) <= UMBRALES_ALERTA["desenganche"]["control_max"]
        and a.get("valor", 50) <= UMBRALES_ALERTA["desenganche"]["valor_max"]
    ]
    if len(afectados_des2) >= UMBRALES_ALERTA["desenganche"]["n_min"]:
        alertas.append({
            "tipo": "desenganche",
            "descripcion": f"{len(afectados_des2)} alumnos con desenganche general "
                           f"(control < 40, valor < 40)",
            "afectados": [a["id"] for a in afectados_des2],
            "nombres_afectados": [a["nombre"] for a in afectados_des2],
            "severidad": "media"
        })

    # Tensión social: baja relación percibida
    afectados_soc = [
        a for a in alumnos
        if a.get("relacion", 60) <= UMBRALES_ALERTA["tension_social"]["relacion_max"]
    ]
    if len(afectados_soc) >= UMBRALES_ALERTA["tension_social"]["n_min"]:
        alertas.append({
            "tipo": "tension_social",
            "descripcion": f"{len(afectados_soc)} alumnos con baja relación social "
                           f"percibida (relación < 30)",
            "afectados": [a["id"] for a in afectados_soc],
            "nombres_afectados": [a["nombre"] for a in afectados_soc],
            "severidad": "media"
        })

    return alertas


# ── GENERACIÓN DE PROPUESTA XAI ───────────────────────────────────────────────

def generar_propuesta(alerta: dict, estilo_docente: str) -> dict:
    """
    Selecciona la propuesta más adecuada para la alerta detectada,
    considerando el estilo docente para elegir la más aceptable.
    """
    propuestas_disponibles = PROPUESTAS_POR_ALERTA.get(alerta["tipo"], [])
    if not propuestas_disponibles:
        return None

    sesgos_estilo = SESGOS.get(estilo_docente, SESGOS["Estructurado-autónomo"])

    # Seleccionar la propuesta con mayor prior para este estilo
    mejor_propuesta = max(
        propuestas_disponibles,
        key=lambda p: sesgos_estilo.get(p["tipo"], 50)
    )

    prior = sesgos_estilo.get(mejor_propuesta["tipo"], 50)

    return {
        **mejor_propuesta,
        "alerta": alerta,
        "prior_aceptacion": prior,
        "estilo_docente": estilo_docente
    }


# ── PROMPT DE DECISIÓN DEL DOCENTE ────────────────────────────────────────────

def construir_prompt_decision(
    docente: dict,
    propuesta: dict,
    config: dict,
    historial_decisiones: list[dict]
) -> str:
    """
    Construye el prompt para que el agente-docente decida
    sobre la propuesta del sistema afectivo externo.
    El prior de sesgo se inyecta como contexto interno del personaje.
    """
    doc_config = config["docente"]
    prior = propuesta["prior_aceptacion"]
    alerta = propuesta["alerta"]

    # Describir historial de decisiones previas (últimas 3)
    hist_txt = "Sin decisiones previas en esta sesión."
    if historial_decisiones:
        ultimas = historial_decisiones[-3:]
        hist_txt = "\n".join([
            f"- Propuesta '{d['propuesta_tipo']}': {d['decision']} — {d['justificacion'][:60]}..."
            for d in ultimas
        ])

    # Nivel de inclinación basado en prior
    if prior >= 70:
        inclinacion = "tiendes a aceptar este tipo de propuestas según tu estilo"
    elif prior >= 45:
        inclinacion = "tienes una postura ambivalente ante este tipo de propuestas"
    else:
        inclinacion = "tiendes a resistir este tipo de propuestas según tu estilo"

    return f"""Eres {docente['nombre']}, profesor/a con estilo pedagógico {doc_config['estilo_predominante']}.

PERFIL: {docente.get('descripcion', '')}
Estado emocional actual: motivación={docente.get('motivacion',65):.0f}, estrés={docente.get('estres',40):.0f}, confianza={docente.get('confianza',68):.0f}
SDT docente: autonomía={docente.get('sdt_autonomia_docente',50):.0f}, estructura={docente.get('sdt_estructura_docente',65):.0f}, implicación={docente.get('sdt_implicacion_docente',60):.0f}

EL SISTEMA DE APOYO AFECTIVO TE ENVÍA ESTA ALERTA:
Situación detectada: {alerta['descripcion']}
Alumnos afectados: {', '.join(alerta['nombres_afectados'])}
Severidad: {alerta['severidad']}

PROPUESTA DE INTERVENCIÓN:
Tipo: {propuesta['tipo']}
Descripción: {propuesta['descripcion']}
Fundamento teórico: {propuesta['fundamento']}
Impacto esperado: control {'+' if propuesta['impacto_esperado']['control'] >= 0 else ''}{propuesta['impacto_esperado']['control']}, valor {'+' if propuesta['impacto_esperado']['valor'] >= 0 else ''}{propuesta['impacto_esperado']['valor']}

TU CONTEXTO INTERNO (no lo menciones explícitamente):
Como docente con estilo {doc_config['estilo_predominante']}, {inclinacion}.
Tu nivel de disposición a este tipo de intervención: {prior}/100.

HISTORIAL DE DECISIONES ANTERIORES:
{hist_txt}

Decide si aceptas, rechazas o modificas esta propuesta. Razona desde tu personaje,
considerando tu estilo docente, tu estado emocional actual y la situación del aula.

Responde ÚNICAMENTE con JSON válido sin markdown:
{{
  "decision": "acepta" | "rechaza" | "modifica",
  "modificacion": "descripción de qué cambiarías (null si acepta o rechaza sin cambios)",
  "justificacion": "razonamiento en primera persona, 2-3 frases, como lo diría el docente",
  "emocion_docente": "cómo te sientes al recibir esta propuesta (1 frase)",
  "delta_sdt": {{
    "autonomia": número entero -5 a +5,
    "estructura": número entero -5 a +5,
    "implicacion": número entero -5 a +5
  }}
}}"""


# ── DECISIÓN DEL DOCENTE VIA LLM ──────────────────────────────────────────────

def procesar_decision_docente(
    docente: dict,
    propuesta: dict,
    config: dict,
    sesion_id: str,
    turno: int,
    historial_decisiones: list[dict]
) -> dict:
    """
    Llama al LLM para que el agente-docente tome una decisión
    sobre la propuesta del sistema afectivo. Guarda en BD.
    """
    prompt = construir_prompt_decision(
        docente, propuesta, config, historial_decisiones
    )

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}]
        )

        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        parsed = json.loads(text)

    except Exception as e:
        print(f"  ⚠ Error en decisión docente: {e}")
        # Fallback: decisión neutral
        parsed = {
            "decision": "rechaza",
            "modificacion": None,
            "justificacion": "No puedo atender esto ahora mismo.",
            "emocion_docente": "sobrepasado",
            "delta_sdt": {"autonomia": 0, "estructura": 0, "implicacion": 0}
        }

    # Calcular estado emocional medio de la clase (pre-decisión)
    alerta = propuesta["alerta"]
    emo_clase_pre = calcular_estado_medio_clase(
        docente["sesion_id"] if "sesion_id" in docente else sesion_id
    )

    # Guardar decisión en BD
    decision_id = str(uuid.uuid4())
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO decisiones_docente VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
    """, (
        decision_id,
        sesion_id,
        docente["id"],
        turno,
        alerta["tipo"],
        alerta["descripcion"],
        propuesta["tipo"],
        propuesta["descripcion"],
        propuesta["fundamento"],
        float(propuesta["prior_aceptacion"]),
        parsed["decision"],
        parsed.get("modificacion"),
        parsed["justificacion"],
        parsed["emocion_docente"],
        json.dumps(parsed.get("delta_sdt", {})),
        json.dumps(emo_clase_pre),
        None,  # emo_clase_post se actualiza después
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()

    # Actualizar SDT del docente si hay delta
    delta_sdt = parsed.get("delta_sdt", {})
    if any(v != 0 for v in delta_sdt.values()):
        actualizar_sdt_docente(docente["id"], delta_sdt)
        # Actualizar en memoria también
        docente["sdt_autonomia_docente"] = max(0, min(100,
            docente.get("sdt_autonomia_docente", 50) + delta_sdt.get("autonomia", 0)))
        docente["sdt_estructura_docente"] = max(0, min(100,
            docente.get("sdt_estructura_docente", 65) + delta_sdt.get("estructura", 0)))
        docente["sdt_implicacion_docente"] = max(0, min(100,
            docente.get("sdt_implicacion_docente", 60) + delta_sdt.get("implicacion", 0)))

    resultado = {
        "decision_id": decision_id,
        "decision": parsed["decision"],
        "modificacion": parsed.get("modificacion"),
        "justificacion": parsed["justificacion"],
        "emocion_docente": parsed["emocion_docente"],
        "prior_aceptacion": propuesta["prior_aceptacion"],
        "propuesta_tipo": propuesta["tipo"],
        "alerta_tipo": alerta["tipo"]
    }

    historial_decisiones.append({
        "propuesta_tipo": propuesta["tipo"],
        "decision": parsed["decision"],
        "justificacion": parsed["justificacion"]
    })

    return resultado


# ── ACTUALIZACIÓN DEL PERFIL DOCENTE ─────────────────────────────────────────

def actualizar_sdt_docente(docente_id: str, delta_sdt: dict):
    """Actualiza las dimensiones SDT del docente en BD."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        UPDATE agentes SET
            sdt_autonomia_docente = MAX(0, MIN(100, sdt_autonomia_docente + ?)),
            sdt_estructura_docente = MAX(0, MIN(100, sdt_estructura_docente + ?)),
            sdt_implicacion_docente = MAX(0, MIN(100, sdt_implicacion_docente + ?))
        WHERE id = ?
    """, (
        delta_sdt.get("autonomia", 0),
        delta_sdt.get("estructura", 0),
        delta_sdt.get("implicacion", 0),
        docente_id
    ))
    conn.commit()
    conn.close()


def calcular_estado_medio_clase(sesion_id: str) -> dict:
    """Calcula el estado emocional medio de la clase en el momento actual."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("""
        SELECT
            AVG(control) as control_medio,
            AVG(valor) as valor_medio,
            AVG(autonomia) as autonomia_media,
            AVG(competencia) as competencia_media,
            AVG(relacion) as relacion_media
        FROM agentes
        WHERE sesion_id = ? AND rol = 'student'
    """, (sesion_id,)).fetchone()
    conn.close()

    if row:
        return {
            "control_medio": round(row[0] or 50, 1),
            "valor_medio": round(row[1] or 50, 1),
            "autonomia_media": round(row[2] or 50, 1),
            "competencia_media": round(row[3] or 50, 1),
            "relacion_media": round(row[4] or 50, 1),
        }
    return {}


def calcular_metricas_perfil_docente(sesion_id: str, docente_id: str) -> dict:
    """
    Calcula las métricas del perfil evolutivo del docente
    a partir del historial de decisiones de la sesión.
    """
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT decision, propuesta_tipo, prior_sesgo
        FROM decisiones_docente
        WHERE sesion_id = ? AND agente_id = ?
        ORDER BY created_at
    """, (sesion_id, docente_id)).fetchall()
    conn.close()

    if not rows:
        return {}

    total = len(rows)
    aceptadas = sum(1 for r in rows if r[0] == "acepta")
    modificadas = sum(1 for r in rows if r[0] == "modifica")
    rechazadas = sum(1 for r in rows if r[0] == "rechaza")

    # Tasa por tipo de propuesta
    por_tipo = {}
    for row in rows:
        tipo = row[1]
        if tipo not in por_tipo:
            por_tipo[tipo] = {"total": 0, "acepta": 0}
        por_tipo[tipo]["total"] += 1
        if row[0] in ("acepta", "modifica"):
            por_tipo[tipo]["acepta"] += 1

    acceptance_by_type = {
        tipo: round(v["acepta"] / v["total"], 2)
        for tipo, v in por_tipo.items()
    }

    # Coherencia sesgo-decisión
    coherencias = []
    for row in rows:
        decision_bin = 1 if row[0] in ("acepta", "modifica") else 0
        prior_norm = (row[2] or 50) / 100
        coherencias.append(abs(decision_bin - prior_norm))
    bias_coherence = round(1 - (sum(coherencias) / len(coherencias)), 2)

    # Firma de estilo (vector de aceptación por tipo)
    tipos_propuesta = [
        "aumentar_autonomia", "aumentar_estructura", "trabajo_cooperativo",
        "reducir_ritmo", "atencion_individual", "cambiar_actividad",
        "feedback_emocional", "coevaluacion"
    ]
    teaching_signature = {
        tipo: acceptance_by_type.get(tipo, 0.5)
        for tipo in tipos_propuesta
    }

    return {
        "total_propuestas": total,
        "aceptadas": aceptadas,
        "modificadas": modificadas,
        "rechazadas": rechazadas,
        "acceptance_rate": round(aceptadas / total, 2),
        "modification_rate": round(modificadas / total, 2),
        "bias_coherence": bias_coherence,
        "acceptance_by_type": acceptance_by_type,
        "teaching_signature": teaching_signature,
    }


def guardar_perfil_docente(sesion_id: str, docente_id: str, config: dict):
    """
    Calcula y guarda el perfil evolutivo del docente al final de la sesión.
    """
    metricas = calcular_metricas_perfil_docente(sesion_id, docente_id)
    if not metricas:
        return

    # Obtener estado SDT actual del docente
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("""
        SELECT sdt_autonomia_docente, sdt_estructura_docente, sdt_implicacion_docente
        FROM agentes WHERE id = ?
    """, (docente_id,)).fetchone()
    conn.close()

    sdt_emergente = {
        "autonomia": row[0] if row else 50,
        "estructura": row[1] if row else 65,
        "implicacion": row[2] if row else 60,
    }

    sdt_inicial = config["docente"]["sdt"]

    sdt_drift = {
        dim: round(sdt_emergente[dim] - sdt_inicial[dim], 1)
        for dim in ["autonomia", "estructura", "implicacion"]
    }

    # Inferir estilo emergente por mínima distancia a los perfiles de sesgo
    estilo_emergente = inferir_estilo_emergente(metricas["teaching_signature"])

    # Guardar en tabla teacher_profiles
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT OR REPLACE INTO teacher_profiles VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
    """, (
        str(uuid.uuid4()),
        docente_id,
        sesion_id,
        json.dumps(sdt_inicial),
        json.dumps(sdt_emergente),
        config["docente"]["estilo_predominante"],
        estilo_emergente,
        metricas["acceptance_rate"],
        metricas["modification_rate"],
        metricas["bias_coherence"],
        None,  # openness_index (longitudinal, se calcula entre sesiones)
        json.dumps(metricas["teaching_signature"]),
        None,  # system_alignment (longitudinal)
        json.dumps(sdt_drift),
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()

    print(f"\n  Perfil docente guardado:")
    print(f"    Tasa aceptación: {metricas['acceptance_rate']:.0%}")
    print(f"    Tasa modificación: {metricas['modification_rate']:.0%}")
    print(f"    Coherencia sesgo-decisión: {metricas['bias_coherence']:.2f}")
    print(f"    SDT drift: autonomía {sdt_drift['autonomia']:+.1f}, "
          f"estructura {sdt_drift['estructura']:+.1f}, "
          f"implicación {sdt_drift['implicacion']:+.1f}")
    print(f"    Estilo inicial: {config['docente']['estilo_predominante']} → "
          f"Emergente: {estilo_emergente}")

    return metricas


def inferir_estilo_emergente(teaching_signature: dict) -> str:
    """
    Infiere el estilo pedagógico emergente comparando el vector de firma
    del docente con los perfiles de la matriz de sesgos.
    Mínima distancia euclidiana.
    """
    tipos = list(teaching_signature.keys())
    min_distancia = float("inf")
    estilo_inferido = "Estructurado-autónomo"

    for estilo, sesgos in SESGOS.items():
        distancia = sum(
            (teaching_signature.get(t, 0.5) - sesgos.get(t, 50) / 100) ** 2
            for t in tipos
        ) ** 0.5

        if distancia < min_distancia:
            min_distancia = distancia
            estilo_inferido = estilo

    return estilo_inferido


# ── CREAR TABLA TEACHER_PROFILES SI NO EXISTE ─────────────────────────────────

def init_teacher_profiles_table():
    """Crea la tabla teacher_profiles si no existe."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS teacher_profiles (
            id TEXT PRIMARY KEY,
            teacher_id TEXT,
            sesion_id TEXT,
            sdt_initial TEXT,
            sdt_emergent TEXT,
            style_initial TEXT,
            style_emergent TEXT,
            acceptance_rate REAL,
            modification_rate REAL,
            bias_coherence REAL,
            openness_index REAL,
            teaching_signature TEXT,
            system_alignment REAL,
            sdt_drift TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


# ── FUNCIÓN PÚBLICA PRINCIPAL ─────────────────────────────────────────────────

def evaluar_y_proponer(
    agentes: list[dict],
    docente: dict,
    config: dict,
    sesion_id: str,
    turno: int,
    historial_decisiones: list[dict]
) -> dict | None:
    """
    Función principal del módulo. Detecta alertas, genera propuesta
    y procesa la decisión del docente.
    Devuelve el resultado de la decisión o None si no hay alertas.
    """
    alertas = detectar_alertas(agentes)

    if not alertas:
        return None

    # Tomar la alerta más severa
    alerta_prioritaria = sorted(
        alertas,
        key=lambda a: {"alta": 2, "media": 1}.get(a["severidad"], 0),
        reverse=True
    )[0]

    estilo_docente = config["docente"]["estilo_predominante"]
    propuesta = generar_propuesta(alerta_prioritaria, estilo_docente)

    if not propuesta:
        return None

    print(f"\n  🔔 ALERTA: {alerta_prioritaria['descripcion']}")
    print(f"  💡 Propuesta: {propuesta['descripcion'][:70]}...")
    print(f"  Prior de aceptación ({estilo_docente}): {propuesta['prior_aceptacion']}/100")
    print(f"  ⟳ El docente decide...")

    resultado = procesar_decision_docente(
        docente, propuesta, config,
        sesion_id, turno, historial_decisiones
    )

    icono = {"acepta": "✓", "rechaza": "✗", "modifica": "↻"}.get(
        resultado["decision"], "?"
    )
    print(f"  {icono} Decisión: {resultado['decision'].upper()}")
    print(f"  {docente.get('emoji','👩‍🏫')} {docente['nombre']}: "
          f"{resultado['justificacion'][:80]}...")

    return resultado


# ── ENTRY POINT (prueba standalone) ──────────────────────────────────────────

if __name__ == "__main__":
    """
    Modo de prueba: muestra las alertas y propuestas para una sesión activa
    sin ejecutar la decisión del docente.
    """
    import sys
    from pathlib import Path

    sesion_file = Path("data/ultima_sesion.txt")
    if not sesion_file.exists():
        print("✗ No hay sesión activa. Ejecuta genera_agentes.py primero.")
        sys.exit(1)

    sesion_id = sesion_file.read_text().strip()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    agentes = [dict(r) for r in conn.execute(
        "SELECT * FROM agentes WHERE sesion_id = ?", (sesion_id,)
    ).fetchall()]
    conn.close()

    print(f"\nAnalizando sesión {sesion_id[:8]}...")
    print(f"Agentes: {len(agentes)}")

    alertas = detectar_alertas(agentes)

    if not alertas:
        print("\n✓ Sin alertas activas en el estado emocional actual.")
    else:
        print(f"\n{len(alertas)} alerta(s) detectada(s):")
        for alerta in alertas:
            print(f"\n  [{alerta['severidad'].upper()}] {alerta['tipo']}")
            print(f"  {alerta['descripcion']}")
            print(f"  Afectados: {', '.join(alerta['nombres_afectados'])}")
