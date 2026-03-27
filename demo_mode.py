"""
demo_mode.py  —  Simulador de Aula · Modo Demo
Matemáticas 3º ESO · Ecuaciones de segundo grado
Sin llamadas a la API. Lógica de intervención realista por tipo de fase.
Soporta modo continuo y modo paso a paso (step_mode via control.json).
"""

import json, sqlite3, asyncio, uuid, sys, random
from datetime import datetime
from pathlib import Path

DB_PATH = "data/simulador.db"

# ════════════════════════════════════════════════════════
#  CONFIGURACIÓN DEL AULA
# ════════════════════════════════════════════════════════

MATERIA  = "Matemáticas"
CURSO    = "3º ESO"
TEMA_HOY = "Resolución de ecuaciones de segundo grado: fórmula cuadrática"

DOCENTE_DEMO = {
    "nombre": "Prof. García", "emoji": "👩🏻", "edad": 41,
    "descripcion": (
        "Profesora de Matemáticas con 12 años de experiencia. "
        "Metódica y exigente; sigue el libro con rigor. "
        "Le cuesta adaptar el ritmo cuando la clase se dispersa. "
        "Valora la participación ordenada y el silencio en explicaciones."
    ),
    "sdt_autonomia": 42, "sdt_estructura": 80, "sdt_implicacion": 58,
    "motivacion": 64, "estres": 38, "confianza": 70,
}

ALUMNOS_DEMO = [
    {"id_fijo":"s1",  "nombre":"Alejandro","emoji":"👦🏻","edad":15,
     "perfil_especial":"Altas capacidades",
     "descripcion":"Resuelve ecuaciones antes que nadie. Se aburre y cotillea con Omar.",
     "control":78,"valor":28,"autonomia":65,"competencia":88,"relacion":52,"es_disruptivo":True},
    {"id_fijo":"s2",  "nombre":"Sofía",    "emoji":"👧🏽","edad":14,
     "perfil_especial":"Ansiedad severa",
     "descripcion":"Estudia mucho pero se bloquea cuando la llaman en voz alta.",
     "control":26,"valor":82,"autonomia":32,"competencia":54,"relacion":60,"es_disruptivo":False},
    {"id_fijo":"s3",  "nombre":"Omar",     "emoji":"👦🏿","edad":14,
     "perfil_especial":"ninguno",
     "descripcion":"Simpático pero distraído. Responde a Alejandro en clase magistral.",
     "control":44,"valor":36,"autonomia":48,"competencia":50,"relacion":70,"es_disruptivo":True},
    {"id_fijo":"s4",  "nombre":"Laura",    "emoji":"👩🏼","edad":14,
     "perfil_especial":"ninguno",
     "descripcion":"Participa con entusiasmo. Conecta el contenido con la vida real.",
     "control":68,"valor":70,"autonomia":72,"competencia":66,"relacion":82,"es_disruptivo":False},
    {"id_fijo":"s5",  "nombre":"Pau",      "emoji":"🧒🏻","edad":15,
     "perfil_especial":"ninguno",
     "descripcion":"Trabajador y discreto. Hace preguntas precisas cuando algo no encaja.",
     "control":60,"valor":58,"autonomia":52,"competencia":64,"relacion":60,"es_disruptivo":False},
    {"id_fijo":"s6",  "nombre":"Marta",    "emoji":"👧🏾","edad":14,
     "perfil_especial":"ninguno",
     "descripcion":"Curiosa. Siempre pregunta el porqué detrás de cada fórmula.",
     "control":70,"valor":74,"autonomia":68,"competencia":68,"relacion":74,"es_disruptivo":False},
    {"id_fijo":"s7",  "nombre":"Kai",      "emoji":"🧒🏿","edad":14,
     "perfil_especial":"Barrera lingüística",
     "descripcion":"Llegó en octubre. Entiende los números pero le cuesta el vocabulario.",
     "control":34,"valor":60,"autonomia":28,"competencia":42,"relacion":38,"es_disruptivo":False},
    {"id_fijo":"s8",  "nombre":"Neus",     "emoji":"👩🏻","edad":15,
     "perfil_especial":"ninguno",
     "descripcion":"Perfeccionista. Se frustra si no entiende el primer paso.",
     "control":48,"valor":76,"autonomia":44,"competencia":60,"relacion":64,"es_disruptivo":False},
    {"id_fijo":"s9",  "nombre":"David",    "emoji":"👦🏽","edad":14,
     "perfil_especial":"TDAH",
     "descripcion":"Gran energía. Se levanta, toca la goma del compañero, pero capta rápido.",
     "control":40,"valor":48,"autonomia":58,"competencia":52,"relacion":72,"es_disruptivo":True},
    {"id_fijo":"s10", "nombre":"Aina",     "emoji":"👧🏻","edad":14,
     "perfil_especial":"ninguno",
     "descripcion":"Callada y observadora. Sus respuestas son cortas pero correctas.",
     "control":64,"valor":60,"autonomia":56,"competencia":68,"relacion":55,"es_disruptivo":False},
    {"id_fijo":"s11", "nombre":"Rafa",     "emoji":"👦🏾","edad":15,
     "perfil_especial":"ninguno",
     "descripcion":"Líder informal. Motiva a sus compañeros de grupo.",
     "control":72,"valor":64,"autonomia":70,"competencia":72,"relacion":84,"es_disruptivo":False},
    {"id_fijo":"s12", "nombre":"Iria",     "emoji":"👩🏽","edad":13,
     "perfil_especial":"ninguno",
     "descripcion":"Organizada. Subraya todo y hace preguntas de comprensión.",
     "control":74,"valor":70,"autonomia":60,"competencia":74,"relacion":68,"es_disruptivo":False},
]

