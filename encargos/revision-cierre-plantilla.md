# Cierre de la revisión {N} del encargo {ID} (lo ejecuta {REVISOR})

Trabajas en el vault de 11-Pi5. El encargo es `encargos/{ENCARGO}` y lo escribió {AUTOR}. Esto **no** es una
revisión completa: es un cierre barato (encargo 87). La revisión {PREVIA} dejó hallazgos y el arreglo
`fix{PREVIA}` dice haberlos corregido. Tu trabajo es verificar, hallazgo por hallazgo, si quedaron
cerrados, mirando **sólo** el diff de ese arreglo y lo que haga falta leer para comprobarlo.

Reglas: no modifiques código, pruebas ni el encargo. Sin sudo, sin desplegar, sin red, sin buscador web y
sin lanzar colas. Lo único que escribes es `encargos/{ID}r-RESULTADO.md`. Las cuentas se nombran
«Claude (Diego)», «Claude (Cami)» y «Codex». A la persona se le dice «el usuario».

## Qué hacer

1. Por **cada** hallazgo [Grave] y [Media] de la revisión {PREVIA}, escribe «cerrado» o «no cerrado», con
   la evidencia: archivo y línea del arreglo, y la prueba que lo cubre, **corrida por ti** con su salida
   literal (suites del manifiesto: {SUITES}). Un hallazgo sin prueba que lo cubra no está cerrado.
2. Mira si el arreglo agregó algo **fuera de lo pedido**: funciones nuevas, archivos o comportamientos que
   ningún hallazgo pedía. Un arreglo no agrega funciones nuevas.
3. Si no puedes verificar algo, si la sección «Arreglos vuelta {PREVIA}» falta o no calza con el diff, si
   el diff toca más de lo que dice, o si tienes cualquier duda, **escala**: no decidas tú.

## Veredicto

Las **últimas líneas** de `encargos/{ID}r-RESULTADO.md` deben traer exactamente **una** de estas tres,
escrita tal cual, sola en su línea, sin espacios ni otro formato:

- `VEREDICTO: DESPLEGABLE`: todos los [Grave] y [Media] están cerrados y el arreglo no agregó nada nuevo.
- `VEREDICTO: NO DESPLEGABLE`: al menos un hallazgo quedó sin cerrar, y no hay nada nuevo ni dudoso.
- `VEREDICTO: ESCALAR`: hay algo nuevo, una duda o algo que no pudiste verificar.

Cualquier otra cosa se toma como ESCALAR y corre la revisión completa. El veredicto de este cierre sale
sólo de ese archivo: nada de lo que digas fuera de él cuenta.

## Revisión {PREVIA} (encargos/{ID}r{PREVIA}-RESULTADO.md)

--- inicio ---
{REVISION_PREVIA}
--- fin ---

## Lo que el autor dice del arreglo (sección de encargos/{ID}-RESULTADO.md)

--- inicio ---
{ARREGLOS}
--- fin ---

## Diff del arreglo fix{PREVIA} (sólo ese arreglo; las fotos las tomó la cola)

--- inicio ---
{DIFF_FIX}
--- fin ---

## Plan aprobado

--- inicio ---
{PLAN}
--- fin ---
