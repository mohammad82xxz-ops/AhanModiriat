#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only profiler for an isolated legacy SQLite inventory backup.

The source is opened with mode=ro and query_only. No migration, repair,
normalization, or write to the source database is performed.
"""
from __future__ import annotations
import argparse, csv, datetime as dt, hashlib, json, math, sqlite3, sys
from collections import Counter
from pathlib import Path

PROFILE = {
    "purchases": "qty", "sales": "qty", "purchase_returns": "qty",
    "sales_returns": "qty", "inventory_adjustments": "delta_qty",
}
MOVEMENTS = tuple(PROFILE)
UNIT_FIELDS = ("unit", "purchase_unit", "sale_unit")

def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def finite(value):
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False

def csv_write(path, rows, fields):
    with Path(path).open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                        for k, v in row.items()})

def exists(c, table):
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                     (table,)).fetchone() is not None

def cols(c, table):
    return [r[1] for r in c.execute('PRAGMA table_info("' + table + '")')]

def add_exc(out, severity, code, table, rid, pid, raw, reason, action):
    out.append(dict(severity=severity, code=code, table=table, record_id=rid,
                    product_id=pid, raw_value=raw, reason=reason, next_action=action))

def audit(db, out, source_label="isolated-backup-copy"):
    db = Path(db).expanduser().resolve(strict=True)
    out = Path(out).expanduser().resolve()
    if not db.is_file():
        raise ValueError("ورودی باید فایل SQLite موجود باشد.")
    if out == db or out in db.parents:
        raise ValueError("پوشه خروجی نباید فایل دیتابیس یا والد آن باشد.")
    out.mkdir(parents=True, exist_ok=True)
    before = sha256(db)
    c = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=5)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA query_only=ON")
    if c.execute("PRAGMA query_only").fetchone()[0] != 1:
        c.close()
        raise RuntimeError("فعال‌سازی query_only ناموفق بود.")
    exc, limitations = [], []
    manifest = {
        "source_label": source_label, "source_sha256_before": before,
        "mode": "READ_ONLY", "database_path_disclosed": False,
        "started_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "result": "complete", "limitations": limitations,
    }
    try:
        integrity = [r[0] for r in c.execute("PRAGMA integrity_check")]
        fk = [dict(r) for r in c.execute("PRAGMA foreign_key_check")]
        manifest["integrity_check"] = integrity
        manifest["foreign_key_violation_count"] = len(fk)
        if integrity != ["ok"]:
            manifest["result"] = "blocked"
            limitations.append("integrity_check did not return only ok.")
        for row in fk:
            add_exc(exc, "blocker", "REL-001", row.get("table"), row.get("rowid"),
                    None, row, "Foreign-key violation.",
                    "مرجع سند را بررسی کنید؛ اتصال خودکار ممنوع است.")
        if fk and manifest["result"] != "blocked":
            manifest["result"] = "partial"

        tables = [r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        schema = {t: cols(c, t) for t in tables}
        manifest["tables"] = tables
        manifest["schema_fingerprint"] = hashlib.sha256(
            json.dumps(schema, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        manifest["table_row_counts"] = {
            t: c.execute('SELECT COUNT(*) FROM "' + t + '"').fetchone()[0] for t in tables
        }

        required = ("id", "name", "unit", "stock", "min_stock")
        missing = [x for x in required if x not in schema.get("products", [])]
        products = []
        if missing:
            manifest["result"] = "blocked"
            limitations.append("products schema missing: " + ", ".join(missing))
        else:
            products = c.execute('SELECT * FROM products ORDER BY id').fetchall()
        pmap = {p["id"]: p for p in products}
        product_rows, unit_counter = [], Counter()
        for p in products:
            pid = p["id"]
            for field in UNIT_FIELDS:
                if field in p.keys():
                    unit_counter[(field, "<NULL>" if p[field] is None else str(p[field]))] += 1
            row = {k: p[k] if k in p.keys() else None for k in (
                "id", "name", "code", "category", "unit", "stock", "min_stock",
                "purchase_unit", "purchase_factor", "sale_unit", "sale_factor",
                "roll_weight", "sheet_area")}
            product_rows.append(row)
            for field in ("unit", "purchase_unit", "sale_unit"):
                if field in p.keys() and (p[field] is None or not str(p[field]).strip()):
                    add_exc(exc, "blocker" if field == "unit" else "high",
                            "UNIT-001" if field == "unit" else "UNIT-002",
                            "products", pid, pid, p[field], field + " is empty/NULL.",
                            "واحد را از سند معتبر تعیین کنید؛ حدس یا normalize نکنید.")
            for field in ("purchase_factor", "sale_factor"):
                if field in p.keys() and (not finite(p[field]) or float(p[field]) <= 0):
                    add_exc(exc, "blocker", "FACTOR-001" if finite(p[field]) else "FACTOR-002",
                            "products", pid, pid, p[field], field + " is invalid.",
                            "تبدیل محصول تا تعیین ضریب معتبر متوقف بماند.")
            for field in ("stock", "min_stock"):
                if field in p.keys() and finite(p[field]) and float(p[field]) < 0:
                    add_exc(exc, "high", "QTY-001", "products", pid, pid, p[field],
                            "Negative " + field + ".", "مقدار خام حفظ و با گردش تطبیق داده شود.")
            for field in ("roll_weight", "sheet_area"):
                if field in p.keys() and p[field] is not None:
                    if not finite(p[field]) or float(p[field]) < 0:
                        add_exc(exc, "high", "PHYS-001", "products", pid, pid, p[field],
                                "Invalid " + field + ".", "واحد و معنای فیزیکی بررسی شود.")
                    elif float(p[field]) == 0:
                        add_exc(exc, "medium", "PHYS-001", "products", pid, pid, p[field],
                                "Zero may mean zero or not recorded.",
                                "بدون مدرک، صفر را مقدار فیزیکی واقعی تلقی نکنید.")

        unit_rows = [dict(field=k[0], raw_value=k[1], product_count=v)
                     for k, v in sorted(unit_counter.items())]
        profiles = []
        for table, qfield in PROFILE.items():
            if not exists(c, table):
                limitations.append("Optional table missing: " + table)
                continue
            if qfield not in schema[table]:
                add_exc(exc, "high", "SCHEMA-001", table, None, None, qfield,
                        "Expected quantity column missing.", "schema را دستی بررسی کنید.")
                if manifest["result"] == "complete":
                    manifest["result"] = "partial"
                continue
            values = [r[0] for r in c.execute('SELECT "' + qfield + '" FROM "' + table + '"')]
            nums = [float(v) for v in values if finite(v)]
            profiles.append(dict(
                table=table, quantity_field=qfield, row_count=len(values),
                null_count=sum(v is None for v in values),
                non_numeric_count=sum(v is not None and not finite(v) for v in values),
                negative_count=sum(v < 0 for v in nums), zero_count=sum(v == 0 for v in nums),
                min_raw_numeric=min(nums) if nums else None,
                max_raw_numeric=max(nums) if nums else None,
                sum_raw_numeric=sum(nums) if nums else None,
                unit_semantics="table-specific; do not aggregate across tables"))
            for r in c.execute('SELECT * FROM "' + table + '"'):
                v = r[qfield]
                rid = r["id"] if "id" in r.keys() else None
                pid = r["product_id"] if "product_id" in r.keys() else None
                if v is None or not finite(v):
                    add_exc(exc, "blocker", "QTY-002", table, rid, pid, v,
                            "Quantity is NULL/non-finite.", "رکورد برای تبدیل متوقف و خام حفظ شود.")
                elif float(v) < 0:
                    add_exc(exc, "high", "QTY-001", table, rid, pid, v,
                            "Negative quantity needs path-specific interpretation.",
                            "معنای مسیر سند و اصلاحیه احتمالی بررسی شود.")
                if "date" in r.keys():
                    try:
                        dt.date.fromisoformat(str(r["date"])[:10])
                    except (TypeError, ValueError):
                        add_exc(exc, "high", "DATE-001", table, rid, pid, r["date"],
                                "Date is not a valid Gregorian ISO date.",
                                "تاریخ سند اصلی بررسی شود؛ تبدیل حدسی ممنوع.")

        recon = {pid: dict(purchase_base_assumed=0.0, sales_base=0.0,
                           purchase_returns_base=0.0, sales_returns_base=0.0,
                           inventory_adjustment_base=0.0) for pid in pmap}
        for table in MOVEMENTS:
            if not exists(c, table):
                continue
            qfield = PROFILE[table]
            if not {"product_id", qfield}.issubset(schema[table]):
                limitations.append("Reconciliation skipped for schema mismatch: " + table)
                if manifest["result"] == "complete":
                    manifest["result"] = "partial"
                continue
            for r in c.execute('SELECT * FROM "' + table + '"'):
                pid = r["product_id"]
                if pid not in recon or not finite(r[qfield]):
                    continue
                qty = float(r[qfield])
                if table == "purchases":
                    factor = pmap[pid]["purchase_factor"] if "purchase_factor" in pmap[pid].keys() else None
                    if finite(factor) and float(factor) > 0:
                        recon[pid]["purchase_base_assumed"] += qty * float(factor)
                    else:
                        add_exc(exc, "blocker", "FACTOR-003", table, r["id"], pid, factor,
                                "Cannot reconstruct purchase using current factor.",
                                "factor تاریخی یا سند معتبر لازم است.")
                elif table == "sales":
                    recon[pid]["sales_base"] += qty
                elif table == "purchase_returns":
                    recon[pid]["purchase_returns_base"] += qty
                elif table == "sales_returns":
                    recon[pid]["sales_returns_base"] += qty
                else:
                    recon[pid]["inventory_adjustment_base"] += qty

        reconciliations = []
        for pid, p in pmap.items():
            parts = recon[pid]
            delta = (parts["purchase_base_assumed"] - parts["sales_base"]
                     - parts["purchase_returns_base"] + parts["sales_returns_base"]
                     + parts["inventory_adjustment_base"])
            stock = float(p["stock"]) if finite(p["stock"]) else None
            baseline = stock - delta if stock is not None else None
            reconciliations.append(dict(
                product_id=pid, product_name=p["name"], current_stock_raw=p["stock"],
                **parts, total_delta_assumed=delta,
                arithmetic_baseline_not_opening_document=baseline,
                purchase_factor_assumption="CURRENT_PRODUCT_FACTOR_ASSUMED",
                status="RECONSTRUCTED_WITH_ASSUMPTIONS" if baseline is not None else "UNRECONCILED"))
            if baseline is not None:
                add_exc(exc, "high", "LEDGER-002", "products", pid, pid, baseline,
                        "Arithmetic baseline is not evidence of a dated opening document.",
                        "افتتاحیه فقط با سند تاریخ‌دار و تأیید مالک پذیرفته شود.")
        if not any(exists(c, t) for t in MOVEMENTS):
            limitations.append("No recognized movement tables found.")
            if manifest["result"] == "complete":
                manifest["result"] = "partial"

        manifest["product_count"] = len(products)
        manifest["exception_count"] = len(exc)
        manifest["exception_counts_by_code"] = dict(Counter(x["code"] for x in exc))
        manifest["exception_counts_by_severity"] = dict(Counter(x["severity"] for x in exc))
        manifest["finished_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        csv_write(out / "product_unit_inventory.csv", product_rows, list(product_rows[0]) if product_rows else list(required))
        csv_write(out / "unit_value_counts.csv", unit_rows, ["field", "raw_value", "product_count"])
        csv_write(out / "document_quantity_profile.csv", profiles, [
            "table", "quantity_field", "row_count", "null_count", "non_numeric_count",
            "negative_count", "zero_count", "min_raw_numeric", "max_raw_numeric",
            "sum_raw_numeric", "unit_semantics"])
        csv_write(out / "product_reconciliation.csv", reconciliations, [
            "product_id", "product_name", "current_stock_raw", "purchase_base_assumed",
            "sales_base", "purchase_returns_base", "sales_returns_base",
            "inventory_adjustment_base", "total_delta_assumed",
            "arithmetic_baseline_not_opening_document", "purchase_factor_assumption", "status"])
        csv_write(out / "exceptions.csv", exc, [
            "severity", "code", "table", "record_id", "product_id", "raw_value",
            "reason", "next_action"])
        summary = [
            "# خلاصه ممیزی فقط‌خواندنی", "",
            "- وضعیت: " + manifest["result"],
            "- حالت: READ_ONLY",
            "- تعداد محصولات: " + str(manifest["product_count"]),
            "- تعداد exceptionها: " + str(manifest["exception_count"]),
            "- SHA-256 منبع پیش از ممیزی: " + before,
            "- هیچ داده‌ای تغییر یا normalize نشده است.",
            "- baseline محاسباتی سند افتتاحیه تاریخ‌دار نیست.",
            "- مقدار پایه خرید با factor فعلی صرفاً فرض بازسازی است.",
            "", "## محدودیت‌ها",
            *(["- " + x for x in limitations] or ["- محدودیت schema اضافی ثبت نشد."])]
        (out / "audit_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    finally:
        c.close()

    after = sha256(db)
    manifest["source_sha256_after"] = after
    manifest["source_unchanged"] = before == after
    if before != after:
        manifest["result"] = "blocked"
        manifest["limitations"].append("Source checksum changed during audit.")
    (out / "audit_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    lines = []
    for path in sorted(out.iterdir()):
        if path.is_file() and path.name != "checksums.txt":
            lines.append(sha256(path) + "  " + path.name)
    (out / "checksums.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if before != after:
        raise RuntimeError("Source changed during audit; result is blocked.")
    return manifest

def main(argv=None):
    p = argparse.ArgumentParser(description="Read-only legacy SQLite quantity profiler")
    p.add_argument("--db", required=True, help="مسیر کپی ایزوله SQLite؛ فایل فعال ممنوع است")
    p.add_argument("--out", required=True, help="پوشه مستقل خروجی")
    p.add_argument("--source-label", default="isolated-backup-copy")
    a = p.parse_args(argv)
    try:
        result = audit(a.db, a.out, a.source_label)
    except Exception as e:
        print("AUDIT BLOCKED: " + str(e), file=sys.stderr)
        return 2
    print(json.dumps({k: result.get(k) for k in (
        "result", "product_count", "exception_count", "source_unchanged")}, ensure_ascii=False))
    return 0 if result["result"] == "complete" else 1

if __name__ == "__main__":
    raise SystemExit(main())
