"""
motor.py
Simulador de Aula Multi-Agente — Módulo 2
Orquesta las fases y turnos de una sesión, gestiona la selección por umbral
emocional, llama a la API en paralelo y aplica el contagio emocional pasivo.
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

# ── CONFIGURACIÓN ─────────────────────────────────────────────────────────────

DB_PATH = "data/simulador.db"
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# Matriz de contagio emocional pasivo (Hatfield et al., 1993)
# Supuestos simplificadores basados en dirección de efectos CVT (postura B)
CONTAGIO_MATRIX = {
    "disfrute":      {"control": +3,  "valor": +2},
    "orgullo":       {"control": +2,  "valor": +1},
    "ansiedad":      {"control": -5,  "valor": +2},
    "aburrimiento":  {"control": +1,  "valor": -4},
    "desesperanza":  {"control": -4,  "valor": -3},
    "neutro":        {"control":  0,  "valor":  0},
}

# Contagio amplificado del docente → toda la clase
CONTAGIO_DOCENTE = {
    "motivacion_alta":   {"control": +4, "valor": +3},
    "motivacion_baja":   {"control": -3, "valor": -2},
    "estres_alto":       {"control": -5, "valor": +2},
    "confianza_alta":    {"control": +3, "valor": +2},
    "confianza_baja":    {"control": -3, "valor": -1},
}


# ── UTILIDADES BD ─────────────────────────────────────────────────────────────

def get_sesion(sesion_id: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM sesiones WHERE id = ?", (sesion_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise ValueError(f"Sesión no encontrada: {sesion_id}")
    return dict(row)

def get_agentes(sesion_id: str) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM agentes WHERE sesion_id = ?", (sesion_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def actualizar_agente_emo(agente_id: str, control: float, valor: float):
    """Actualiza el estado emocional de un agente en BD."""
    from genera_agentes import calcular_emocion_dominante
    emocion = calcular_emocion_dominante(control, valor)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        UPDATE agentes SET control=?, valor=?, emocion_dominante=?
        WHERE id=?
    """, (
        max(0, min(100, control)),
        max(0, min(100, valor)),
        emocion, agente_id
    ))
    conn.commit()
    conn.close()
    return emocion

