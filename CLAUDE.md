# GenesisGeo Project Memory

---

## Module Reference

| Module | Purpose | Key Class(es) |
|--------|---------|---------------|
| `api.py` | Solver interface | `GeometricSolver`, `GeometricSolverBuilder` |
| `proof.py` | Proof state management | `ProofState` |
| `agent/ddarn.py` | DDARN symbolic reasoning | `DDARNAgent` |
| `agent/lm.py` | LLM auxiliary construction | `LMAgent` |
| `agent/vlm.py` | Vision-language model agent | `VLMAgent` |
| `generation/pipeline.py` | Generation orchestrator | `ProblemPipeline` |
| `generation/sampler.py` | Geometry construction sampling | `ProblemSampler` |
| `generation/point_naming.py` | Point naming management | `PointNaming` |
| `generation/filter.py` | Goal filtering | `GoalFilter` |
| `generation/worker.py` | Per-problem processing | `ProblemWorker` |
| `generation/writer.py` | Data writing & image rendering | `Writer` |
| `generation/constructions.py` | Construction type constants | — |
| `generation/statistics.py` | Generation statistics | `Statistics` |
| `generation/auxiliary/` | Auxiliary point discovery | — |

---

## Geometry Problem Data Format

### Problem Definition (fl_problem)

```
constructions ? goal
```

**Example:**
```
a b c = triangle a b c; d = free d; e = on_circum e c b d, angle_bisector e a d b ? eqangle b d b e c d c e
```

### Construction Syntax

The construction part consists of multiple **clauses** separated by semicolons `;`:

```
clause1; clause2; clause3; ...
```

Each clause has the format:
```
point_names = construction_type [args]
```

- **Point names**: one or more points separated by spaces (e.g. `a b c` or `d`)
- **Construction type**: may have multiple, separated by commas `,`
- **Args**: reference points required by the construction

### Example Breakdown

```
a b c = triangle a b c; d = free d; e = on_circum e c b d, angle_bisector e a d b ? eqangle b d b e c d c e
```

| Clause | Points | Construction | Meaning |
|--------|--------|-------------|---------|
| `a b c = triangle a b c` | a, b, c | triangle | Triangle ABC |
| `d = free d` | d | free | D is a free point |
| `e = on_circum e c b d, angle_bisector e a d b` | e | on_circum, angle_bisector | E on circumcircle of CBD and angle bisector of ∠ADB |

**Goal**: `eqangle b d b e c d c e` — prove ∠BDE = ∠DCE

### Predicates

Construction language (e.g. `triangle`, `on_circum`) is translated into predicate language for symbolic reasoning. Predicates describe both premises and goals.

#### Common Predicates

| Predicate | Args | Meaning |
|-----------|------|---------|
| `coll a b c` | 3 | A, B, C are collinear |
| `para a b c d` | 4 | AB ∥ CD |
| `perp a b c d` | 4 | AB ⊥ CD |
| `cong a b c d` | 4 | AB = CD |
| `cyclic a b c d` | 4 | A, B, C, D are concyclic |
| `eqangle a b c d e f g h` | 8 | ∠(AB,CD) = ∠(EF,GH) |
| `eqratio a b c d e f g h` | 8 | AB/CD = EF/GH |
| `simtri a b c d e f` | 6 | △ABC ∼ △DEF |
| `contri a b c d e f` | 6 | △ABC ≅ △DEF |
| `midp m a b` | 3 | M is midpoint of AB |
| `circle o a b c` | 4 | O is circumcenter of △ABC |

#### Construction-to-Predicate Translation

Constructions are translated to predicates during solving:

```
Construction: e = on_circum e c b d, angle_bisector e a d b
  ↓ translate
Predicates:  cyclic b c d e [000]
             eqangle a d d e d e b d [001]
```

### LLM Input/Output Format

#### LLM Input (llm_input_renamed)

```xml
<problem> point1 : premises ; point2 : premises ; ... ? goal </problem>
```

Premise format: `predicate args [id]`

**Example:**
```xml
<problem> a : ; b : ; c : ; d : ; e : cyclic b c d e [000] eqangle a d d e d e b d [001] ? eqangle b d b e c d c e </problem>
```

#### LLM Output (llm_output_renamed)

```xml
<proof> conclusion1 [id] rule [dep_ids] ; conclusion2 [id] rule [dep_ids] ; ... </proof>
```

**Example:**
```xml
<proof> eqangle b d b e c d c e [002] r03 [000] ; </proof>
```
