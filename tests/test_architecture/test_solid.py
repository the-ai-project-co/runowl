"""Tests for SOLID / architecture checks (paid tier)."""

from architecture.checks import (
    check_deep_nesting,
    check_dependency_inversion,
    check_feature_envy,
    check_interface_segregation,
    check_liskov_substitution,
    check_long_methods,
    check_open_closed,
    check_single_responsibility,
)
from architecture.models import ArchCheckType
from architecture.solid import run_solid_scan
from github.models import DiffHunk, FileDiff


def _diff(filename: str, added_lines: list[str], status: str = "added") -> FileDiff:
    raw = [f"+{line}" for line in added_lines]
    hunk = DiffHunk(
        header=f"@@ -0,0 +1,{len(added_lines)} @@",
        old_start=0,
        old_lines=0,
        new_start=1,
        new_lines=len(added_lines),
        lines=raw,
    )
    return FileDiff(
        filename=filename,
        status=status,
        additions=len(added_lines),
        deletions=0,
        hunks=[hunk],
    )


# ── Single Responsibility ──────────────────────────────────────────────────────


class TestSingleResponsibility:
    def test_detects_mixed_http_and_db(self) -> None:
        diff = _diff(
            "src/views.py",
            [
                "def create_user(request):",
                "    data = request.json",
                "    user = User.objects.create(**data)",
                "    return jsonify(user.to_dict())",
            ],
        )
        hits = check_single_responsibility(diff)
        assert hits
        assert any(h.check == ArchCheckType.SINGLE_RESPONSIBILITY for h in hits)

    def test_detects_god_class(self) -> None:
        # 11 public methods = god class
        lines = ["class BigService:"]
        for i in range(11):
            lines += [f"    def method_{i}(self):", "        pass"]
        diff = _diff("src/service.py", lines)
        hits = check_single_responsibility(diff)
        assert any("god object" in h.message for h in hits)

    def test_clean_view_not_flagged(self) -> None:
        diff = _diff(
            "src/views.py",
            [
                "def get_users(request):",
                "    users = user_service.list_all()",
                "    return jsonify(users)",
            ],
        )
        hits = check_single_responsibility(diff)
        # No DB concern mixed with HTTP — should not flag mixed concerns
        mixed = [h for h in hits if "mixes HTTP" in h.message]
        assert not mixed

    def test_all_hits_are_paid(self) -> None:
        diff = _diff(
            "src/views.py",
            ["def f(request):", "    x = Model.objects.get(id=1)", "    return jsonify(x)"],
        )
        hits = check_single_responsibility(diff)
        assert all(not h.is_free for h in hits)


# ── Open/Closed Principle ─────────────────────────────────────────────────────


class TestOpenClosed:
    def test_detects_long_elif_chain(self) -> None:
        lines = [
            "if type(shape) == 'circle':",
            "    draw_circle(shape)",
            "elif type(shape) == 'square':",
            "    draw_square(shape)",
            "elif type(shape) == 'triangle':",
            "    draw_triangle(shape)",
            "elif type(shape) == 'rectangle':",
            "    draw_rectangle(shape)",
            "elif type(shape) == 'hexagon':",
            "    draw_hexagon(shape)",
            "else:",
            "    raise ValueError()",
        ]
        diff = _diff("src/drawing.py", lines)
        hits = check_open_closed(diff)
        assert hits
        assert hits[0].check == ArchCheckType.OPEN_CLOSED

    def test_short_if_not_flagged(self) -> None:
        lines = [
            "if x == 'a':",
            "    do_a()",
            "elif x == 'b':",
            "    do_b()",
        ]
        diff = _diff("src/dispatch.py", lines)
        assert not check_open_closed(diff)

    def test_all_hits_are_paid(self) -> None:
        lines = [f"elif type(x) == 'type{i}':" for i in range(6)]
        lines.insert(0, "if type(x) == 'type_start':")
        diff = _diff("src/dispatch.py", lines)
        hits = check_open_closed(diff)
        assert all(not h.is_free for h in hits)


# ── Liskov Substitution ───────────────────────────────────────────────────────


