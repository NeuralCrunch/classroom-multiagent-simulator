# Classroom Multi-Agent Simulator

A research tool for simulating classroom dynamics using **CVT (Pekrun, 2006)** and **SDT Teaching Style (Reeve, 2009)** frameworks with a **Teacher-in-the-Loop** affective computing system.

## Overview

This simulator implements a multi-agent system where:
- **12 student agents** with diverse CVT profiles (control perceived, task value → emotions)
- **1 teacher agent** with SDT dimensions (autonomy support, structure, involvement)
- **Affective computing system** that monitors emotional states and generates XAI proposals
- **Teacher-in-the-Loop** decision loop with Bayesian priors

## Architecture

```
genera_agentes.py  →  Agent profile generation (Claude API)
motor.py           →  Simulation engine (CVT + SDT)
docente.py         →  Teacher agent + affective system
run_sesion.py      →  Session orchestrator
api.py             →  Flask API server
dashboard.html     →  Real-time visualization dashboard
demo_mode.py       →  Demo mode (no API calls needed)
```

## Theoretical Framework

- **CVT (Control-Value Theory)**: Pekrun, R. (2006). The control-value theory of achievement emotions. *Educational Psychology Review*, 18(4), 315–341.
- **SDT Teaching Style**: Reeve, J. (2009). Why teachers adopt a controlling motivating style toward students. *Educational Psychologist*, 44(3), 159–175.
- **Emotional contagion**: Hatfield, E., Cacioppo, J. T., & Rapson, R. L. (1993). Emotional contagion. *Current Directions in Psychological Science*, 2(3), 96–99.

## Quick Start

```bash
# Install dependencies
pip install flask anthropic

# Run demo (no API key needed)
python api.py --port 8080
# Open http://127.0.0.1:8080
# Click ▶ Start Demo
```

## Dashboard Features

- **Agent graph**: Real-time node-edge visualization with CVT emotion coloring
- **Speech bubbles**: Differentiated thought / speech / action bubbles
- **Affective console**: XAI messages in retro terminal style
- **Chat log**: Full dialogue history with emotion tags
- **Affinity tab**: Heatmap + network of student interactions
- **Teacher tab**: SDT profile and decision history
- **Metrics tab**: CVT distribution and session analytics

## Configuration

The dashboard includes a full configuration screen with:
- **ISCED Level** (0–8) + **QS Subject Areas**
- Teacher SDT parameters
- Student profiles (manually or generated via Claude API)
- Session phases and CVT alert thresholds

## Related Publication

> Junquera-Prats, E. et al. (2025). *Technically Advanced but Pedagogically Misaligned: A Systematic Literature Review on AI-Based Affective Computing in Education*. Artificial Intelligence Review, Springer Nature. (Under review)

## License

MIT License — Research use encouraged with attribution.
