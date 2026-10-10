# Planned next

**None of these is available in this cadgen yet**, and none has a study key
to write today. They come after every analysis in the skill's "Choose the
analysis" table. When the user asks for one, say plainly that it is planned
and not here yet, and do not stand a static result in for it.

| What the user asks about | Plain word | How it will work |
| --- | --- | --- |
| Turbulent flow (fast water or air in a pipe, past a body) | Turbulent flow | an extension of `cfd`, with a turbulence model |
| Fast gas flow, where the gas compresses | Fast gas flow | an extension of `cfd`, slower than sound first |
| A part slowly stretching under load at high temperature | Creep | a `creep` analysis, stepped through time |
| Carbon fibre, laminates, wood or other materials stiffer one way than another | Composite | direction-dependent materials, and layups on thin parts |
| A bolted joint's preload and how it carries load | Bolted joint | a `bolt` connection between assembly parts |
| Magnetic or electric fields, magnet forces, heating from current | Magnetic / electric | an `electromagnetic` analysis, feeding forces into `static` and heating into `thermal` |

Until they ship, an honest hand estimate, labelled as one, is the most you
can offer.