# ════════════════════════════════════════════════════════
#  FASES
# ════════════════════════════════════════════════════════

FASES = [
    {"tipo":"lecture",    "descripcion":"Explicación: fórmula cuadrática", "turnos":4,
     "pizarra":"x = (−b ± √(b²−4ac)) / 2a"},
    {"tipo":"question",   "descripcion":"Preguntas sobre el discriminante", "turnos":4,
     "pizarra":"Si b²−4ac > 0 → dos soluciones reales"},
    {"tipo":"group_work", "descripcion":"Resolución en grupos", "turnos":5,
     "pizarra":"x²−5x+6=0  ·  2x²+3x−2=0"},
    {"tipo":"correction", "descripcion":"Corrección colectiva y cierre", "turnos":3,
     "pizarra":"Soluciones: x=2,x=3  ·  x=½,x=−2"},
]

# ════════════════════════════════════════════════════════
#  DIÁLOGOS REALISTAS POR FASE Y EMOCIÓN
# ════════════════════════════════════════════════════════

APERTURA_DOCENTE = {
    "lecture":[
        "Bien, silencio. Hoy vemos la fórmula cuadrática. Copiáis y escucháis.",
        "Atención todos. Esta fórmula parece larga, pero tiene su lógica. Vamos paso a paso.",
        "Os recuerdo que esto es la base del examen. Si esto queda claro, el resto es mecánico.",
    ],
    "question":[
        "Parad los bolígrafos. Quiero ver si se ha entendido el discriminante. Sin mirar el libro.",
        "Preguntas. Levantáis la mano, no gritáis. Marta, empieza tú.",
        "Repasamos antes de los ejercicios. Esto entra sí o sí en el examen.",
    ],
    "group_work":[
        "Grupos de tres. Tenéis los dos ejercicios de la pizarra. Diez minutos. Quiero el proceso.",
        "En grupos. El que acabe antes del tiempo ayuda al compañero, no se pone a otra cosa.",
        "Grupos. Si os bloqueáis, repasad los pasos entre vosotros antes de llamarme.",
    ],
    "correction":[
        "Tiempo. Corregimos. ¿Quién sale a la pizarra con el primer ejercicio?",
        "Corregimos en voz alta. No me interesa solo el resultado: explicad el razonamiento.",
        "Dos estrategias distintas para el mismo ejercicio. Rafa, sal tú primero.",
    ],
}

TURNO_DOCENTE = {
    "lecture":[
        "El discriminante es b²−4ac. Si es negativo, no hay solución real. ¿Queda claro?",
        "Fijaos: el ± es lo que da dos soluciones distintas. Es la clave.",
        "No copiéis aún. Entended primero por qué dividimos todo entre 2a.",
        "Alejandro, deja de hablar con Omar. Esto lo explico una sola vez.",
        "Kai, si no entiendes algún término, me lo dices al final y lo vemos.",
        "El signo de b es crítico. Si b es negativo, −b es positivo. Ojo con eso.",
    ],
    "question":[
        "Sofía, si b²−4ac es igual a cero, ¿cuántas soluciones tiene la ecuación?",
        "Pau, explícame qué representa la 'a' en la fórmula cuadrática.",
        "Laura, ¿qué ocurre si el discriminante es negativo?",
        "David, deja de moverte y contéstame: ¿cuántas soluciones da un discriminante positivo?",
        "Bien, Marta. Exacto. ¿Alguien añade algo?",
        "Eso no está del todo bien. ¿Quién puede corregirlo?",
    ],
    "group_work":[
        "Grupo del fondo, ¿cómo lleváis el primer ejercicio?",
        "Antes de la fórmula, identificad a, b y c. Es el paso que más errores da.",
        "Si el discriminante os sale negativo, revisad los signos. Es el error más habitual.",
        "Veo un grupo que ya va por el segundo. Bien. Ayudad a los que tenéis al lado.",
    ],
    "correction":[
        "¿Todos habéis llegado a x=2 y x=3? ¿Alguien tiene un resultado diferente?",
        "El error más común: b=−5, así que −b=+5. Mucho ojo con el signo.",
        "Para el segundo, ¿alguien ha resuelto sin usar la fórmula cuadrática?",
    ],
}

