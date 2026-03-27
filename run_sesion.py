"""
run_sesion.py
Simulador de Aula Multi-Agente — Orquestador principal
Conecta genera_agentes.py, motor.py y docente.py en un único flujo.
Uso:
    python run_sesion.py                          # usa config por defecto
    python run_sesion.py config/mi_config.json    # config personalizada
    python run_sesion.py --sesion <sesion_id>     # continúa sesión existente
"""

import asyncio
import json
import os
import sys
import sqlite3
from datetime import datetime
from pathlib import Path

# Importar módulos del simulador
from genera_agentes import generar_agentes
from motor import ejecutar_sesion, get_agentes, get_sesion
from docente import (
    evaluar_y_proponer,
    guardar_perfil_docente,
    init_teacher_profiles_table,
    calcular_estado_medio_clase
)

DB_PATH = "data/simulador.db"


# ── MOTOR CON SISTEMA AFECTIVO INTEGRADO ─────────────────────────────────────

async def ejecutar_sesion_completa(
    sesion_id: str,
    config: dict,
    pausa_segundos: float = 2.0
):
    """
    Extiende el motor base integrando el sistema afectivo externo.
    Evalúa alertas y propone al docente al final de cada fase.
    """
    from motor import (
        get_agentes, actualizar_estado_sesion,
        seleccionar_agentes_activos, construir_prompt_apertura_fase,
        construir_prompt_agente, llamar_agente_async,
        aplicar_contagio_pasivo, aplicar_contagio_docente,
        exportar_csv
    )

    agentes = get_agentes(sesion_id)
    docente = next((a for a in agentes if a["rol"] == "teacher"), None)
    alumnos = [a for a in agentes if a["rol"] == "student"]

    fases = config["sesion"]["fases"]
    umbral = config["sesion"].get("umbral_activacion", 60)
    max_activos = config["sesion"].get("max_agentes_activos", 4)
    cohesion = config["afecto_inicial"]["sdt"]["cohesion"]

    historial = []
    turnos_previos = {}
    historial_decisiones = []  # Para el perfil evolutivo del docente

    print(f"\n{'='*60}")
    print(f"  SESIÓN: {config['experimento']['nombre']}")
    print(f"  {len(alumnos)} alumnos · {len(fases)} fases")
    print(f"  Docente: {docente['nombre']} · {config['docente']['estilo_predominante']}")
    print(f"{'='*60}")

    actualizar_estado_sesion(sesion_id, 0, 0, "simulando")
    turno_global = 0

    for fase_idx, fase in enumerate(fases):
        print(f"\n{'─'*50}")
        print(f"  FASE {fase_idx + 1}/{len(fases)}: {fase.get('descripcion', fase['tipo'])}")
        print(f"{'─'*50}")

        # Apertura de fase por el docente
        if docente:
            print(f"\n  ⟳ Apertura de fase...")
            prompt_apertura = construir_prompt_apertura_fase(
                docente, fase, fase_idx + 1, config, historial
            )
            resultado = await llamar_agente_async(
                docente, prompt_apertura, sesion_id,
                fase_idx, turno_global,
                f"apertura_{fase['tipo']}", historial
            )
            if resultado:
                historial.append(resultado)
                _imprimir_intervencion(resultado)
            turno_global += 1
            await asyncio.sleep(pausa_segundos)

        # Turnos de la fase
        for turno_idx in range(fase.get("turnos", 3)):
            print(f"\n  · Turno {turno_idx + 1}/{fase['turnos']}")

            activos, pasivos = seleccionar_agentes_activos(
                agentes, umbral, max_activos,
                fase["tipo"], turnos_previos,
                incluir_docente=(fase["tipo"] not in ["group_work", "pair_work"])
            )

            print(f"    Activos: {', '.join(a['nombre'] for a in activos)}"
                  f" · {len(pasivos)} pasivos")

            # Llamadas paralelas
            tareas = [
                llamar_agente_async(
                    ag,
                    construir_prompt_agente(
                        ag,
                        [a for a in activos if a["id"] != ag["id"]],
                        fase, turno_idx + 1, historial, config
                    ),
                    sesion_id, fase_idx, turno_global,
                    fase["tipo"], historial
                )
                for ag in activos
            ]
            resultados = await asyncio.gather(*tareas)

            for resultado in resultados:
                if resultado:
                    historial.append(resultado)
                    turnos_previos[resultado["agente_id"]] = {
                        "delta_control": resultado["delta"].get("control", 0),
                        "delta_valor": resultado["delta"].get("valor", 0)
                    }
                    _imprimir_intervencion(resultado)

            # Contagio pasivo y docente
            aplicar_contagio_pasivo(
                pasivos, activos, cohesion,
                sesion_id, fase_idx, turno_global
            )
            if docente:
                aplicar_contagio_docente(
                    docente, alumnos,
                    sesion_id, fase_idx, turno_global
                )

            actualizar_estado_sesion(sesion_id, fase_idx, turno_global, "simulando")
            turno_global += 1
            await asyncio.sleep(pausa_segundos)

        # ── SISTEMA AFECTIVO AL FINAL DE CADA FASE ──
        print(f"\n  🔍 Sistema afectivo evaluando estado del aula...")
        agentes_actualizados = get_agentes(sesion_id)
        docente_actualizado = next(
            (a for a in agentes_actualizados if a["rol"] == "teacher"), docente
        )

        decision = evaluar_y_proponer(
            agentes_actualizados,
            docente_actualizado,
            config,
            sesion_id,
            turno_global,
            historial_decisiones
        )

        if decision:
            # Actualizar docente en memoria con los nuevos valores SDT
            for ag in agentes:
                if ag["rol"] == "teacher":
                    ag.update({
                        k: v for k, v in docente_actualizado.items()
                        if k.startswith("sdt_")
                    })

        await asyncio.sleep(pausa_segundos)

    # ── FIN DE SESIÓN ──
    actualizar_estado_sesion(sesion_id, len(fases), turno_global, "completada")
    _imprimir_resumen_final(sesion_id, agentes, turno_global, config)

    # Guardar perfil docente
    print("\n  Calculando perfil evolutivo del docente...")
    if docente:
        guardar_perfil_docente(sesion_id, docente["id"], config)

    # Exportar CSV
    exportar_csv(sesion_id)

    return historial


