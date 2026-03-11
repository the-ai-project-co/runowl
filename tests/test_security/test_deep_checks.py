"""Tests for deep security checks (paid tier)."""

from github.models import DiffHunk, FileDiff
from security.deep_checks import (
    check_broken_access_control,
    check_cryptographic_failures,
    check_injection,
    check_jwt_auth,
    check_race_conditions,
    check_security_misconfiguration,
    check_supply_chain,
)
from security.deep_scanner import run_deep_scan


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


# ── Broken Access Control ─────────────────────────────────────────────────────


class TestBrokenAccessControl:
    def test_detects_idor_from_request_args(self) -> None:
        diff = _diff("src/views.py", ["obj = Obj.get(request.args['id'])"])
        assert check_broken_access_control(diff)

    def test_detects_missing_ownership_filter(self) -> None:
        diff = _diff("src/views.py", ["item = Item.objects.get(id=item_id)"])
        assert check_broken_access_control(diff)

    def test_safe_with_user_filter_not_flagged(self) -> None:
        diff = _diff("src/views.py", ["item = Item.objects.get(id=item_id, user=request.user)"])
        # The MISSING_AUTHZ pattern uses negative lookahead — user present means no flag
        hits = check_broken_access_control(diff)
        authz_hits = [h for h in hits if "ownership" in h.message or "broken access" in h.message]
        assert not authz_hits

    def test_all_hits_are_paid(self) -> None:
        diff = _diff("src/views.py", ["obj = Model.objects.get(id=request.args['record_id'])"])
        hits = check_broken_access_control(diff)
        assert hits
        assert all(not h.is_free for h in hits)


# ── Cryptographic Failures ────────────────────────────────────────────────────


class TestCryptographicFailures:
    def test_detects_md5(self) -> None:
        diff = _diff("src/utils.py", ["digest = hashlib.md5(data).hexdigest()"])
        assert check_cryptographic_failures(diff)

    def test_detects_sha1(self) -> None:
        diff = _diff("src/utils.py", ["h = hashlib.sha1(password.encode())"])
        assert check_cryptographic_failures(diff)

    def test_detects_ecb_mode(self) -> None:
        diff = _diff("src/crypto.py", ["cipher = AES.new(key, AES.MODE_ECB)"])
        assert check_cryptographic_failures(diff)

    def test_detects_des(self) -> None:
        diff = _diff("src/legacy.py", ["cipher = DES.new(key)"])
        assert check_cryptographic_failures(diff)

    def test_detects_hardcoded_iv(self) -> None:
        diff = _diff("src/crypto.py", ['iv = b"1234567890123456"'])
        assert check_cryptographic_failures(diff)

    def test_safe_sha256_not_flagged(self) -> None:
        diff = _diff("src/utils.py", ["digest = hashlib.sha256(data).hexdigest()"])
        assert not check_cryptographic_failures(diff)

    def test_all_hits_are_paid(self) -> None:
        diff = _diff("src/utils.py", ["h = hashlib.md5(x)"])
        hits = check_cryptographic_failures(diff)
        assert hits
        assert all(not h.is_free for h in hits)


# ── Injection (beyond SQL) ────────────────────────────────────────────────────


class TestInjection:
    def test_detects_os_system_with_input(self) -> None:
        diff = _diff("src/exec.py", ['os.system("ls " + user_input)'])
        assert check_injection(diff)

    def test_detects_subprocess_with_fstring(self) -> None:
        diff = _diff("src/exec.py", ['subprocess.run(f"cat {filename}")'])
        assert check_injection(diff)

    def test_detects_eval_with_input(self) -> None:
        diff = _diff("src/exec.py", ["result = eval(user_code + extra)"])
        assert check_injection(diff)

    def test_detects_nosql_injection(self) -> None:
        diff = _diff("src/db.py", ["result = col.find({'name': request.args['name']})"])
        assert check_injection(diff)

    def test_safe_subprocess_list_not_flagged(self) -> None:
        diff = _diff("src/exec.py", ['subprocess.run(["ls", "-la"], shell=False)'])
        assert not check_injection(diff)

    def test_all_hits_are_paid(self) -> None:
        diff = _diff("src/exec.py", ['os.system("rm " + path)'])
        hits = check_injection(diff)
        assert hits
        assert all(not h.is_free for h in hits)


# ── JWT / Auth Failures ────────────────────────────────────────────────────────


class TestJWTAuth:
    def test_detects_none_algorithm(self) -> None:
        diff = _diff("src/auth.py", ['token = jwt.decode(t, algorithms=["none"])'])
        assert check_jwt_auth(diff)

    def test_detects_verify_false(self) -> None:
        diff = _diff("src/auth.py", ["payload = jwt.decode(token, verify=False)"])
        assert check_jwt_auth(diff)

    def test_detects_weak_jwt_secret(self) -> None:
        diff = _diff("src/auth.py", ['token = jwt.encode(payload, "secret", algorithm="HS256")'])
        assert check_jwt_auth(diff)

    def test_detects_jwt_no_expiry(self) -> None:
        diff = _diff("src/auth.py", ['token = jwt.encode({"user_id": uid}, key)'])
        assert check_jwt_auth(diff)

    def test_detects_session_fixation(self) -> None:
        diff = _diff("src/auth.py", ['session["user_id"] = user.id'])
        assert check_jwt_auth(diff)

    def test_all_hits_are_paid(self) -> None:
        diff = _diff("src/auth.py", ['jwt.decode(t, algorithms=["none"])'])
        hits = check_jwt_auth(diff)
        assert hits
        assert all(not h.is_free for h in hits)