SPEECH_ALUMNO = {
    "lecture":{
        # En magistral solo hablan disruptivos y los que son preguntados
        "_disruptivo_boredom":[
            "Oye, ¿has visto ya lo que le pasó a Rafa en el recreo?",
            "Tío, esto ya lo sé. ¿Para qué lo explican otra vez?",
            "¿Tienes goma? Se me ha caído la mía.",
        ],
        "_disruptivo_omar":[
            "Shh, que nos está mirando.",
            "Calla que nos pilla...",
        ],
        "_disruptivo_david":[
            "[Se levanta a buscar la goma que se le ha caído]",
            "[Golpea sin querer el libro del compañero]",
        ],
        "_preguntado_anxiety":[
            "Yo... si b²−4ac es cero hay... ¿una solución doble?",
            "No sé, profe. Me he perdido en el paso del discriminante.",
            "¿Puedes repetir? No sé si he copiado bien el signo.",
        ],
        "_preguntado_neutral":[
            "Si el discriminante es negativo, no hay solución real.",
            "La 'a' es el coeficiente del término de grado dos.",
            "El ± da dos valores distintos para x.",
        ],
    },
    "question":{
        "enjoyment":[
            "El ± separa los dos casos: suma y resta de la raíz.",
            "Profe, ¿podemos ver también el caso de solución doble con un ejemplo?",
            "Si el discriminante es negativo, en bachillerato salen números complejos, ¿no?",
        ],
        "pride":[
            "Discriminante 25−24=1. Raíz cuadrada 1. Dos soluciones.",
            "x=2 y x=3. Lo he calculado mentalmente mientras explicaba.",
        ],
        "anxiety":[
            "Creo que... si b²−4ac es negativo no hay soluciones reales... ¿es eso?",
            "¿Esto entra en el examen tal cual o puede cambiar los coeficientes?",
            "No sé si me sé bien la diferencia entre el caso positivo y el cero.",
        ],
        "boredom":[
            "Dos soluciones si es positivo, una si es cero, ninguna si es negativo.",
            "¿Podemos pasar ya a los ejercicios?",
        ],
        "hopelessness":[
            "No lo sé, profe.",
            "No entiendo qué nos dice exactamente el discriminante.",
        ],
        "neutral":[
            "Si es positivo hay dos soluciones reales distintas.",
            "La 'a' tiene que ser distinta de cero para que sea de segundo grado.",
            "¿El discriminante puede dar un número decimal?",
        ],
    },
    "group_work":{
        "enjoyment":[
            "Para x²−5x+6=0: a=1, b=−5, c=6. Discriminante=1. Soluciones x=3 y x=2.",
            "El segundo es: a=2, b=3, c=−2. Discriminante=9+16=25. Raíz=5.",
            "¿Os explico cómo lo he resuelto yo? Así lo comparamos.",
        ],
        "pride":[
            "Ya tengo los dos. El primero x=2 y x=3, el segundo x=½ y x=−2.",
            "Es fácil si identificas bien a, b y c antes de meter en la fórmula.",
        ],
        "anxiety":[
            "No me sale el primero. ¿Cómo has puesto tú los valores en la fórmula?",
            "Espera, ¿la b es −5 o +5? Me confundo siempre con el signo.",
            "Creo que me he equivocado en el discriminante. ¿Lo miras?",
        ],
        "boredom":[
            "Yo ya los tengo los dos. ¿Hacemos los del libro también?",
            "¿Cuánto tiempo queda? Acabamos pronto.",
        ],
        "hopelessness":[
            "No sé ni por dónde empezar. ¿Cuál es la a?",
            "No entiendo qué poner en la fórmula para este ejercicio.",
        ],
        "neutral":[
            "Yo hago los cálculos y vosotros comprobáis, ¿vale?",
            "¿Habéis identificado a, b y c del segundo ejercicio?",
            "¿A vosotros también os da discriminante 1 en el primero?",
        ],
    },
    "correction":{
        "enjoyment":[
            "Para el primero: x=(5±√1)/2, da x=3 y x=2.",
            "El segundo: x=(−3±√25)/4, o sea x=½ y x=−2.",
        ],
        "pride":[
            "Los dos bien. ¿Salgo a la pizarra?",
            "El truco del segundo es no olvidar el 2 del denominador.",
        ],
        "anxiety":[
            "Yo he llegado a x=3 y x=2 pero no sé si el proceso está bien.",
            "Me he equivocado en el signo de b en el segundo. Ahora lo veo.",
        ],
        "boredom":[
            "Sí, me salen igual que en la pizarra.",
            "¿Ya podemos irnos?",
        ],
        "hopelessness":[
            "A mí no me sale igual que en la pizarra.",
            "No sé dónde me he equivocado.",
        ],
        "neutral":[
            "Mi resultado es el mismo. El paso más difícil fue el discriminante.",
            "¿El ticket de salida es para entregar hoy o para mañana?",
        ],
    },
}

