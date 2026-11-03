"""Datos lingüísticos del módulo ``ai``: stopwords y léxicos de sentimiento
(español + inglés). Los conjuntos POS y NEG están disjuntos por construcción.
"""

from __future__ import annotations

STOPWORDS: frozenset[str] = frozenset(
    """
    de la el en y que los se del las un por con no una su para es al lo como
    mas más o pero sus le ya este si sí porque esta entre cuando muy sin sobre
    tambien también me hasta hay donde quien desde todo nos durante todos uno
    les ni contra otros ese eso ante ellos e esto mi antes algunos que unos yo
    otro otras otra él tanto esa estos mucho quienes nada muchos cual poco ella
    estar estas algunas algo nosotros mis tu te ti tus ellas os sea eres soy era
    the a an and or but if then than that this these those of in on at to for
    with without from by about into over after before is are was were be been
    being am do does did doing have has had having i you he she it we they me
    him her us them my your his its our their what which who whom whose when
    where why how all any both each few more most other some such no nor not
    only own same so too very can will just should now don't does it's i'm
    """.split()
)

POSITIVE_WORDS: frozenset[str] = frozenset(
    """
    good great excellent amazing wonderful love loved lovely best better
    awesome fantastic brilliant perfect happy glad joy beautiful nice cool
    positive success successful win winning enjoy enjoyed delightful superb
    outstanding incredible like liked likes helpful useful recommend
    recommended impressive strong appreciate grateful thanks thank bien bueno
    genial excelente increible increíble perfecto feliz encanta encantó gustar
    gusta útil gracias maravilloso brillante positivo exito éxito disfrutar
    bien logro logros excelente excelente feliz contento satisfecho
    """.split()
)

NEGATIVE_WORDS: frozenset[str] = frozenset(
    """
    bad worse worst terrible awful horrible hate hated disgusting poor sad
    angry upset disappointed disappointing fail failure failed problem
    problems issue issues bug broken wrong error errors useless annoying
    frustrating slow ugly negative lose lost losing unfortunately mal malo
    peor terrible horrible odio triste enojado decepcionado decepción falla
    fallas problema problemas error errores roto lento feo negativo perder
    desafortunadamente inutil inútil molesto frustrante malo malísima pésimo
    """.split()
)