# ── Security Misconfiguration ─────────────────────────────────────────────────


class TestSecurityMisconfiguration:
    def test_detects_cors_wildcard(self) -> None:
        diff = _diff("src/app.py", ['allow_origins=["*"]'])
        assert check_security_misconfiguration(diff)

    def test_detects_debug_true(self) -> None:
        diff = _diff("src/settings.py", ["DEBUG = True"])
        assert check_security_misconfiguration(diff)

    def test_detects_app_run_debug(self) -> None:
        diff = _diff("src/app.py", ['app.run(host="0.0.0.0", debug=True)'])
        assert check_security_misconfiguration(diff)

    def test_safe_debug_false_not_flagged(self) -> None:
        diff = _diff("src/settings.py", ["DEBUG = False"])
        assert not check_security_misconfiguration(diff)

    def test_all_hits_are_paid(self) -> None:
        diff = _diff("src/app.py", ['origins=["*"]'])
        hits = check_security_misconfiguration(diff)
        assert hits
        assert all(not h.is_free for h in hits)


# ── Race Conditions ───────────────────────────────────────────────────────────


class TestRaceConditions:
    def test_detects_toctou_pattern(self) -> None:
        diff = _diff(
            "src/files.py",
            [
                "if os.path.exists(path):",
                "    with open(path) as f:",
                "        data = f.read()",
            ],
        )
        assert check_race_conditions(diff)

    def test_detects_unsync_shared_state(self) -> None:
        diff = _diff("src/counter.py", ["self.count += 1"])
        assert check_race_conditions(diff)

    def test_all_hits_are_paid(self) -> None:
        diff = _diff("src/counter.py", ["self.total += amount"])
        hits = check_race_conditions(diff)
        assert hits
        assert all(not h.is_free for h in hits)


# ── Supply Chain ──────────────────────────────────────────────────────────────


class TestSupplyChain:
    def test_detects_typosquat_package(self) -> None:
        diff = _diff("requirements.txt", ["requets==2.28.0"])
        assert check_supply_chain(diff)

    def test_detects_eval_of_network_content(self) -> None:
        diff = _diff("src/updater.py", ["eval(requests.get(url).text)"])
        assert check_supply_chain(diff)

    def test_safe_correct_package_name_not_flagged(self) -> None:
        diff = _diff("requirements.txt", ["requests==2.31.0"])
        assert not check_supply_chain(diff)

    def test_typosquat_only_checked_in_dep_files(self) -> None:
        # Same typo in a Python file should not flag
        diff = _diff("src/app.py", ["import requets"])
        hits = check_supply_chain(diff)
        typo_hits = [h for h in hits if "typosquat" in h.message]
        assert not typo_hits

    def test_all_hits_are_paid(self) -> None:
        diff = _diff("src/updater.py", ["exec(requests.get(url).text)"])
        hits = check_supply_chain(diff)
        assert hits
        assert all(not h.is_free for h in hits)


# ── Deep Scanner integration ──────────────────────────────────────────────────


class TestRunDeepScan:
    def test_empty_diffs_returns_empty_report(self) -> None:
        report = run_deep_scan([])
        assert not report.has_issues
        assert report.files_scanned == 0

    def test_detects_weak_hash_in_py_file(self) -> None:
        diff = _diff("src/utils.py", ["h = hashlib.md5(data)"])
        report = run_deep_scan([diff])
        assert report.has_issues

    def test_skips_removed_files(self) -> None:
        diff = _diff("src/utils.py", ["h = hashlib.md5(data)"], status="removed")
        report = run_deep_scan([diff])
        assert not report.has_issues

    def test_skips_lock_files(self) -> None:
        diff = _diff("package-lock.json", ["eval(fetch(url).text)"])
        report = run_deep_scan([diff])
        assert not report.has_issues

    def test_counts_files_scanned(self) -> None:
        diffs = [
            _diff("src/a.py", ["x = 1"]),
            _diff("src/b.py", ["y = 2"]),
        ]
        report = run_deep_scan(diffs)
        assert report.files_scanned == 2

    def test_deduplicates_hits(self) -> None:
        diff = _diff("src/utils.py", ["h = hashlib.md5(data)"])
        report = run_deep_scan([diff, diff])
        keys = [(h.file, h.line, h.check) for h in report.hits]
        assert len(keys) == len(set(keys))

    def test_all_hits_are_paid_tier(self) -> None:
        diff = _diff("src/auth.py", ['jwt.decode(t, algorithms=["none"])'])
        report = run_deep_scan([diff])
        assert report.has_issues
        assert all(not h.is_free for h in report.hits)
