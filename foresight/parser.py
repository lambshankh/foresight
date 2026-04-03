from datetime import date
from pathlib import Path
from lark import Lark, Transformer
from lark.exceptions import UnexpectedToken, UnexpectedCharacters
from .models import (
    Duration, Qualification, Training, HoldsRecord, ScheduledTraining,
    Staff, TimeWindow, Requirements, Task, ForesightModel,
)


class ForesightError(Exception):
    def __init__(self, message, line=None, column=None):
        self.line = line
        self.column = column
        super().__init__(message)


class ForesightTransformer(Transformer):

    def DATE(self, t):
        y, m, d = str(t).split("-")
        return date(int(y), int(m), int(d))

    def IDENTIFIER(self, t):        return str(t)
    def STRING(self, t):            return str(t)[1:-1]
    def INT(self, t):               return int(t)
    def NUMBER(self, t):            return float(t)
    def duration_unit(self, i):     return str(i[0])
    def duration(self, i):          return Duration(i[0], i[1])

    def CATEGORY_LIT(self, t):      return str(t)
    def RENEWAL_LIT(self, t):       return str(t)
    def EXPERIENCE_NONE(self, t):   return None
    def TRAINING_TYPE_LIT(self, t): return str(t)
    def ROLE_LIT(self, t):          return str(t)
    def MAINT_TYPE_LIT(self, t):    return str(t)
    def PREFER_LIT(self, t):        return str(t)
    def DURATION_UNIT_LIT(self, t): return str(t)

    def category_value(self, i):         return i[0]
    def renewal_value(self, i):          return i[0]
    def experience_value(self, i):       return i[0]
    def training_type_value(self, i):    return i[0]
    def role_value(self, i):             return i[0]
    def maintenance_type_value(self, i): return i[0]
    def preference_value(self, i):       return i[0]
    def empty_prereqs(self, i):          return []
    def prereq_ids(self, i):             return list(i)

    def qual_category(self, i):        return ("category", i[0])
    def qual_regulatory_body(self, i): return ("regulatory_body", i[0])
    def qual_issuing_body(self, i):    return ("issuing_body", i[0])
    def qual_validity(self, i):        return ("validity", i[0])
    def qual_recency(self, i):         return ("recency", i[0])
    def qual_renewal(self, i):         return ("renewal", i[0])
    def qual_prerequisites(self, i):   return ("prerequisites", i[0])
    def qual_min_experience(self, i):  return ("min_experience", i[0])
    def qual_description(self, i):     return ("description", i[0])

    def qualification_block(self, i):
        q = Qualification(name=i[0])
        for k, v in i[1:]: setattr(q, k, v)
        return ("qualification", q)

    def train_renews(self, i):   return ("renews", i[0])
    def train_type(self, i):     return ("type", i[0])

    def training_block(self, i):
        t = Training(name=i[0], renews="")
        for k, v in i[1:]: setattr(t, k, v)
        return ("training", t)

    def staff_role(self, i):         return ("role", i[0])
    def staff_base(self, i):         return ("base", i[0])
    def staff_career_start(self, i): return ("career_start", i[0])
    def staff_day_rate(self, i):     return ("day_rate", i[0])
    def holds_issued(self, i):     return ("issued", i[0])
    def holds_last_used(self, i): return ("last_used", i[0])

    def holds_block(self, i):
        fields = dict(i[1:])
        return HoldsRecord(
            qualification=i[0],
            issued=fields.get("issued"),
            last_used=fields.get("last_used"),
        )

    def staff_holds(self, i):        return ("holds", i[0])
    def training_scheduled(self, i): return ("scheduled", i[0])

    def staff_training_block(self, i):
        scheduled = next((v for k, v in i[1:] if k == "scheduled"), None)
        return ScheduledTraining(training=i[0], scheduled=scheduled)

    def staff_training(self, i): return ("training", i[0])

    def staff_block(self, i):
        s = Staff(name=i[0], role="")
        for item in i[1:]:
            if not isinstance(item, tuple): continue
            k, v = item
            if k == "holds":        s.holds.append(v)
            elif k == "training":   s.trainings.append(v)
            else:                   setattr(s, k, v)
        return ("staff", s)

    def task_description(self, i): return ("description", i[0])
    def task_type(self, i):        return ("type", i[0])
    def task_aircraft(self, i):    return ("aircraft", i[0])
    def task_location(self, i):    return ("location", i[0])
    def window_start(self, i):     return ("start", i[0])
    def window_end(self, i):       return ("end", i[0])

    def window_block(self, i):
        d = dict(i)
        return TimeWindow(start=d["start"], end=d["end"])

    def task_window(self, i):       return ("window", i[0])
    def req_qualification(self, i): return ("qualification", i[0])
    def req_role(self, i):          return ("role", i[0])
    def req_min_staff(self, i):     return ("min_staff", i[0])

    def requires_block(self, i):
        r = Requirements()
        for k, v in i:
            if k == "qualification": r.qualifications.append(v)
            elif k == "role":        r.role = v
            elif k == "min_staff":   r.min_staff = v
        return r

    def task_requires(self, i): return ("requires", i[0])
    def task_prefer(self, i):   return ("prefer", i[0])

    def task_block(self, i):
        t = Task(name=i[0])
        for item in i[1:]:
            if isinstance(item, tuple): setattr(t, item[0], item[1])
        return ("task", t)

    def subsumption_rule(self, i):
        return (str(i[0]), str(i[1]))   # (subsuming, subsumed)

    def subsumption_block(self, i):
        return ("subsumption", list(i))

    def block(self, i): return i[0]

    def start(self, i):
        model = ForesightModel()
        for btype, obj in i:
            if btype == "qualification":  model.qualifications[obj.name] = obj
            elif btype == "training":     model.trainings[obj.name] = obj
            elif btype == "staff":        model.staff[obj.name] = obj
            elif btype == "task":         model.tasks[obj.name] = obj
            elif btype == "subsumption":
                for subsuming, subsumed in obj:
                    model.subsumptions.setdefault(subsuming, set()).add(subsumed)
        return model


