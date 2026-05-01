# Expression Engine — Contracts

**Authoritative reference for parallel implementation. Do not change without coordination.**

## Grammar (locked)

```
expression := or_expr
or_expr    := and_expr ( "OR" and_expr )*
and_expr   := not_expr ( "AND" not_expr )*
not_expr   := "NOT" not_expr | comparison
comparison := add_expr ( ( ">" | "<" | ">=" | "<=" | "==" | "!=" |
                           "crosses_above" | "crosses_below" ) add_expr )?
add_expr   := mul_expr ( ( "+" | "-" ) mul_expr )*
mul_expr   := unary ( ( "*" | "/" ) unary )*
unary      := "-" unary | atom
atom       := NUMBER
            | IDENT  ( "." IDENT )*  ( "(" arg_list? ")" )?  ( "[" INTEGER "]" "." IDENT )?
            | "(" expression ")"
arg_list   := expression ( "," expression )*

Tokens:
  NUMBER     := digits ( "." digits )?
  IDENT      := [a-zA-Z_][a-zA-Z0-9_]*
  INTEGER    := "-"? digits
  KEYWORDS   := AND OR NOT crosses_above crosses_below
                within any_of all_of true false
  TIMEFRAMES := 1m 5m 15m 30m 1h 4h 1d
  COMMENT    := "//" ... newline
```

## Identifier resolution order

When an `IDENT` is encountered:
1. Is it a **timeframe** (1m, 5m, etc.)? → must be followed by `.IDENT(...)` → `TimeframedFeature` node
2. Is it a **keyword** (AND, OR, NOT, true, false, crosses_above, crosses_below, within, any_of, all_of)? → handled at parse layer
3. Is it a **variable name** (provided to validator via context)? → `VariableRef` node
4. Is it a **non-tf feature** (`session.is_open`, `orb.high`, `prior_day.close`, `bar`, `volume`, `close`, etc.)? → `FeatureRef` node
5. Otherwise → unknown identifier (validator error)

## AST node types (locked — `ast_nodes.py` must export exactly these)

```python
@dataclass(frozen=True)
class NumberLit:
    value: float

@dataclass(frozen=True)
class BoolLit:
    value: bool

@dataclass(frozen=True)
class VariableRef:
    name: str

@dataclass(frozen=True)
class FeatureRef:
    """Non-timeframed feature like session.is_open, orb.high(15), bar[-3].close."""
    path: tuple[str, ...]              # ("session", "is_open") or ("orb", "high")
    args: tuple["AstNode", ...]        # () or (NumberLit(15),)
    bar_offset: int | None = None      # for bar[-3].close pattern; None if not used
    bar_field: str | None = None       # "close" in bar[-3].close

@dataclass(frozen=True)
class TimeframedFeature:
    """Feature bound to a timeframe like 5m.ema(9) or 1h.rsi(14)."""
    timeframe: str                     # "5m"
    name: str                          # "ema"
    args: tuple["AstNode", ...]

@dataclass(frozen=True)
class UnaryOp:
    op: str                            # "NOT" or "-"
    operand: "AstNode"

@dataclass(frozen=True)
class BinaryOp:
    op: str                            # "AND" "OR" ">" "<" ">=" "<=" "==" "!=" "+" "-" "*" "/"
                                       # "crosses_above" "crosses_below"
    left: "AstNode"
    right: "AstNode"

@dataclass(frozen=True)
class FunctionCall:
    """For within(a, b, c) / any_of(...) / all_of(...) — keyword-style functions."""
    name: str
    args: tuple["AstNode", ...]

# Union type alias — every parser-produced node is one of these
AstNode = NumberLit | BoolLit | VariableRef | FeatureRef | TimeframedFeature | UnaryOp | BinaryOp | FunctionCall
```

## ValidatedAst

```python
@dataclass(frozen=True)
class ValidatedAst:
    root: AstNode
    feature_requirements: tuple["FeatureRef" | "TimeframedFeature", ...]
    variables_used: tuple[str, ...]
```

## CompiledExpr