def guardar_turno(turno_data: dict):
    """Guarda un turno en BD."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO turnos VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?
        )
    """, (
        str(uuid.uuid4()),
        turno_data["sesion_id"],
        turno_data["agente_id"],
        turno_data["fase"],
        turno_data["turno"],
        turno_data["tipo_interaccion"],
        turno_data["speech"],
        turno_data.get("emotion_note", ""),
        turno_data.get("delta_control", 0),
        turno_data.get("delta_valor", 0),
        turno_data.get("delta_autonomia", 0),
        turno_data.get("delta_competencia", 0),
        turno_data.get("delta_relacion", 0),
        turno_data.get("control_post", 50),
        turno_data.get("valor_post", 50),
        turno_data.get("emocion_post", "neutro"),
        turno_data.get("es_activo", 1),
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()

def actualizar_estado_sesion(sesion_id: str, fase: int, turno: int, estado: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        UPDATE sesiones
        SET fase_actual=?, turno_actual=?, estado=?, updated_at=?
        WHERE id=?
    """, (fase, turno, estado, datetime.now().isoformat(), sesion_id))
    conn.commit()
    conn.close()


# ── CÁLCULO DE UMBRAL ─────────────────────────────────────────────────────────

def calcular_activation_score(agente: dict, turno_anterior: dict | None) -> float:
    """
    Calcula el activation_score de un agente para decidir si interviene activamente.
    Fórmula basada en CVT: estados extremos (ansiedad alta, confianza baja) y
    cambios recientes activan al agente.
    Supuesto simplificador — postura B metodológica.
    """
    control = agente.get("control", 50)
    valor = agente.get("valor", 50)

    # Componente 1: estados extremos negativos (ansiedad = bajo control + alto valor)
    ansiedad_proxy = max(0, (100 - control) * (valor / 100))
    componente_extremo = ansiedad_proxy * 0.4

    # Componente 2: engagement (control alto + valor alto)
    engagement = (control / 100) * (valor / 100) * 100
    componente_engagement = engagement * 0.3

    # Componente 3: cambio reciente en el último turno
    delta_reciente = 0
    if turno_anterior:
        delta_control = abs(turno_anterior.get("delta_control", 0))
        delta_valor = abs(turno_anterior.get("delta_valor", 0))
        delta_reciente = (delta_control + delta_valor) / 2
    componente_delta = delta_reciente * 0.3

    return componente_extremo + componente_engagement + componente_delta


def seleccionar_agentes_activos(
    agentes: list[dict],
    umbral: float,
    max_activos: int,
    tipo_fase: str,
    turnos_previos: dict,
    incluir_docente: bool = True
) -> tuple[list[dict], list[dict]]:
    """
    Selecciona los agentes que intervienen activamente este turno.
    Devuelve (activos, pasivos).
    """
    docente = next((a for a in agentes if a["rol"] == "teacher"), None)
    alumnos = [a for a in agentes if a["rol"] == "student"]

    activos = []
    pasivos = []

    # El docente siempre es activo en fases que lo requieren
    if incluir_docente and docente:
        activos.append(docente)

    # Calcular scores para alumnos
    scores = []
    for alumno in alumnos:
        ultimo_turno = turnos_previos.get(alumno["id"])
        score = calcular_activation_score(alumno, ultimo_turno)
        scores.append((alumno, score))

    # Ordenar por score descendente
    scores.sort(key=lambda x: -x[1])

    # Garantizar el agente con emoción más extrema
    extremo = scores[0][0] if scores else None

    slots_disponibles = max_activos - (1 if incluir_docente and docente else 0)

    agentes_seleccionados = set()

    # Incluir el más extremo siempre
    if extremo and slots_disponibles > 0:
        activos.append(extremo)
        agentes_seleccionados.add(extremo["id"])
        slots_disponibles -= 1

    # Rellenar con los que superan el umbral
    for alumno, score in scores:
        if slots_disponibles <= 0:
            break
        if alumno["id"] in agentes_seleccionados:
            continue
        if score >= umbral:
            activos.append(alumno)
            agentes_seleccionados.add(alumno["id"])
            slots_disponibles -= 1

    # El resto son pasivos
    for alumno in alumnos:
        if alumno["id"] not in agentes_seleccionados:
            pasivos.append(alumno)

    return activos, pasivos


# ── PROMPTS PARA EL LLM ───────────────────────────────────────────────────────

def construir_historial_texto(historial: list[dict]) -> str:
    """Construye el historial de la sesión como texto para el prompt."""
    if not historial:
        return "No hay intervenciones previas. Es el inicio de la clase."
    ultimas = historial[-6:]  # Últimas 6 intervenciones para no saturar contexto
    return "\n".join([
        f"{h['nombre']}: {h['speech']}"
        for h in ultimas
    ])


def construir_prompt_agente(
    agente: dict,
    otros_agentes: list[dict],
    fase: dict,
    turno: int,
    historial: list[dict],
    config: dict
) -> str:
    """Construye el prompt para un agente en un turno concreto."""
    es_docente = agente["rol"] == "teacher"
    control = agente.get("control", 50)
    valor = agente.get("valor", 50)
    autonomia = agente.get("autonomia", 50)
    competencia = agente.get("competencia", 50)
    relacion = agente.get("relacion", 50)

    # Descripción de otros agentes presentes (versión corta)
    otros_desc = "\n".join([
        f"- {a['nombre']} ({'docente' if a['rol']=='teacher' else 'alumno/a'}): "
        f"{a.get('descripcion','')[:80]}... "
        f"[emoción: {a.get('emocion_dominante','neutro')}]"
        for a in otros_agentes[:6]  # Máximo 6 para no saturar
    ])

    historial_txt = construir_historial_texto(historial)
    doc_config = config["docente"]

    if es_docente:
        rol_desc = f"profesor/a de {config['aula']['qs_subject']}"
        estado_desc = f"""
Estado emocional actual:
- Motivación: {agente.get('motivacion', 65)}/100
- Estrés: {agente.get('estres', 40)}/100
- Confianza en el grupo: {agente.get('confianza', 68)}/100
Estilo pedagógico: {doc_config['framework_pedagogico']} → {doc_config['estilo_predominante']}
SDT: autonomía={agente.get('sdt_autonomia_docente',50):.0f}, estructura={agente.get('sdt_estructura_docente',65):.0f}, implicación={agente.get('sdt_implicacion_docente',60):.0f}"""
    else:
        rol_desc = f"alumno/a de {config['aula']['qs_subject']}"
        emocion_actual = agente.get("emocion_dominante", "neutro")
        estado_desc = f"""
Estado emocional actual (CVT — Pekrun, 2006):
- Control percibido: {control:.0f}/100
- Valor percibido: {valor:.0f}/100
- Emoción dominante: {emocion_actual}
Necesidades psicológicas (SDT — Deci & Ryan):
- Autonomía percibida: {autonomia:.0f}/100
- Competencia percibida: {competencia:.0f}/100
- Relación social: {relacion:.0f}/100
Perfil especial: {agente.get('perfil_especial','ninguno')}"""

    return f"""Eres {agente['nombre']}, {rol_desc} en una clase de {config['aula']['etapa']} (edad media {config['aula']['edad_media']} años).

PERFIL:
{agente.get('descripcion', '')}
{estado_desc}

OTROS PRESENTES EN ESTE TURNO:
{otros_desc}

FASE ACTUAL: {fase.get('descripcion', fase.get('tipo',''))} (turno {turno})

HISTORIAL RECIENTE:
{historial_txt}

INSTRUCCIONES:
- Habla en primera persona, de forma natural y realista para tu personaje
- Tu estado emocional DEBE influir en cómo hablas, qué dices y cómo reaccionas
- Reacciona a lo que acaban de decir los demás si hay historial
- Sé breve y natural: 1-3 frases como lo haría alguien en clase
- NO rompas el personaje ni menciones el framework teórico
- Los valores de emotion_delta deben ser enteros entre -15 y +15
- Justifica el delta con la lógica CVT+SDT (ej: "la pregunta fácil sube mi control")

Responde ÚNICAMENTE con JSON válido sin markdown:
{{
  "speech": "lo que dices en voz alta",
  "emotion_note": "descripción breve de tu estado emocional interno (1 frase)",
  "emotion_delta": {{
    "control": número entero -15 a +15,
    "valor": número entero -15 a +15,
    "autonomia": número entero -10 a +10,
    "competencia": número entero -10 a +10,
    "relacion": número entero -10 a +10
  }}
}}"""


def construir_prompt_apertura_fase(
    docente: dict,
    fase: dict,
    num_fase: int,
    config: dict,
    historial: list[dict]
) -> str:
    """Prompt para que el docente abra una nueva fase."""
    historial_txt = construir_historial_texto(historial)
    doc_config = config["docente"]

    return f"""Eres {docente['nombre']}, profesor/a de {config['aula']['qs_subject']}.

PERFIL: {docente.get('descripcion', '')}
Estilo: {doc_config['estilo_predominante']} · Motivación: {docente.get('motivacion',65):.0f}/100

NUEVA FASE {num_fase}: {fase.get('descripcion', fase.get('tipo', ''))}

HISTORIAL PREVIO:
{historial_txt}

Introduce esta nueva fase de la clase con naturalidad. 1-3 frases como lo haría un/a docente real.

Responde ÚNICAMENTE con JSON válido sin markdown:
{{
  "speech": "lo que dices para abrir esta fase",
  "emotion_note": "cómo te sientes al iniciar esta fase",
  "emotion_delta": {{
    "control": 0,
    "valor": 0,
    "autonomia": 0,
    "competencia": 0,
    "relacion": 0
  }}
}}"""


# ── LLAMADAS PARALELAS A LA API ───────────────────────────────────────────────

async def llamar_agente_async(
    agente: dict,
    prompt: str,
    sesion_id: str,
    fase_idx: int,
    turno_idx: int,
    tipo_interaccion: str,
    historial: list[dict]
) -> dict | None:
    """Llama a la API para un agente y procesa su respuesta."""
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}]
            )
        )

        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        parsed = json.loads(text)
        delta = parsed.get("emotion_delta", {})

        # Calcular estado post-turno
        control_pre = agente.get("control", 50)
        valor_pre = agente.get("valor", 50)
        control_post = max(0, min(100, control_pre + delta.get("control", 0)))
        valor_post = max(0, min(100, valor_pre + delta.get("valor", 0)))

        # Actualizar en BD
        emocion_post = actualizar_agente_emo(agente["id"], control_post, valor_post)

        # También actualizar el dict en memoria
        agente["control"] = control_post
        agente["valor"] = valor_post
        agente["emocion_dominante"] = emocion_post

        # Guardar turno en BD
        guardar_turno({
            "sesion_id": sesion_id,
            "agente_id": agente["id"],
            "fase": fase_idx,
            "turno": turno_idx,
            "tipo_interaccion": tipo_interaccion,
            "speech": parsed.get("speech", ""),
            "emotion_note": parsed.get("emotion_note", ""),
            "delta_control": delta.get("control", 0),
            "delta_valor": delta.get("valor", 0),
            "delta_autonomia": delta.get("autonomia", 0),
            "delta_competencia": delta.get("competencia", 0),
            "delta_relacion": delta.get("relacion", 0),
            "control_post": control_post,
            "valor_post": valor_post,
            "emocion_post": emocion_post,
            "es_activo": 1
        })

        return {
            "agente_id": agente["id"],
            "nombre": agente["nombre"],
            "emoji": agente.get("emoji", "🧑"),
            "rol": agente["rol"],
            "speech": parsed.get("speech", ""),
            "emotion_note": parsed.get("emotion_note", ""),
            "emocion": emocion_post,
            "delta": delta
        }

    except json.JSONDecodeError as e:
        print(f"  ⚠ JSON inválido de {agente['nombre']}: {e}")
        return None
    except Exception as e:
        print(f"  ⚠ Error en {agente['nombre']}: {e}")
        return None


# ── CONTAGIO EMOCIONAL PASIVO ─────────────────────────────────────────────────

def aplicar_contagio_pasivo(
    agentes_pasivos: list[dict],
    agentes_activos: list[dict],
    cohesion: float,
    sesion_id: str,
    fase_idx: int,
    turno_idx: int
):
    """
    Aplica contagio emocional a los agentes pasivos basado en el estado
    de los agentes activos. Sin llamada a la API.
    Hatfield et al. (1993) — coeficiente modulado por cohesión grupal.
    """
    if not agentes_activos or not agentes_pasivos:
        return

    coef_cohesion = cohesion / 100  # Normalizar a 0-1

    # Calcular delta medio de los activos
    delta_control_medio = 0
    delta_valor_medio = 0
    n_activos = 0

    for activo in agentes_activos:
        if activo["rol"] == "student":
            emocion = activo.get("emocion_dominante", "neutro")
            contagio = CONTAGIO_MATRIX.get(emocion, {"control": 0, "valor": 0})
            delta_control_medio += contagio["control"]
            delta_valor_medio += contagio["valor"]
            n_activos += 1

    if n_activos == 0:
        return

    delta_control_medio /= n_activos
    delta_valor_medio /= n_activos

    # Aplicar a cada pasivo con coeficiente de cohesión
    for pasivo in agentes_pasivos:
        if pasivo["rol"] != "student":
            continue

        delta_c = delta_control_medio * coef_cohesion
        delta_v = delta_valor_medio * coef_cohesion

        control_pre = pasivo.get("control", 50)
        valor_pre = pasivo.get("valor", 50)
        control_post = max(0, min(100, control_pre + delta_c))
        valor_post = max(0, min(100, valor_pre + delta_v))

        emocion_post = actualizar_agente_emo(pasivo["id"], control_post, valor_post)
        pasivo["control"] = control_post
        pasivo["valor"] = valor_post
        pasivo["emocion_dominante"] = emocion_post

        # Guardar como turno pasivo en BD (sin speech)
        guardar_turno({
            "sesion_id": sesion_id,
            "agente_id": pasivo["id"],
            "fase": fase_idx,
            "turno": turno_idx,
            "tipo_interaccion": "contagio_pasivo",
            "speech": "",
            "emotion_note": f"contagio pasivo de grupo (cohesión {cohesion:.0f}%)",
            "delta_control": delta_c,
            "delta_valor": delta_v,
            "delta_autonomia": 0,
            "delta_competencia": 0,
            "delta_relacion": 0,
            "control_post": control_post,
            "valor_post": valor_post,
            "emocion_post": emocion_post,
            "es_activo": 0
        })


def aplicar_contagio_docente(
    docente: dict,
    alumnos: list[dict],
    sesion_id: str,
    fase_idx: int,
    turno_idx: int
):
    """
    Propaga el estado emocional del docente a todos los alumnos.
    El docente tiene mayor centralidad en la red social del aula.
    """
    motivacion = docente.get("motivacion", 65)
    estres = docente.get("estres", 40)
    confianza = docente.get("confianza", 68)

    delta_control = 0
    delta_valor = 0

    if motivacion >= 70:
        delta_control += CONTAGIO_DOCENTE["motivacion_alta"]["control"]
        delta_valor += CONTAGIO_DOCENTE["motivacion_alta"]["valor"]
    elif motivacion < 40:
        delta_control += CONTAGIO_DOCENTE["motivacion_baja"]["control"]
        delta_valor += CONTAGIO_DOCENTE["motivacion_baja"]["valor"]

    if estres >= 70:
        delta_control += CONTAGIO_DOCENTE["estres_alto"]["control"]
        delta_valor += CONTAGIO_DOCENTE["estres_alto"]["valor"]

    if confianza >= 70:
        delta_control += CONTAGIO_DOCENTE["confianza_alta"]["control"]
        delta_valor += CONTAGIO_DOCENTE["confianza_alta"]["valor"]
    elif confianza < 40:
        delta_control += CONTAGIO_DOCENTE["confianza_baja"]["control"]
        delta_valor += CONTAGIO_DOCENTE["confianza_baja"]["valor"]

    # Aplicar a todos los alumnos con factor reducido (no todos lo perciben igual)
    factor = 0.5
    for alumno in alumnos:
        if alumno["rol"] != "student":
            continue
        control_post = max(0, min(100, alumno.get("control", 50) + delta_control * factor))
        valor_post = max(0, min(100, alumno.get("valor", 50) + delta_valor * factor))
        emocion_post = actualizar_agente_emo(alumno["id"], control_post, valor_post)
        alumno["control"] = control_post
        alumno["valor"] = valor_post
        alumno["emocion_dominante"] = emocion_post


# ── BUCLE PRINCIPAL ───────────────────────────────────────────────────────────

async def ejecutar_sesion(
    sesion_id: str,
    pausa_segundos: float = 2.0,
    callback_turno=None
):
    """
    Ejecuta una sesión completa de simulación.
    callback_turno: función opcional que se llama tras cada turno con los resultados
    (útil para el dashboard en tiempo real).
    """
    # Cargar datos
    sesion = get_sesion(sesion_id)
    config = json.loads(sesion["config_json"])
    agentes = get_agentes(sesion_id)

    docente = next((a for a in agentes if a["rol"] == "teacher"), None)
    alumnos = [a for a in agentes if a["rol"] == "student"]

    fases = config["sesion"]["fases"]
    umbral = config["sesion"].get("umbral_activacion", 60)
    max_activos = config["sesion"].get("max_agentes_activos", 4)
    cohesion = config["afecto_inicial"]["sdt"]["cohesion"]

    historial = []  # Lista de intervenciones de la sesión
    turnos_previos = {}  # Último turno de cada agente para calcular delta

    print(f"\n{'='*60}")
    print(f"  INICIANDO SESIÓN: {sesion['nombre']}")
    print(f"  {len(alumnos)} alumnos · {len(fases)} fases")
    print(f"  Umbral activación: {umbral} · Máx. activos: {max_activos}")
    print(f"{'='*60}\n")

    actualizar_estado_sesion(sesion_id, 0, 0, "simulando")

    turno_global = 0

    for fase_idx, fase in enumerate(fases):
        print(f"\n── FASE {fase_idx + 1}: {fase.get('descripcion', fase['tipo'])} ──")

        # Apertura de fase por el docente
        if docente:
            print(f"  ⟳ {docente['nombre']} abre la fase...")
            prompt_apertura = construir_prompt_apertura_fase(
                docente, fase, fase_idx + 1, config, historial
            )
            resultado_apertura = await llamar_agente_async(
                docente, prompt_apertura, sesion_id,
                fase_idx, turno_global, f"apertura_{fase['tipo']}", historial
            )
            if resultado_apertura:
                historial.append(resultado_apertura)
                print(f"  {docente.get('emoji','👩‍🏫')} {docente['nombre']}: {resultado_apertura['speech'][:80]}...")
                if callback_turno:
                    await callback_turno(resultado_apertura, agentes, fase_idx, turno_global)

            turno_global += 1
            await asyncio.sleep(pausa_segundos)

        # Turnos de la fase
        for turno_idx in range(fase.get("turnos", 3)):
            print(f"\n  Turno {turno_idx + 1}/{fase['turnos']}")

            # Seleccionar agentes activos
            activos, pasivos = seleccionar_agentes_activos(
                agentes, umbral, max_activos,
                fase["tipo"], turnos_previos,
                incluir_docente=(fase["tipo"] not in ["group_work", "pair_work"])
            )

            nombres_activos = [a["nombre"] for a in activos]
            print(f"  Activos: {', '.join(nombres_activos)} ({len(pasivos)} pasivos)")

            # Llamadas paralelas para agentes activos
            prompts = []
            for agente in activos:
                otros = [a for a in activos if a["id"] != agente["id"]]
                prompt = construir_prompt_agente(
                    agente, otros, fase, turno_idx + 1, historial, config
                )
                prompts.append((agente, prompt))

            # Ejecutar en paralelo
            tareas = [
                llamar_agente_async(
                    agente, prompt, sesion_id,
                    fase_idx, turno_global, fase["tipo"], historial
                )
                for agente, prompt in prompts
            ]
            resultados = await asyncio.gather(*tareas)

            # Procesar resultados
            for resultado in resultados:
                if resultado:
                    historial.append(resultado)
                    agente_id = resultado["agente_id"]
                    turnos_previos[agente_id] = {
                        "delta_control": resultado["delta"].get("control", 0),
                        "delta_valor": resultado["delta"].get("valor", 0)
                    }
                    emo_icon = {"disfrute":"😊","ansiedad":"😰","aburrimiento":"😑",
                                "desesperanza":"😟","orgullo":"😤","neutro":"😐"}.get(
                                    resultado["emocion"], "😐")
                    print(f"  {resultado['emoji']} {resultado['nombre']} {emo_icon}: "
                          f"{resultado['speech'][:70]}...")

                    if callback_turno:
                        await callback_turno(resultado, agentes, fase_idx, turno_global)

            # Aplicar contagio pasivo
            aplicar_contagio_pasivo(
                pasivos, activos, cohesion,
                sesion_id, fase_idx, turno_global
            )

            # Aplicar contagio del docente a todos
            if docente:
                aplicar_contagio_docente(
                    docente, alumnos, sesion_id, fase_idx, turno_global
                )

            actualizar_estado_sesion(sesion_id, fase_idx, turno_global, "simulando")
            turno_global += 1
            await asyncio.sleep(pausa_segundos)

    # Fin de sesión
    actualizar_estado_sesion(sesion_id, len(fases), turno_global, "completada")

    # Resumen final
    print(f"\n{'='*60}")
    print(f"  ✓ SESIÓN COMPLETADA")
    print(f"  Turnos totales: {turno_global}")
    print(f"\n  Estado emocional final:")

    emociones_final = {}
    for ag in alumnos:
        emo = ag.get("emocion_dominante", "neutro")
        emociones_final[emo] = emociones_final.get(emo, 0) + 1

    for emo, n in sorted(emociones_final.items(), key=lambda x: -x[1]):
        barra = "█" * n
        print(f"    {emo:<15} {barra} ({n})")

    print(f"{'='*60}\n")

    # Exportar CSV
    exportar_csv(sesion_id)

    return historial


# ── EXPORTACIÓN CSV ───────────────────────────────────────────────────────────

def exportar_csv(sesion_id: str):
    """Exporta los turnos de la sesión a CSV para análisis."""
    import csv

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Join de turnos con agentes para tener nombre y rol
    rows = conn.execute("""
        SELECT
            t.fase, t.turno, t.tipo_interaccion,
            a.nombre, a.rol, a.emoji,
            a.perfil_especial,
            t.speech, t.emotion_note,
            t.delta_control, t.delta_valor,
            t.control_post, t.valor_post, t.emocion_post,
            t.es_activo, t.created_at
        FROM turnos t
        JOIN agentes a ON t.agente_id = a.id
        WHERE t.sesion_id = ?
        ORDER BY t.fase, t.turno, a.rol DESC
    """, (sesion_id,)).fetchall()
    conn.close()

    sesion_nombre = get_sesion(sesion_id)["nombre"]
    csv_path = f"data/{sesion_nombre}_{sesion_id[:8]}.csv"

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "fase", "turno", "tipo_interaccion",
            "nombre", "rol", "emoji", "perfil_especial",
            "speech", "emotion_note",
            "delta_control", "delta_valor",
            "control_post", "valor_post", "emocion_post",
            "es_activo", "created_at"
        ])
        writer.writeheader()
        writer.writerows([dict(r) for r in rows])

    print(f"✓ CSV exportado: {csv_path}")


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Leer sesion_id del archivo generado por genera_agentes.py
    # o pasarlo como argumento
    if len(sys.argv) > 1:
        sesion_id = sys.argv[1]
    else:
        sesion_file = Path("data/ultima_sesion.txt")
        if not sesion_file.exists():
            print("✗ No se encontró sesión activa.")
            print("  Ejecuta primero: python genera_agentes.py")
            sys.exit(1)
        sesion_id = sesion_file.read_text().strip()

    print(f"Usando sesión: {sesion_id[:8]}...")
    asyncio.run(ejecutar_sesion(sesion_id))