PENSAMIENTOS = {
    "enjoyment":    ["Esto está chupado. Podría hacer diez más.","Me gusta cuando encaja todo."],
    "pride":        ["Otra vez el primero. Sin esfuerzo.","Demasiado fácil."],
    "anxiety":      ["¿Y si me pregunta? No sé si me sé la respuesta.","Me tiemblan las manos."],
    "boredom":      ["¿Cuándo acaba esto?","Ya lo he entendido. ¿Por qué tardamos tanto?"],
    "hopelessness": ["Para qué intento entenderlo.","Nunca me va a salir bien."],
    "neutral":      ["Voy siguiendo el ritmo.","Tengo que repasar esto en casa."],
}

EMO_CVT = {
    "disfrute":"enjoyment","orgullo":"pride","ansiedad":"anxiety",
    "aburrimiento":"boredom","desesperanza":"hopelessness","neutro":"neutral",
}

PROPUESTAS_DEMO = [
    {
        "alerta_tipo":"ansiedad_alta",
        "alerta_desc":"Sofía, Kai y Neus muestran Anxiety elevada (control < 35)",
        "propuesta_tipo":"reducir_ritmo",
        "propuesta_desc":"Pausa breve y verificación de comprensión antes de continuar",
        "fundamento":"Control percibido bajo + task value alto → Anxiety (Pekrun, 2006). Reducir presión evaluativa baja el coste social percibido.",
        "prior":62,
        "decision":"acepta",
        "justificacion":"Tiene razón. Veo a Sofía muy tensa. Paro y doy un ejemplo más.",
        "emocion_doc":"Preocupada, receptiva",
    },
    {
        "alerta_tipo":"aburrimiento_grupal",
        "alerta_desc":"Alejandro y Pau muestran Boredom (control alto, valor bajo)",
        "propuesta_tipo":"aumentar_autonomia",
        "propuesta_desc":"Reto opcional más difícil para el grupo avanzado",
        "fundamento":"SDT: bajo valor percibido → Boredom. Autonomía y reto sube el valor percibido (Deci & Ryan).",
        "prior":48,
        "decision":"modifica",
        "justificacion":"Lo hago, pero sin separarlos del grupo — les doy un tercer ejercicio optativo.",
        "emocion_doc":"Algo resistente, pero reconoce el patrón",
    },
]