class TestLiskovSubstitution:
    def test_detects_multi_isinstance(self) -> None:
        diff = _diff(
            "src/shapes.py",
            [
                "class Renderer:",
                "    def draw(self, shape):",
                "        if isinstance(shape, (Circle, Square, Triangle)):",
                "            shape.render()",
            ],
        )
        hits = check_liskov_substitution(diff)
        assert any(h.check == ArchCheckType.LISKOV_SUBSTITUTION for h in hits)

    def test_detects_noop_override(self) -> None:
        diff = _diff(
            "src/animals.py",
            [
                "class Dog(Animal):",
                "    def speak(self):",
                "        pass",
            ],
        )
        hits = check_liskov_substitution(diff)
        assert any("No-op" in h.message for h in hits)

    def test_all_hits_are_paid(self) -> None:
        diff = _diff(
            "src/shapes.py",
            [
                "class MyClass:",
                "    def do(self):",
                "        if isinstance(obj, (A, B, C)):",
                "            pass",
            ],
        )
        hits = check_liskov_substitution(diff)
        assert all(not h.is_free for h in hits)


# ── Interface Segregation ─────────────────────────────────────────────────────


class TestInterfaceSegregation:
    def test_detects_fat_interface(self) -> None:
        lines = ["class IFatService(ABC):"]
        for i in range(8):
            lines += ["    @abstractmethod", f"    def method_{i}(self): ..."]
        diff = _diff("src/interfaces.py", lines)
        hits = check_interface_segregation(diff)
        assert any(h.check == ArchCheckType.INTERFACE_SEGREGATION for h in hits)

    def test_detects_stub_implementation(self) -> None:
        diff = _diff(
            "src/impl.py",
            [
                "class ConcreteService(BaseService):",
                "    def unused_method(self):",
                "        raise NotImplementedError",
            ],
        )
        hits = check_interface_segregation(diff)
        assert any("Stub" in h.message for h in hits)

    def test_small_interface_not_flagged(self) -> None:
        lines = ["class ISmall(ABC):", "    @abstractmethod", "    def run(self): ..."]
        diff = _diff("src/interfaces.py", lines)
        hits = check_interface_segregation(diff)
        fat = [h for h in hits if "Large interface" in h.message]
        assert not fat

    def test_all_hits_are_paid(self) -> None:
        lines = ["class IFat(ABC):"]
        for i in range(8):
            lines += ["    @abstractmethod", f"    def m{i}(self): ..."]
        diff = _diff("src/interfaces.py", lines)
        hits = check_interface_segregation(diff)
        assert all(not h.is_free for h in hits)


# ── Dependency Inversion ──────────────────────────────────────────────────────


class TestDependencyInversion:
    def test_detects_hardcoded_instantiation(self) -> None:
        diff = _diff(
            "src/service.py",
            [
                "class OrderService:",
                "    def __init__(self):",
                "        self.repo = SqlOrderRepository()",
            ],
        )
        hits = check_dependency_inversion(diff)
        assert hits
        assert hits[0].check == ArchCheckType.DEPENDENCY_INVERSION

    def test_injected_dependency_not_flagged(self) -> None:
        diff = _diff(
            "src/service.py",
            [
                "class OrderService:",
                "    def __init__(self, repo: OrderRepository):",
                "        self.repo = repo",
            ],
        )
        assert not check_dependency_inversion(diff)

    def test_all_hits_are_paid(self) -> None:
        diff = _diff(
            "src/service.py",
            ["class S:", "    def __init__(self):", "        self.db = PostgresDB()"],
        )
        hits = check_dependency_inversion(diff)
        assert all(not h.is_free for h in hits)


# ── Long Methods ──────────────────────────────────────────────────────────────


class TestLongMethods:
    def test_detects_long_method(self) -> None:
        lines = ["def big_function(x):"]
        lines += [f"    step_{i} = process(x)" for i in range(45)]
        diff = _diff("src/utils.py", lines)
        hits = check_long_methods(diff)
        assert hits
        assert hits[0].check == ArchCheckType.LONG_METHOD

    def test_short_method_not_flagged(self) -> None:
        diff = _diff("src/utils.py", ["def add(a, b):", "    return a + b"])
        assert not check_long_methods(diff)

    def test_all_hits_are_paid(self) -> None:
        lines = ["def big(x):"] + [f"    x = x + {i}" for i in range(45)]
        diff = _diff("src/utils.py", lines)
        hits = check_long_methods(diff)
        assert all(not h.is_free for h in hits)


