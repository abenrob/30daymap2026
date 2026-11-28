# Classifying cyclist comments (Baromètre vélo 2025, Grenoble metro)

Each input line is JSON: `{"id", "file", "text"}`.
- `file` is the map layer the cyclist dropped the point on: `neg` = "point to improve as a priority", `pos` = "improvement noticed in the last 2 years". This is only the starting assumption. Some people misunderstood the layer (complaining on a `pos` point, or praising on a `neg` point). Judge from the TEXT; fall back on `file` only when the text gives no signal (e.g. a bare place name).

For every input line, output exactly one JSON line:
`{"id": "...", "label": "...", "valence": "...", "vivid": 0}`

## label: exactly one of these French nouns (the dominant feeling)
- PEUR: fear, feeling in danger oneself ("dangereux", "on se fait frôler", "j'ai failli")
- COLÈRE: anger, outrage, insults, "inadmissible", "scandaleux", lots of !!!
- AGACEMENT: irritation at a recurring nuisance (cars parked on the lane, detours, waiting)
- INQUIÉTUDE: worry, especially for others (children, school route, "un jour il y aura un accident")
- LASSITUDE: weariness, resignation ("toujours pas", "depuis des années", "rien ne change")
- INCOMPRÉHENSION: bafflement at absurd design ("piste qui s'arrête net", "aucune logique")
- CONSTAT: neutral factual description with no emotional colour (problem or improvement stated flatly)
- SOUHAIT: a request or suggestion ("il faudrait", "créer une piste")
- SOULAGEMENT: relief that something got better or less bad ("enfin", "moins dangereux qu'avant")
- SATISFACTION: calm approval ("bien", "pratique", "agréable", "bon aménagement")
- JOIE: enthusiasm ("super", "génial", "top", "un plaisir")
- GRATITUDE: thanks, congratulations ("merci", "bravo")

## valence: one of
- `neg`: the place is described as a problem
- `pos`: the place is described as good / improved
- `mixed`: the comment clearly says both (e.g. "new lane, but the exit is dangerous"; "well signed and safe, though I hate riding it")

## vivid: 0, 1 or 2
2 = a short (ideally under 120 characters), striking, self-contained quote that would work on screen in a social video: concrete, emotional, no names of private people. Be strict: at most about 3% of lines get 2. 1 = decent. 0 = everything else.

## Rules
- One output line per input line, same ids, nothing skipped, no extra keys.
- Write output with a script or heredoc to the output file, in chunks if needed. Valid JSONL only.
- Do not invent: classify only what the text says.