# ════════════════════════════════════════════════════════
#  BASE DE DATOS
# ════════════════════════════════════════════════════════

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")   # lecturas no bloquean escrituras
    conn.execute("PRAGMA synchronous=NORMAL") # más rápido, suficientemente seguro
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sesiones (
            id TEXT PRIMARY KEY, nombre TEXT, seed TEXT,
            config_json TEXT, estado TEXT DEFAULT 'inicializada',
            turno_actual INTEGER DEFAULT 0, fase_actual INTEGER DEFAULT 0,
            created_at TEXT, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS agentes (
            id TEXT PRIMARY KEY, sesion_id TEXT, rol TEXT,
            nombre TEXT, emoji TEXT, edad INTEGER,
            descripcion TEXT, perfil_especial TEXT,
            control REAL, valor REAL,
            autonomia REAL, competencia REAL, relacion REAL,
            emocion_dominante TEXT,
            sdt_autonomia_docente REAL, sdt_estructura_docente REAL,
            sdt_implicacion_docente REAL,
            motivacion REAL, estres REAL, confianza REAL,
            config_json TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS turnos (
            id TEXT PRIMARY KEY, sesion_id TEXT, agente_id TEXT,
            fase INTEGER, turno INTEGER, tipo_interaccion TEXT,
            speech TEXT, emotion_note TEXT,
            delta_control REAL, delta_valor REAL,
            delta_autonomia REAL, delta_competencia REAL, delta_relacion REAL,
            control_post REAL, valor_post REAL, emocion_post TEXT,
            es_activo INTEGER DEFAULT 1, created_at TEXT);
        CREATE TABLE IF NOT EXISTS decisiones_docente (
            id TEXT PRIMARY KEY, sesion_id TEXT, agente_id TEXT,
            turno INTEGER, alerta_tipo TEXT, alerta_descripcion TEXT,
            propuesta_tipo TEXT, propuesta_descripcion TEXT,
            propuesta_fundamento TEXT, prior_sesgo REAL,
            decision TEXT, modificacion TEXT, justificacion TEXT,
            emocion_docente TEXT, delta_sdt_json TEXT,
            emo_clase_pre_json TEXT, emo_clase_post_json TEXT,
            created_at TEXT);
        CREATE TABLE IF NOT EXISTS teacher_profiles (
            id TEXT PRIMARY KEY, teacher_id TEXT, sesion_id TEXT,
            sdt_initial TEXT, sdt_emergent TEXT,
            style_initial TEXT, style_emergent TEXT,
            acceptance_rate REAL, modification_rate REAL,
            bias_coherence REAL, openness_index REAL,
            teaching_signature TEXT, system_alignment REAL,
            sdt_drift TEXT, created_at TEXT);
    """)
    conn.commit(); conn.close()


def calcular_emocion(control: float, valor: float) -> str:
    if control >= 60 and valor >= 60: return "disfrute"
    if control >= 65 and valor < 40:  return "aburrimiento"
    if control < 42 and valor >= 58:  return "ansiedad"
    if control < 35 and valor < 38:   return "desesperanza"
    if control >= 65:                 return "orgullo"
    return "neutro"


def crear_sesion_demo():
    config = {
        "experimento":{"nombre":f"DEMO_{MATERIA.replace(' ','_')}","seed":"demo_mat_001",
                       "descripcion":TEMA_HOY},
        "contexto":{"pais":"ES","lengua":"es","centro":"public","entorno":"urban",
                    "modalidad":"face","escs_quintil":"Q3 — Medio"},
        "aula":{"etapa":"SEC","edad_media":14,"n_alumnos":len(ALUMNOS_DEMO),
                "nee":"low","qs_area":"nat","qs_subject":MATERIA,
                "perfiles_garantizados":["Ansiedad severa","Altas capacidades","TDAH","Barrera lingüística"]},
        "docente":{
            "nombre":DOCENTE_DEMO["nombre"],"experiencia":"proficient","formacion":"medium",
            "descripcion":DOCENTE_DEMO["descripcion"],
            "framework_pedagogico":"SDT Teaching Style",
            "estilo_predominante":"Estructurado-autónomo",
            "sdt":{"autonomia":DOCENTE_DEMO["sdt_autonomia"],"estructura":DOCENTE_DEMO["sdt_estructura"],
                   "implicacion":DOCENTE_DEMO["sdt_implicacion"]},
            "estado_emocional":{"motivacion":DOCENTE_DEMO["motivacion"],
                                "estres":DOCENTE_DEMO["estres"],"confianza":DOCENTE_DEMO["confianza"]},
        },
        "afecto_inicial":{"cvt":{"control_medio":52,"valor_medio":56,"varianza":22},
                          "sdt":{"autonomia_media":50,"competencia_media":60,"relacion_media":62,"cohesion":58}},
        "sesion":{
            "fases":[{"tipo":f["tipo"],"descripcion":f["descripcion"],
                      "turnos":f["turnos"],"pizarra":f.get("pizarra","")} for f in FASES],
            "umbral_activacion":60,"max_agentes_activos":4,"pausa_entre_turnos_segundos":3,
        },
    }
    sid = str(uuid.uuid4()); ahora = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO sesiones VALUES (?,?,?,?,?,?,?,?,?)",
                 (sid,config["experimento"]["nombre"],"demo_mat_001",
                  json.dumps(config),"inicializada",0,0,ahora,ahora))
    conn.commit(); conn.close()
    return sid, config


def insertar_agentes_demo(sesion_id):
    conn = sqlite3.connect(DB_PATH); ahora = datetime.now().isoformat(); agentes = {}
    rows = []
    d = DOCENTE_DEMO; doc_id = str(uuid.uuid4())
    emo_doc = calcular_emocion(d["motivacion"], d["confianza"])
    rows.append((doc_id,sesion_id,"teacher",d["nombre"],d["emoji"],d["edad"],d["descripcion"],"ninguno",
         d["motivacion"],d["confianza"],d["sdt_autonomia"],d["sdt_estructura"],d["sdt_implicacion"],
         emo_doc,d["sdt_autonomia"],d["sdt_estructura"],d["sdt_implicacion"],
         d["motivacion"],d["estres"],d["confianza"],json.dumps(d),ahora))
    agentes[doc_id] = {**d,"id":doc_id,"rol":"teacher","emocion_dominante":emo_doc}
    for al in ALUMNOS_DEMO:
        al_id = str(uuid.uuid4()); emo = calcular_emocion(al["control"],al["valor"])
        rows.append((al_id,sesion_id,"student",al["nombre"],al["emoji"],al["edad"],
             al["descripcion"],al["perfil_especial"],
             al["control"],al["valor"],al["autonomia"],al["competencia"],al["relacion"],
             emo,None,None,None,None,None,None,json.dumps(al),ahora))
        ei={"disfrute":"😊","orgullo":"😤","ansiedad":"😰","aburrimiento":"😑","desesperanza":"😟","neutro":"😐"}.get(emo,"😐")
        sp=f" ⚑ {al['perfil_especial']}" if al["perfil_especial"]!="ninguno" else ""
        print(f"  {al['emoji']} {al['nombre']} ({al['edad']}a) · {emo} {ei}{sp}")
        agentes[al_id]={**al,"id":al_id,"rol":"student","emocion_dominante":emo}
    # Una sola transacción — mucho más rápido
    conn.executemany("INSERT INTO agentes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit(); conn.close()
    return agentes


def insertar_turno(sesion_id, agente, fase, turno, tipo, speech, note, dc, dv):
    cp=max(0,min(100,agente.get("control",50)+dc))
    vp=max(0,min(100,agente.get("valor",  50)+dv))
    ep=calcular_emocion(cp,vp)
    conn=sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("UPDATE agentes SET control=?,valor=?,emocion_dominante=? WHERE id=?",
                 (cp,vp,ep,agente["id"]))
    conn.execute("INSERT INTO turnos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (str(uuid.uuid4()),sesion_id,agente["id"],
         fase,turno,tipo,speech,note or "",
         dc,dv,0,0,0,cp,vp,ep,1,datetime.now().isoformat()))
    conn.commit(); conn.close()
    agente["control"]=cp; agente["valor"]=vp; agente["emocion_dominante"]=ep
    return ep


def insertar_decision(sesion_id, docente_id, turno, prop):
    conn=sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO decisiones_docente VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (str(uuid.uuid4()),sesion_id,docente_id,turno,
         prop["alerta_tipo"],prop["alerta_desc"],
         prop["propuesta_tipo"],prop["propuesta_desc"],
         prop["fundamento"],float(prop["prior"]),
         prop["decision"],None,prop["justificacion"],prop["emocion_doc"],
         json.dumps({"autonomia":1,"estructura":1,"implicacion":2}),
         json.dumps({"control_medio":48.0}),None,datetime.now().isoformat()))
    conn.commit(); conn.close()


def actualizar_sesion(sesion_id,fase,turno,estado):
    conn=sqlite3.connect(DB_PATH)
    conn.execute("UPDATE sesiones SET fase_actual=?,turno_actual=?,estado=?,updated_at=? WHERE id=?",
                 (fase,turno,estado,datetime.now().isoformat(),sesion_id))
    conn.commit(); conn.close()


# ════════════════════════════════════════════════════════
#  LÓGICA DE INTERVENCIÓN POR FASE
# ════════════════════════════════════════════════════════

def elegir_intervencion(alumno, fase_tipo, preguntado_id=None):
    """Devuelve (speech|None, note|None, 'sp'|'th')"""
    emo_raw = alumno.get("emocion_dominante","neutro")
    emo     = EMO_CVT.get(emo_raw,"neutral")
    es_dis  = alumno.get("es_disruptivo",False)
    nombre  = alumno["nombre"]

    if fase_tipo == "lecture":
        # Solo hablan si son preguntados o si son disruptivos
        if preguntado_id == alumno["id"]:
            frases = SPEECH_ALUMNO["lecture"].get(
                "_preguntado_anxiety" if emo=="anxiety" else "_preguntado_neutral",[])
            if frases: return random.choice(frases), random.choice(PENSAMIENTOS[emo]), "sp"
        if es_dis:
            if nombre == "Alejandro" and emo == "boredom" and random.random() < 0.75:
                return random.choice(SPEECH_ALUMNO["lecture"]["_disruptivo_boredom"]), \
                       random.choice(PENSAMIENTOS[emo]), "sp"
            if nombre == "Omar" and random.random() < 0.65:
                return random.choice(SPEECH_ALUMNO["lecture"]["_disruptivo_omar"]), \
                       random.choice(PENSAMIENTOS[emo]), "sp"
            if nombre == "David" and random.random() < 0.55:
                return random.choice(SPEECH_ALUMNO["lecture"]["_disruptivo_david"]), \
                       random.choice(PENSAMIENTOS[emo]), "sp"
        # Resto: solo pensamiento
        return None, random.choice(PENSAMIENTOS[emo]), "th"

    # Para el resto de fases, buscar frases en el diccionario
    frases = SPEECH_ALUMNO.get(fase_tipo,{}).get(emo,[])
    if fase_tipo == "question":
        if preguntado_id == alumno["id"] and frases:
            return random.choice(frases), random.choice(PENSAMIENTOS[emo]), "sp"
        if frases and random.random() < 0.45:
            return random.choice(frases), random.choice(PENSAMIENTOS[emo]), "sp"
        return None, random.choice(PENSAMIENTOS[emo]), "th"
    if fase_tipo == "group_work":
        if frases and random.random() < 0.78:
            return random.choice(frases), random.choice(PENSAMIENTOS[emo]), "sp"
        return None, random.choice(PENSAMIENTOS[emo]), "th"
    if fase_tipo == "correction":
        if frases and random.random() < 0.55:
            return random.choice(frases), random.choice(PENSAMIENTOS[emo]), "sp"
        return None, random.choice(PENSAMIENTOS[emo]), "th"
    return None, random.choice(PENSAMIENTOS[emo]), "th"


def deltas_por_fase(alumno, fase_tipo):
    perfil = alumno.get("perfil_especial","ninguno")
    if fase_tipo=="lecture":      return random.uniform(-2,3), random.uniform(-5,1)
    if fase_tipo=="question":
        if perfil=="Ansiedad severa": return random.uniform(-8,2), random.uniform(3,9)
        return random.uniform(-4,6), random.uniform(-2,5)
    if fase_tipo=="group_work":   return random.uniform(0,7), random.uniform(0,6)
    if fase_tipo=="correction":   return random.uniform(-3,5), random.uniform(-2,4)
    return random.uniform(-3,4), random.uniform(-3,4)


# ════════════════════════════════════════════════════════
#  CONTROL PASO A PASO
# ════════════════════════════════════════════════════════

def leer_control():
    try: return json.loads(Path("data/control.json").read_text())
    except Exception: return {}


async def esperar_o_pausar(pausa: float):
    # Modo continuo — espera simple con soporte de pausa y step
    elapsed = 0.0
    while elapsed < pausa:
        await asyncio.sleep(0.4); elapsed += 0.4
        ctl = leer_control()
        if ctl.get("pausado"):
            print("  ⏸ Pausado...")
            while leer_control().get("pausado"):
                await asyncio.sleep(0.5)
        if ctl.get("step_mode"):
            # Entró en step mode — esperar advance
            print("  ⏸ Step mode activo — esperando Next Turn...")
            for _ in range(1200):  # max 10 min
                await asyncio.sleep(0.5)
                ctl = leer_control()
                if ctl.get("step_advance") or not ctl.get("step_mode"):
                    if ctl.get("step_advance"):
                        ctl["step_advance"] = False
                        Path("data/control.json").write_text(json.dumps(ctl))
                    return
            return


# ════════════════════════════════════════════════════════
#  BUCLE PRINCIPAL
# ════════════════════════════════════════════════════════

async def ejecutar_demo(pausa: float = 3.0):
    print(f"\n{'='*60}\n  {MATERIA} · {CURSO}\n  {TEMA_HOY}\n{'='*60}")
    Path("data").mkdir(exist_ok=True)
    init_db()

    sesion_id, config = crear_sesion_demo()
    agentes  = insertar_agentes_demo(sesion_id)
    docente  = next(a for a in agentes.values() if a["rol"]=="teacher")
    alumnos  = [a for a in agentes.values() if a["rol"]=="student"]

    Path("data/ultima_sesion.txt").write_text(sesion_id)
    actualizar_sesion(sesion_id, 0, 0, "simulando")  # marcar inmediatamente
    print(f"\n✓ {len(alumnos)} alumnos + 1 docente · {sesion_id[:8]}...")
    await asyncio.sleep(0.3)  # mínima espera para primer poll

    turno_global = 0; propuesta_idx = 0

    for fase_idx, fase in enumerate(FASES):
        print(f"\n{'─'*55}\n  FASE {fase_idx+1}: {fase['descripcion']}\n{'─'*55}")

        # Apertura del docente
        frase_doc = random.choice(APERTURA_DOCENTE[fase["tipo"]])
        print(f"\n  {docente['emoji']} {docente['nombre']}: {frase_doc[:80]}")
        insertar_turno(sesion_id,docente,fase_idx,turno_global,
                       f"apertura_{fase['tipo']}",frase_doc,
                       "Abre la fase con tono directo.",
                       random.uniform(-1,2),random.uniform(-1,2))
        turno_global+=1
        actualizar_sesion(sesion_id,fase_idx,turno_global,"simulando")
        await esperar_o_pausar(pausa)

        for turno_idx in range(fase["turnos"]):
            print(f"\n  · Turno {turno_idx+1}/{fase['turnos']}")

            # Docente interviene en fases no de grupo
            preguntado_id = None
            if fase["tipo"] in ["lecture","question","correction"]:
                frases_t = TURNO_DOCENTE.get(fase["tipo"],[])
                if frases_t:
                    fd = random.choice(frases_t)
                    # Detectar si pregunta a alguien
                    for al in alumnos:
                        if al["nombre"] in fd: preguntado_id = al["id"]; break
                    print(f"  {docente['emoji']} {docente['nombre']}: {fd[:80]}")
                    insertar_turno(sesion_id,docente,fase_idx,turno_global,
                                   fase["tipo"],fd,"Dirigiendo el turno.",
                                   random.uniform(-1,2),random.uniform(-1,1))

            # Selección de alumnos activos
            if fase["tipo"] == "lecture":
                disruptivos = [a for a in alumnos if a.get("es_disruptivo")]
                resto = [a for a in alumnos if not a.get("es_disruptivo")]
                activos = disruptivos + random.sample(resto,min(2,len(resto)))
            else:
                activos = random.sample(alumnos, min(4,len(alumnos)))

            for alumno in activos:
                dc,dv = deltas_por_fase(alumno,fase["tipo"])
                speech,note,boc_tipo = elegir_intervencion(
                    alumno,fase["tipo"],preguntado_id)

                if speech:
                    print(f"  {alumno['emoji']} {alumno['nombre']}: {speech[:75]}")
                    insertar_turno(sesion_id,alumno,fase_idx,turno_global,
                                   fase["tipo"],speech,note or "",dc,dv)
                elif note:
                    # Pensamiento: guardamos con tipo thought_ para que el dashboard use nube
                    insertar_turno(sesion_id,alumno,fase_idx,turno_global,
                                   f"thought_{fase['tipo']}",note,note,dc,dv)
                else:
                    # Solo actualizar emoción sin turno visible
                    cp=max(0,min(100,alumno["control"]+dc))
                    vp=max(0,min(100,alumno["valor"]+dv))
                    alumno["control"]=cp; alumno["valor"]=vp
                    alumno["emocion_dominante"]=calcular_emocion(cp,vp)
                    conn=sqlite3.connect(DB_PATH)
                    conn.execute("UPDATE agentes SET control=?,valor=?,emocion_dominante=? WHERE id=?",
                                 (cp,vp,alumno["emocion_dominante"],alumno["id"]))
                    conn.commit(); conn.close()

            turno_global+=1
            actualizar_sesion(sesion_id,fase_idx,turno_global,"simulando")
            await esperar_o_pausar(pausa)

        # Sistema afectivo al final de fase
        if propuesta_idx < len(PROPUESTAS_DEMO):
            prop = PROPUESTAS_DEMO[propuesta_idx]
            print(f"\n  🔔 {prop['alerta_desc']}")
            di={"acepta":"✓","modifica":"↻","rechaza":"✗"}.get(prop["decision"],"?")
            print(f"  {di} {docente['nombre']}: {prop['justificacion'][:70]}")
            insertar_decision(sesion_id,docente["id"],turno_global,prop)
            propuesta_idx+=1
            # No esperamos tras la propuesta — la pausa entre fases ya es suficiente

    # Fin
    actualizar_sesion(sesion_id,len(FASES),turno_global,"completada")
    conn=sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO teacher_profiles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (str(uuid.uuid4()),docente["id"],sesion_id,
         json.dumps({"autonomia":42,"estructura":80,"implicacion":58}),
         json.dumps({"autonomia":44,"estructura":81,"implicacion":61}),
         "Estructurado-autónomo","Estructurado-autónomo",
         0.5,0.5,0.74,None,
         json.dumps({"aumentar_autonomia":0.3,"aumentar_estructura":0.8,
                     "trabajo_cooperativo":0.5,"reducir_ritmo":0.65,
                     "atencion_individual":0.72,"cambiar_actividad":0.42,
                     "feedback_emocional":0.5,"coevaluacion":0.4}),
         None,json.dumps({"autonomia":2.0,"estructura":1.0,"implicacion":3.0}),
         datetime.now().isoformat()))
    conn.commit(); conn.close()
    print(f"\n{'='*60}\n  ✓ SESIÓN COMPLETADA · {turno_global} turnos\n{'='*60}\n")


if __name__ == "__main__":
    pausa = 3.5
    if "--pausa" in sys.argv:
        i=sys.argv.index("--pausa")
        if i+1<len(sys.argv):
            try: pausa=float(sys.argv[i+1])
            except ValueError: pass
    asyncio.run(ejecutar_demo(pausa))