# ── Deep Nesting ──────────────────────────────────────────────────────────────


class TestDeepNesting:
    def test_detects_deep_nesting(self) -> None:
        # 5 levels of 4-space indentation = 20 spaces
        line = "                    result = compute(x)"
        diff = _diff("src/logic.py", [line])
        hits = check_deep_nesting(diff)
        assert hits
        assert hits[0].check == ArchCheckType.DEEP_NESTING

    def test_shallow_nesting_not_flagged(self) -> None:
        # 2 levels = 8 spaces
        diff = _diff("src/logic.py", ["        x = 1"])
        assert not check_deep_nesting(diff)

    def test_all_hits_are_paid(self) -> None:
        line = "                        deeply_nested = True"
        diff = _diff("src/logic.py", [line])
        hits = check_deep_nesting(diff)
        assert all(not h.is_free for h in hits)


# ── Feature Envy ──────────────────────────────────────────────────────────────


class TestFeatureEnvy:
    def test_detects_deep_chain(self) -> None:
        diff = _diff("src/handler.py", ["    total = order.customer.address.city.zip_code"])
        hits = check_feature_envy(diff)
        assert hits
        assert hits[0].check == ArchCheckType.FEATURE_ENVY

    def test_short_chain_not_flagged(self) -> None:
        diff = _diff("src/handler.py", ["    name = user.profile.name"])
        assert not check_feature_envy(diff)

    def test_all_hits_are_paid(self) -> None:
        diff = _diff("src/handler.py", ["    x = a.b.c.d.e"])
        hits = check_feature_envy(diff)
        assert all(not h.is_free for h in hits)


# ── SOLID Scanner integration ─────────────────────────────────────────────────


class TestRunSolidScan:
    def test_empty_diffs_returns_empty_report(self) -> None:
        report = run_solid_scan([])
        assert not report.has_issues
        assert report.files_scanned == 0

    def test_skips_removed_files(self) -> None:
        lines = ["def big(x):"] + [f"    x = x + {i}" for i in range(45)]
        diff = _diff("src/utils.py", lines, status="removed")
        report = run_solid_scan([diff])
        assert not report.has_issues

    def test_skips_non_code_files(self) -> None:
        diff = _diff("README.md", ["# Hello World"])
        report = run_solid_scan([diff])
        assert report.files_scanned == 0

    def test_counts_files_scanned(self) -> None:
        diffs = [_diff("src/a.py", ["x = 1"]), _diff("src/b.py", ["y = 2"])]
        report = run_solid_scan(diffs)
        assert report.files_scanned == 2

    def test_deduplicates_hits(self) -> None:
        diff = _diff("src/handler.py", ["    total = order.customer.address.city.zip_code"])
        report = run_solid_scan([diff, diff])
        keys = [(h.file, h.line, h.check) for h in report.hits]
        assert len(keys) == len(set(keys))

    def test_by_check_filter(self) -> None:
        diff = _diff("src/handler.py", ["    total = order.customer.address.city.zip_code"])
        report = run_solid_scan([diff])
        envy_hits = report.by_check(ArchCheckType.FEATURE_ENVY)
        assert envy_hits
        assert all(h.check == ArchCheckType.FEATURE_ENVY for h in envy_hits)

    def test_all_hits_are_paid_tier(self) -> None:
        diff = _diff("src/handler.py", ["    total = order.customer.address.city.zip_code"])
        report = run_solid_scan([diff])
        assert report.has_issues
        assert all(not h.is_free for h in report.hits)

    def test_hit_citation_format(self) -> None:
        diff = _diff("src/handler.py", ["    total = order.customer.address.city.zip_code"])
        report = run_solid_scan([diff])
        assert report.hits[0].citation == "src/handler.py:1"