def _imprimir_intervencion(resultado: dict):
    """Imprime una intervención de forma legible."""
    EMO_ICONS = {
        "disfrute": "😊", "orgullo": "😤", "ansiedad": "😰",
        "aburrimiento": "😑", "desesperanza": "😟", "neutro": "😐"
    }
    emo = resultado.get("emocion", "neutro")
    icono = EMO_ICONS.get(emo, "😐")
    rol = "👩‍🏫" if resultado["rol"] == "teacher" else resultado.get("emoji", "🧑")
    speech = resultado["speech"]
    if len(speech) > 90:
        speech = speech[:87] + "..."
    print(f"    {rol} {resultado['nombre']} {icono}: {speech}")
    if resultado.get("emotion_note"):
        print(f"       💭 {resultado['emotion_note'][:70]}")


def _imprimir_resumen_final(
    sesion_id: str,
    agentes: list[dict],
    turno_global: int,
    config: dict
):
    """Imprime el resumen al finalizar la sesión."""
    alumnos = [a for a in agentes if a["rol"] == "student"]

    # Obtener estado actualizado desde BD
    agentes_bd = get_agentes(sesion_id)
    alumnos_bd = [a for a in agentes_bd if a["rol"] == "student"]

    emociones = {}
    for al in alumnos_bd:
        emo = al.get("emocion_dominante", "neutro")
        emociones[emo] = emociones.get(emo, 0) + 1

    control_medio = sum(a.get("control", 50) for a in alumnos_bd) / len(alumnos_bd) if alumnos_bd else 50
    valor_medio = sum(a.get("valor", 50) for a in alumnos_bd) / len(alumnos_bd) if alumnos_bd else 50

    print(f"\n{'='*60}")
    print(f"  ✓ SESIÓN COMPLETADA")
    print(f"  Turnos ejecutados: {turno_global}")
    print(f"  Control medio final: {control_medio:.1f}/100")
    print(f"  Valor medio final: {valor_medio:.1f}/100")
    print(f"\n  Distribución emocional final:")
    for emo, n in sorted(emociones.items(), key=lambda x: -x[1]):
        barra = "█" * n
        print(f"    {emo:<15} {barra} ({n})")
    print(f"{'='*60}")


# ── FUNCIÓN PRINCIPAL ─────────────────────────────────────────────────────────

async def main():
    """Punto de entrada principal."""

    # Verificar API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("✗ Falta ANTHROPIC_API_KEY")
        print("  Ejecuta: export ANTHROPIC_API_KEY='sk-ant-...'")
        sys.exit(1)

    # Parsear argumentos
    config_path = "config/experimento_01.json"
    sesion_id_existente = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--sesion" and i + 1 < len(args):
            sesion_id_existente = args[i + 1]
            i += 2
        elif args[i] == "--pausa" and i + 1 < len(args):
            i += 2  # Se maneja abajo
        elif not args[i].startswith("--"):
            config_path = args[i]
            i += 1
        else:
            i += 1

    pausa = 2.0
    if "--pausa" in args:
        idx = args.index("--pausa")
        if idx + 1 < len(args):
            try:
                pausa = float(args[idx + 1])
            except ValueError:
                pass

    # Inicializar tabla de perfiles docente
    init_teacher_profiles_table()

    # Cargar o crear sesión
    if sesion_id_existente:
        print(f"Retomando sesión: {sesion_id_existente[:8]}...")
        sesion = get_sesion(sesion_id_existente)
        config = json.loads(sesion["config_json"])
        sesion_id = sesion_id_existente
    else:
        # Verificar config
        if not Path(config_path).exists():
            print(f"✗ No se encuentra: {config_path}")
            sys.exit(1)

        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        # Paso 1: Generar agentes
        print("\n[1/2] Generando agentes...")
        sesion_id, _ = await generar_agentes(config_path)

        print(f"\n[2/2] Iniciando simulación...")
        await asyncio.sleep(1)

    # Ejecutar sesión completa con sistema afectivo
    await ejecutar_sesion_completa(sesion_id, config, pausa_segundos=pausa)

    print(f"\n✓ Todo completado.")
    print(f"  Datos guardados en: data/simulador.db")
    print(f"  CSV exportado en:   data/")
    print(f"\n  Para analizar los resultados:")
    print(f"  jupyter notebook analisis.ipynb")


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    asyncio.run(main())
