---
name: hello-world
description: Skill de ejemplo. Sirve para verificar que el SkillLoader la lee, la parsea y la integra correctamente en el contexto del agente.
user-invocable: true
metadata:
  orion:
    requires:
      bins: []
    primaryEnv: ""
---

# hello-world

Esta es una skill mínima. Su único propósito es probar el SkillLoader de
ORION. Si la ves listada en el panel "Skills" del frontend, el parser está
funcionando.

## Qué le enseña al agente

Cuando el Director invoca esta skill, el especialista debe:

1. Responder al usuario con un saludo breve.
2. Indicar que recibió el contenido de la skill.
3. NO ejecutar bash ni tools — es sólo para validar el pipeline.

## Bloque de ejemplo

Las skills reales suelen tener bash embebido que el agente ejecuta. Para
referencia del formato:

```bash
echo "Hola desde la skill hello-world"
```

## Cuándo NO usar esta skill

- Para tareas reales (no hace nada útil).
- En producción una vez que valides que el loader anda.