```python
@dataclass(frozen=True)
class CompiledExpr:
    """Canonical, picklable, immutable. Identical structure to ValidatedAst.root
       but with all feature/variable references resolved to indices into the
       FeatureSnapshot for fast evaluation."""
    root: AstNode               # for v1, same shape as ValidatedAst
    feature_index: dict[str, int]   # feature key -> snapshot column
```

## FeatureSnapshot (passed at evaluation time)

```python
@dataclass(frozen=True)
class FeatureSnapshot:
    """Provided by the runtime/backtest. Contains current + recent bar values
       for all features the strategy declared as required."""
    timestamp: datetime
    values: dict[str, float | bool]            # feature key -> current value
    history: dict[str, tuple[float, ...]]      # feature key -> NEWEST-FIRST: (current, previous, prev-1, ...)
    variables: dict[str, float | bool]         # resolved variable values (computed before entry eval)
```

**History ordering convention (locked, runtime contract):**
- `history[key]` is a tuple ordered **newest-first**: index 0 is the current bar's value, index 1 is the previous bar, index 2 is two bars ago, etc.
- `crosses_above` evaluates `history[left][1] <= history[right][1]` AND `history[left][0] > history[right][0]`.
- `bar[-N].field` evaluates to `history["bar.<field>"][N]` (so `bar[-1].close` is one bar ago = index 1).
- The runtime layer (Slice 11) is responsible for assembling history tuples in this order before calling `evaluate()`.

## Public service interface (`__init__.py`)

```python
def parse(src: str) -> AstNode: ...
def validate(ast: AstNode, catalog: FeatureCatalog, variable_names: Iterable[str] = ()) -> ValidatedAst: ...
def compile(validated: ValidatedAst) -> CompiledExpr: ...
def evaluate(compiled: CompiledExpr, snapshot: FeatureSnapshot) -> bool | float: ...
def extract_features(validated: ValidatedAst) -> list[FeatureRef | TimeframedFeature]: ...
def mirror_long_to_short(src: str) -> str: ...
```

## Errors (`errors.py`)

```python
class ExpressionError(Exception): ...
class ParseError(ExpressionError):
    line: int
    col: int
    message: str

class ValidationError(ExpressionError):
    issues: list[ValidationIssue]   # each has level (error|warning), message, location

class EvalError(ExpressionError): ...
```

## Feature catalog (`features.py`)

```python
@dataclass(frozen=True)
class FeatureSpec:
    name: str                          # "ema"
    namespace: str                     # "" for tf-features, "session" / "orb" / "prior_day" / "bar" for non-tf
    is_timeframed: bool
    arity: int                         # number of positional args; -1 for variadic
    arg_names: tuple[str, ...]
    arg_defaults: tuple[float | int, ...]
    return_type: str                   # "float" or "bool"
    description: str

class FeatureCatalog:
    def get(self, key: str) -> FeatureSpec | None: ...   # key: "5m.ema" or "session.is_open"
    def all(self) -> list[FeatureSpec]: ...
```

The seeded catalog must include all 50 features from the v4 mockup palette categorized as: trend / momentum / volatility / volume / bb / time / bar.

## Mirror operator inversion table (`mirror.py`)

Long → Short inversions:
- `crosses_above` ↔ `crosses_below`
- `>` ↔ `<`, `>=` ↔ `<=`
- `bb_lower` ↔ `bb_upper`
- `donchian_low` ↔ `donchian_high`
- `kc_lower` ↔ `kc_upper`
- `orb.high` ↔ `orb.low`
- `prior_day.high` ↔ `prior_day.low`

`==`, `!=`, `AND`, `OR`, `NOT`, math operators are NOT inverted.

If the source has a `// ` header comment, replace it with `// Auto-mirrored from long entry — review and adjust\n`. Otherwise prepend that comment.

Mirror operates on text via tokenizer, NOT on AST — implementation can re-tokenize and emit, OR walk a parsed AST and pretty-print. For v1, text-level token replace is fine since the grammar is small.

## Anti-rules (enforced)

1. **No `import ast` anywhere in `expression_engine/`.** A test asserts this.
2. **No `eval` / `exec` / `compile` (Python builtins) on user text.** A test asserts this via grep.
3. **AST nodes are `@dataclass(frozen=True)`** — immutable, picklable, hashable.
4. **Every error from parse/validate carries line and column info.** Tests verify error positions for malformed inputs.