_GRAMMAR = Path(__file__).parent / "grammar.lark"
_parser = Lark(_GRAMMAR.read_text(), parser="earley", propagate_positions=True)
_transformer = ForesightTransformer()

def _validate_references(model: ForesightModel):
    errors = []
    qual_names = set(model.qualifications)
    training_names = set(model.trainings)

    for q in model.qualifications.values():
        for p in q.prerequisites:
            if p not in qual_names:
                errors.append(
                    f"qualification '{q.name}': prerequisite '{p}' is not defined")

    completed = set()

    def _has_cycle(name, path):
        if name in path:
            cycle = " -> ".join(list(path) + [name])
            errors.append(f"circular prerequisite chain: {cycle}")
            return True
        if name in completed or name not in qual_names:
            return False
        path.add(name)
        for p in model.qualifications[name].prerequisites:
            if _has_cycle(p, path):
                return True
        path.discard(name)
        completed.add(name)
        return False

    for name in qual_names:
        _has_cycle(name, set())

    for t in model.trainings.values():
        if t.renews and t.renews not in qual_names:
            errors.append(
                f"training '{t.name}': renews qualification '{t.renews}' which is not defined")

    for s in model.staff.values():
        for h in s.holds:
            if h.qualification not in qual_names:
                errors.append(
                    f"staff '{s.name}': holds qualification '{h.qualification}' which is not defined")

    for s in model.staff.values():
        for st in s.trainings:
            if st.training not in training_names:
                errors.append(
                    f"staff '{s.name}': scheduled training '{st.training}' is not defined")

    for t in model.tasks.values():
        if t.requires:
            for qn in t.requires.qualifications:
                if qn not in qual_names:
                    errors.append(
                        f"task '{t.name}': requires qualification '{qn}' which is not defined")

    for t in model.tasks.values():
        if t.window and t.window.start > t.window.end:
            errors.append(
                f"task '{t.name}': window start {t.window.start} is after end {t.window.end}")

    for subsuming, subsumed_set in model.subsumptions.items():
        if subsuming not in qual_names:
            errors.append(f"subsumption: '{subsuming}' is not a defined qualification")
        for subsumed in subsumed_set:
            if subsumed not in qual_names:
                errors.append(
                    f"subsumption: '{subsumed}' (subsumed by '{subsuming}') is not a defined qualification")

    sub_completed = set()

    def _sub_cycle(name, path):
        if name in path:
            errors.append("circular subsumption chain: " + " -> ".join(list(path) + [name]))
            return True
        if name in sub_completed or name not in model.subsumptions:
            return False
        path.add(name)
        for target in model.subsumptions[name]:
            if _sub_cycle(target, path):
                return True
        path.discard(name)
        sub_completed.add(name)
        return False

    for name in list(model.subsumptions):
        _sub_cycle(name, set())

    if errors:
        raise ForesightError("Semantic errors:\n  " + "\n  ".join(errors))


def _format_lark_error(e):
    line = getattr(e, "line", None)
    col = getattr(e, "column", None)
    loc = f"line {line}" if line else "unknown location"
    if col:
        loc += f", column {col}"

    if isinstance(e, UnexpectedToken):
        expected = sorted(e.expected) if e.expected else []
        exp_str = ", ".join(expected) if expected else "unknown"
        found = repr(e.token) if e.token else "end of input"
        msg = f"{loc}: expected {exp_str}, found {found}"
    else:
        found = repr(e.char) if hasattr(e, "char") else "unexpected character"
        allowed = sorted(e.allowed) if hasattr(e, "allowed") and e.allowed else []
        if allowed:
            msg = f"{loc}: expected {', '.join(allowed)}, found {found}"
        else:
            msg = f"{loc}: unexpected {found}"

    return msg, line, col


def parse_foresight(text: str) -> ForesightModel:
    try:
        tree = _parser.parse(text)
    except (UnexpectedToken, UnexpectedCharacters) as e:
        msg, line, col = _format_lark_error(e)
        raise ForesightError(msg, line=line, column=col) from e

    model = _transformer.transform(tree)
    _validate_references(model)
    return model

def parse_file(filepath: str) -> ForesightModel:
    return parse_foresight(Path(filepath).read_text())