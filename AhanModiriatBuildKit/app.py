# -*- coding: utf-8 -*-
"""AhanModiriat - local-first Persian steel inventory and cash/profit tracker.
Python standard library only. Data stays in ./data/business.db.
"""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from pathlib import Path
import sqlite3, json, datetime, html, os, threading, webbrowser, sys, mimetypes, tempfile, calendar, io, zipfile, re, secrets, xml.etree.ElementTree as ET
from email.parser import BytesParser
from email.policy import default as email_policy

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
STATIC_DIR = Path(getattr(sys, '_MEIPASS', ROOT)) / 'static'
# Optional override supports isolated tests and custom persistent data locations.
DATA = Path(os.environ.get('AHAN_DATA_DIR', str(ROOT / 'data'))).expanduser().resolve()
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / 'business.db'
TODAY = datetime.date.today().isoformat()
LOCK = threading.Lock()

# Jalali calendar conversion; database continues to store Gregorian ISO dates.
def gregorian_to_jalali(gy, gm, gd):
    g_days = [0,31,59,90,120,151,181,212,243,273,304,334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + 365*gy + (gy2+3)//4 - (gy2+99)//100 + (gy2+399)//400 + gd + g_days[gm-1]
    jy = -1595 + 33*(days//12053)
    days %= 12053
    jy += 4*(days//1461)
    days %= 1461
    if days > 365:
        jy += (days-1)//365
        days = (days-1)%365
    if days < 186:
        jm = 1 + days//31
        jd = 1 + days%31
    else:
        jm = 7 + (days-186)//30
        jd = 1 + (days-186)%30
    return jy, jm, jd

def jalali_to_gregorian(jy, jm, jd):
    jy += 1595
    days = -355668 + 365*jy + (jy//33)*8 + ((jy%33)+3)//4 + jd
    if jm < 7:
        days += (jm-1)*31
    else:
        days += 186 + (jm-7)*30
    gy = 400*(days//146097)
    days %= 146097
    if days > 36524:
        gy += 100*((days-1)//36524)
        days = (days-1)%36524
        if days >= 365:
            days += 1
    gy += 4*(days//1461)
    days %= 1461
    if days > 365:
        gy += (days-1)//365
        days = (days-1)%365
    gd = days+1
    leap = (gy%4==0 and gy%100!=0) or gy%400==0
    month_days = [0,31,29 if leap else 28,31,30,31,30,31,31,30,31,30,31]
    gm = 1
    while gm <= 12 and gd > month_days[gm]:
        gd -= month_days[gm]
        gm += 1
    return gy, gm, gd

def jalali_month_start_iso():
    jy,jm,jd = gregorian_to_jalali(*map(int, datetime.date.today().strftime("%Y-%m-%d").split("-")))
    gy,gm,gd = jalali_to_gregorian(jy,jm,1)
    return datetime.date(gy,gm,gd).isoformat()

def jalali_year_start_iso():
    jy,jm,jd = gregorian_to_jalali(*map(int, datetime.date.today().strftime("%Y-%m-%d").split("-")))
    gy,gm,gd = jalali_to_gregorian(jy,1,1)
    return datetime.date(gy,gm,gd).isoformat()

def jalali_today():
    y,m,d = gregorian_to_jalali(*map(int, datetime.date.today().strftime("%Y-%m-%d").split("-")))
    return f"{y:04d}-{m:02d}-{d:02d}"

def to_iso_date(value):
    value = (value or "").strip()
    if not value:
        return TODAY
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    value = value.translate(trans).replace("-", "/")
    parts = value.split("/")
    if len(parts) != 3:
        raise ValueError("تاریخ را به شکل ۱۴۰۵/۰۷/۰۱ وارد کنید.")
    y, m, d = map(int, parts)
    if y < 1700:
        # Validate the Jalali date before conversion; the arithmetic converter
        # can otherwise normalize out-of-range month/day values silently.
        if not 1 <= m <= 12 or d < 1 or d > (31 if m <= 6 else 30):
            raise ValueError("تاریخ شمسی نامعتبر است.")
        gy, gm, gd = jalali_to_gregorian(y, m, d)
        result = datetime.date(gy, gm, gd)
        if gregorian_to_jalali(gy, gm, gd) != (y, m, d):
            raise ValueError("تاریخ شمسی نامعتبر است.")
    else:
        result = datetime.date(y, m, d)
    return result.isoformat()

def show_date(value):
    try:
        gy,gm,gd = map(int, str(value).split("-")[:3])
        jy,jm,jd = gregorian_to_jalali(gy,gm,gd)
        return f"{jy:04d}/{jm:02d}/{jd:02d}"
    except Exception:
        return str(value or "")


def create_startup_backup():
    """Create a consistent pre-startup backup and keep only the newest seven."""
    if not DB.exists() or DB.stat().st_size == 0:
        return None
    backup_dir = DATA / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    target = backup_dir / f"business_{stamp}.db"
    try:
        with sqlite3.connect(DB, timeout=20) as source, sqlite3.connect(target) as dest:
            source.backup(dest)
        backups = sorted(backup_dir.glob("business_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in backups[7:]:
            try: old.unlink()
            except OSError: pass
        return target
    except Exception:
        try: target.unlink(missing_ok=True)
        except OSError: pass
        raise

def conn():
    c=sqlite3.connect(DB, timeout=20)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA synchronous=NORMAL')
    return c

def add_interval_date(date_value, interval_value=1, interval_unit="month"):
    """Advance a due date by a configurable interval; clamp month/year dates safely."""
    if not date_value:
        return ""
    try:
        day = datetime.date.fromisoformat(str(date_value)[:10])
    except (TypeError, ValueError):
        return ""
    value = int(interval_value or 1)
    if value < 1 or value > 365:
        raise ValueError("فاصلهٔ سررسید باید بین ۱ تا ۳۶۵ باشد.")
    unit = str(interval_unit or "month").lower()
    if unit == "day":
        return (day + datetime.timedelta(days=value)).isoformat()
    if unit == "week":
        return (day + datetime.timedelta(days=value*7)).isoformat()
    if unit == "month":
        month_index = day.year*12 + (day.month-1) + value
        year, month0 = divmod(month_index, 12)
        month = month0 + 1
        return datetime.date(year, month, min(day.day, calendar.monthrange(year, month)[1])).isoformat()
    if unit == "year":
        year = day.year + value
        return datetime.date(year, day.month, min(day.day, calendar.monthrange(year, day.month)[1])).isoformat()
    raise ValueError("واحد فاصلهٔ سررسید معتبر نیست.")

def compute_purchase_advice(c, window_days=30):
    """Heuristic: stock target = min-stock reserve + recent daily sales × coverage window."""
    window_days = max(1, min(int(window_days), 365))
    today = datetime.date.today()
    start = (today - datetime.timedelta(days=window_days-1)).isoformat()
    rows = []
    for p in c.execute("""SELECT p.*,COALESCE(SUM(s.qty),0) AS sold_window
                          FROM products p LEFT JOIN sales s
                            ON s.product_id=p.id AND s.date>=? AND s.date<=?
                          GROUP BY p.id ORDER BY p.name""",(start,today.isoformat())):
        sold = float(p["sold_window"] or 0)
        daily = sold/window_days
        target = float(p["min_stock"] or 0) + daily*window_days
        recommend = max(0.0, target-float(p["stock"] or 0))
        coverage = (float(p["stock"] or 0)/daily) if daily>0 else None
        rows.append({
            "id":p["id"],"name":p["name"],"unit":p["unit"],"stock":float(p["stock"] or 0),
            "min_stock":float(p["min_stock"] or 0),"sold":sold,"daily":daily,
            "target":target,"recommend":recommend,"coverage":coverage,
            "priority":0 if float(p["stock"] or 0)<=float(p["min_stock"] or 0) else 1,
        })
    rows.sort(key=lambda r:(r["priority"],-r["recommend"],r["name"].casefold()))
    return rows

def returns_page(c, search='', page_num=1):
    sales_opts=[]
    for r in c.execute("""SELECT s.id,s.date,s.qty,s.unit_price,s.customer,p.name,p.unit,
                               COALESCE((SELECT SUM(sr.qty) FROM sales_returns sr WHERE sr.sale_id=s.id),0) AS returned
                          FROM sales s JOIN products p ON p.id=s.product_id ORDER BY s.date DESC,s.id DESC LIMIT 500"""):
        remaining=float(r["qty"])-float(r["returned"])
        if remaining>0.000001:
            sales_opts.append((r["id"],f'#{r["id"]} · {r["name"]} · {show_date(r["date"])} · {r["customer"] or "بدون مشتری"} · مانده مرجوعی {remaining:g} {r["unit"]}'))
    purchase_opts=[]
    for r in c.execute("""SELECT p.id,p.date,p.qty,p.supplier,p.product_id,pr.name,pr.unit,
                                 pr.purchase_factor,
                                 COALESCE((SELECT SUM(prr.qty) FROM purchase_returns prr WHERE prr.purchase_id=p.id),0) AS returned
                          FROM purchases p JOIN products pr ON pr.id=p.product_id ORDER BY p.date DESC,p.id DESC LIMIT 500"""):
        remaining=float(r["qty"])*float(r["purchase_factor"] or 1)-float(r["returned"])
        if remaining>0.000001:
            purchase_opts.append((r["id"],f'#{r["id"]} · {r["name"]} · {show_date(r["date"])} · {r["supplier"] or "بدون فروشنده"} · مانده مرجوعی {remaining:g} {r["unit"]}'))
    limit,offset,page_num=page_window(page_num,50)
    query=str(search or '').strip(); pattern='%'+query+'%'
    total=int(scalar(c,"SELECT COUNT(*) FROM sales_returns")+scalar(c,"SELECT COUNT(*) FROM purchase_returns"))
    union_sql="""SELECT sr.id AS id,sr.date AS date,'مرجوعی فروش' AS kind,p.name AS name,p.unit AS unit,
                        sr.qty AS qty,sr.return_value AS return_value,sr.refund_amount AS cash_amount,
                        sr.customer AS party,sr.reason AS reason
                 FROM sales_returns sr JOIN products p ON p.id=sr.product_id
                 UNION ALL
                 SELECT pr.id AS id,pr.date AS date,'مرجوعی خرید' AS kind,p.name AS name,p.unit AS unit,
                        pr.qty AS qty,pr.return_value AS return_value,pr.cash_refund AS cash_amount,
                        pr.supplier AS party,pr.reason AS reason
                 FROM purchase_returns pr JOIN products p ON p.id=pr.product_id"""
    total=scalar(c,"SELECT COUNT(*) FROM ("+union_sql+") ret WHERE name LIKE ? OR party LIKE ? OR reason LIKE ?",(pattern,pattern,pattern))
    rows=[]
    for r in c.execute("SELECT * FROM ("+union_sql+") ret WHERE name LIKE ? OR party LIKE ? OR reason LIKE ? ORDER BY date DESC,id DESC LIMIT ? OFFSET ?",
                        (pattern,pattern,pattern,limit,offset)):
        rows.append([show_date(r["date"]),esc(r["kind"]),esc(r["name"]),f'{r["qty"]:g} {esc(r["unit"])}',
                     money(r["return_value"]),money(r["cash_amount"]),esc(r["party"]),esc(r["reason"])])
    body=f'''<h1>مرجوعی خرید و فروش</h1>
    <div class="twocol section">
      <div class="card"><h2>ثبت مرجوعی فروش از مشتری</h2>
        <form method="post" action="/add_sales_return"><div class="formgrid">
          {selectfield("سند فروش اصلی","sale_id",sales_opts)}
          {field("تاریخ مرجوعی","date","date",TODAY,True)}
          {field("مقدار برگشتی (واحد پایه کالا)","qty","number","1",True,"0.001")}
          {field("وجهی که واقعاً به مشتری برمی‌گردد (تومان)","refund_amount","number","0",True,"1")}
          {field("علت مرجوعی","reason","text","",True)}
          {field("یادداشت","notes")}
        </div><div class="actions"><button>ثبت مرجوعی فروش</button></div></form>
        <p class="small">کالا با بهای تمام‌شده ذخیره‌شده در فروش اصلی به موجودی برمی‌گردد؛ مبلغ برگشتی از فروش و سود همان تاریخ مرجوعی کم می‌شود.</p>
      </div>
      <div class="card"><h2>ثبت مرجوعی خرید به فروشنده</h2>
        <form method="post" action="/add_purchase_return"><div class="formgrid">
          {selectfield("سند خرید اصلی","purchase_id",purchase_opts)}
          {field("تاریخ مرجوعی","date","date",TODAY,True)}
          {field("مقدار برگشتی (واحد پایه کالا)","qty","number","1",True,"0.001")}
          {field("وجهی که واقعاً از فروشنده دریافت می‌شود (تومان)","cash_refund","number","0",True,"1")}
          {field("علت مرجوعی","reason","text","",True)}
          {field("یادداشت","notes")}
        </div><div class="actions"><button>ثبت مرجوعی خرید</button></div></form>
        <p class="small">مقدار مرجوعی به واحد پایه وارد می‌شود. مانده حساب فروشنده بر اساس ارزش برگشتی کاهش می‌یابد؛ فقط مبلغی که واقعاً دریافت شده در صندوق ثبت می‌شود.</p>
      </div>
    </div>
    <div class="card section"><h2>مرجوعی‌های ثبت‌شده</h2>
    <form method="get" action="/returns" class="search-form"><label>جستجوی مرجوعی</label><div class="formgrid"><input type="search" name="q" value="{esc(query)}" placeholder="کالا، طرف حساب یا علت"><input type="hidden" name="page" value="1"><button>جستجو</button></div></form>
    {table(["تاریخ","نوع","کالا","مقدار","ارزش سند","وجه واقعی","طرف حساب","علت"],rows,total)}
    {page_nav("returns",query,page_num,total,limit)}</div>'''
    return page("مرجوعی‌ها",body,"returns")

def purchase_advice(c):
    data = compute_purchase_advice(c,30)
    rows = []
    for r in data:
        cover = f'{r["coverage"]:.1f} روز' if r["coverage"] is not None else "بدون فروش ثبت‌شده"
        urgency = "کمتر از حداقل" if r["stock"]<=r["min_stock"] else ("نیاز به سفارش" if r["recommend"]>0 else "کافی")
        rows.append([esc(r["name"]),f'{r["stock"]:g} {esc(r["unit"])}',f'{r["min_stock"]:g}',
                     f'{r["sold"]:g} {esc(r["unit"])}',f'{r["daily"]:.3f}',cover,
                     f'{r["target"]:.3f}',f'{r["recommend"]:.3f} {esc(r["unit"])}',urgency])
    body=f'''<h1>پیشنهاد خرید کالا</h1>
    <div class="notice">برآورد ساده بر پایهٔ فروش ثبت‌شدهٔ ۳۰ روز اخیر است: هدف موجودی = حداقل موجودی ایمن + فروش ۳۰ روز اخیر. این محاسبه جایگزین بررسی موجودی فیزیکی، سفارش‌های در راه و زمان واقعی تأمین نیست.</div>
    <div class="card section"><h2>پیشنهاد سفارش</h2>
    {table(["کالا","موجودی فعلی","حداقل ایمن","فروش ۳۰ روز","میانگین روزانه","پوشش موجودی","هدف موجودی","مقدار پیشنهادی سفارش","وضعیت"],rows)}
    </div>'''
    return page("پیشنهاد خرید",body,"buy-advice")

def restore_database_from_file(source_path):
    """Validate an uploaded database, snapshot current data, then restore through SQLite backup API."""
    source_path = Path(source_path)
    if not source_path.is_file() or source_path.stat().st_size <= 0:
        raise ValueError("فایل پشتیبان خالی یا نامعتبر است.")
    if source_path.stat().st_size > 100 * 1024 * 1024:
        raise ValueError("حجم فایل پشتیبان از سقف ۱۰۰ مگابایت بیشتر است.")
    uri = "file:" + source_path.resolve().as_posix() + "?mode=ro"
    check = sqlite3.connect(uri, uri=True, timeout=20)
    try:
        if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("ساختار پایگاه دادهٔ پشتیبان سالم نیست.")
        tables = {r[0] for r in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {
            "products": {"id","name","stock","avg_cost"},
            "purchases": {"id","date","product_id","qty","unit_cost"},
            "sales": {"id","date","product_id","qty","unit_price"},
        }
        for table, columns in required.items():
            if table not in tables:
                raise ValueError("این فایل، پشتیبان معتبر آهن‌مدیریت نیست.")
            actual = {r[1] for r in check.execute(f"PRAGMA table_info({table})")}
            if not columns.issubset(actual):
                raise ValueError("ساختار جدول‌های اصلی پشتیبان با آهن‌مدیریت سازگار نیست.")
    except sqlite3.DatabaseError as exc:
        raise ValueError("فایل پشتیبان قابل خواندن نیست یا پایگاه دادهٔ SQLite معتبری نیست.") from exc
    finally:
        check.close()
    # Retain a separate snapshot of the current database before replacing anything.
    create_startup_backup()
    source = sqlite3.connect(uri, uri=True, timeout=20)
    target = sqlite3.connect(DB, timeout=20)
    try:
        source.backup(target)
        target.commit()
    finally:
        source.close()
        target.close()
    # Apply additive migrations and rebuild only missing cash-ledger links after restore.
    init()

MONEY_INTEGER_COLUMNS = {
    "products": ("avg_cost","market_price"),
    "purchases": ("unit_cost","extra_cost","paid"),
    "sales": ("unit_price","extra_cost","received","cost_basis"),
    "services": ("revenue","cost","received"),
    "expenses": ("amount",),
    "loans": ("principal","remaining","installment"),
    "loan_payments": ("amount","principal_part","interest_part"),
    "cash_events": ("amount",),
    "price_history": ("market_price",),
    "opening_capital": ("amount",),
    "settlements": ("amount",),
    "purchase_returns": ("return_value",),
    "sales_returns": ("return_value","cost_basis","extra_reversed"),
}

def migrate_money_columns_to_integer(c):
    """Safely rebuild tables where legacy monetary columns use REAL; preserve all schema objects."""
    migrated=0
    for table, candidates in MONEY_INTEGER_COLUMNS.items():
        table_row=c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()
        if not table_row or not table_row["sql"]:
            continue
        create_sql=table_row["sql"]
        info=c.execute(f'PRAGMA table_info("{table}")').fetchall()
        money_types={row["name"]:str(row["type"] or "").strip().upper() for row in info}
        to_convert=[name for name in candidates if money_types.get(name) in ("REAL","FLOAT","DOUBLE","NUMERIC","DECIMAL")]
        if not to_convert:
            continue
        match=re.match(r'(?is)^(CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?)([A-Za-z_][A-Za-z_0-9]*)',create_sql)
        if not match:
            raise RuntimeError(f"ساختار جدول {table} برای مهاجرت مبلغ قابل بازسازی نیست.")
        original_name=match.group(2)
        if original_name.lower()!=table.lower():
            raise RuntimeError(f"نام جدول {table} با طرح ذخیره‌شده همخوان نیست.")
        temporary=f"__money_integer_{table}"
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(temporary,)).fetchone():
            raise RuntimeError(f"جدول موقت مهاجرت {temporary} از قبل وجود دارد.")
        objects=c.execute("""SELECT type,name,sql FROM sqlite_master
                             WHERE tbl_name=? AND type IN ('index','trigger') AND sql IS NOT NULL
                             ORDER BY CASE type WHEN 'index' THEN 0 ELSE 1 END,name""",(table,)).fetchall()
        rebuilt_sql=match.group(1)+f'"{temporary}"'+create_sql[match.end():]
        for column in to_convert:
            pattern=re.compile(r'(?i)(\b'+re.escape(column)+r'\s+)(?:REAL|FLOAT|DOUBLE|NUMERIC|DECIMAL)\b')
            rebuilt_sql,count=pattern.subn(r'\1INTEGER',rebuilt_sql,count=1)
            if count!=1:
                raise RuntimeError(f"تعریف نوع ستون {table}.{column} قابل تبدیل نیست.")
        columns=[row["name"] for row in info]
        quoted_columns=",".join('"'+name.replace('"','""')+'"' for name in columns)
        expressions=[]
        for name in columns:
            quoted='"'+name.replace('"','""')+'"'
            if name in to_convert:
                expressions.append(f"CASE WHEN {quoted} IS NULL THEN NULL ELSE CAST(ROUND({quoted}) AS INTEGER) END")
            else:
                expressions.append(quoted)
        c.execute(rebuilt_sql)
        c.execute(f'INSERT INTO "{temporary}" ({quoted_columns}) SELECT {",".join(expressions)} FROM "{table}"')
        c.execute(f'DROP TABLE "{table}"')
        c.execute(f'ALTER TABLE "{temporary}" RENAME TO "{table}"')
        for obj in objects:
            c.execute(obj["sql"])
        migrated+=len(to_convert)
    return migrated

def init():
    create_startup_backup()
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, name TEXT NOT NULL, code TEXT DEFAULT '', unit TEXT NOT NULL DEFAULT 'کیلوگرم', stock REAL NOT NULL DEFAULT 0, avg_cost REAL NOT NULL DEFAULT 0, market_price REAL NOT NULL DEFAULT 0, min_stock REAL NOT NULL DEFAULT 0, notes TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS purchases(id INTEGER PRIMARY KEY, date TEXT NOT NULL, product_id INTEGER NOT NULL REFERENCES products(id), qty REAL NOT NULL, unit_cost REAL NOT NULL, extra_cost REAL NOT NULL DEFAULT 0, supplier TEXT DEFAULT '', paid REAL NOT NULL DEFAULT 0, notes TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS sales(id INTEGER PRIMARY KEY, date TEXT NOT NULL, product_id INTEGER NOT NULL REFERENCES products(id), qty REAL NOT NULL, unit_price REAL NOT NULL, extra_cost REAL NOT NULL DEFAULT 0, customer TEXT DEFAULT '', received REAL NOT NULL DEFAULT 0, notes TEXT DEFAULT '', cost_basis REAL NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS services(id INTEGER PRIMARY KEY, date TEXT NOT NULL, title TEXT NOT NULL, revenue REAL NOT NULL, cost REAL NOT NULL DEFAULT 0, received REAL NOT NULL DEFAULT 0, customer TEXT DEFAULT '', notes TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS expenses(id INTEGER PRIMARY KEY, date TEXT NOT NULL, category TEXT NOT NULL, amount REAL NOT NULL, source TEXT NOT NULL DEFAULT 'نامشخص', business INTEGER NOT NULL DEFAULT 1, notes TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS loans(id INTEGER PRIMARY KEY, title TEXT NOT NULL, principal REAL NOT NULL, remaining REAL NOT NULL, installment REAL NOT NULL, next_date TEXT DEFAULT '', rate_note TEXT DEFAULT '', notes TEXT DEFAULT '', interval_value INTEGER NOT NULL DEFAULT 1, interval_unit TEXT NOT NULL DEFAULT 'month');
        CREATE TABLE IF NOT EXISTS loan_payments(id INTEGER PRIMARY KEY, loan_id INTEGER NOT NULL REFERENCES loans(id), date TEXT NOT NULL, amount REAL NOT NULL, principal_part REAL NOT NULL, interest_part REAL NOT NULL, source TEXT NOT NULL DEFAULT 'نامشخص', notes TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS cash_events(id INTEGER PRIMARY KEY, date TEXT NOT NULL, kind TEXT NOT NULL, amount REAL NOT NULL, source TEXT NOT NULL DEFAULT '', notes TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS price_history(id INTEGER PRIMARY KEY, date TEXT NOT NULL, product_id INTEGER NOT NULL REFERENCES products(id), market_price REAL NOT NULL, notes TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit_log(
            id INTEGER PRIMARY KEY, created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            action TEXT NOT NULL, details TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS form_submission_tokens(
            token TEXT PRIMARY KEY, action TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            consumed_at TEXT DEFAULT NULL
        );
        CREATE TABLE IF NOT EXISTS opening_capital(id INTEGER PRIMARY KEY CHECK(id=1), amount REAL NOT NULL DEFAULT 0, date TEXT NOT NULL);
        INSERT OR IGNORE INTO opening_capital(id,amount,date) VALUES(1,0,date('now'));
        CREATE TABLE IF NOT EXISTS people(
            id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, kind TEXT NOT NULL DEFAULT 'both',
            phone TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS settlements(
            id INTEGER PRIMARY KEY, date TEXT NOT NULL, party TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('receive','pay')),
            amount REAL NOT NULL CHECK(amount>0), notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS ix_settlements_date ON settlements(date,id);
        CREATE TABLE IF NOT EXISTS inventory_adjustments(
            id INTEGER PRIMARY KEY, date TEXT NOT NULL,
            product_id INTEGER NOT NULL REFERENCES products(id),
            expected_qty REAL NOT NULL, counted_qty REAL NOT NULL,
            delta_qty REAL NOT NULL, reason TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS ix_inventory_adjustments_product_date
            ON inventory_adjustments(product_id,date,id);
        CREATE TABLE IF NOT EXISTS purchase_returns(
            id INTEGER PRIMARY KEY, date TEXT NOT NULL,
            purchase_id INTEGER NOT NULL REFERENCES purchases(id),
            product_id INTEGER NOT NULL REFERENCES products(id),
            supplier TEXT NOT NULL DEFAULT '', qty REAL NOT NULL CHECK(qty>0),
            return_value REAL NOT NULL CHECK(return_value>0),
            cash_refund INTEGER NOT NULL DEFAULT 0 CHECK(cash_refund>=0),
            reason TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS ix_purchase_returns_purchase ON purchase_returns(purchase_id);
        CREATE TABLE IF NOT EXISTS sales_returns(
            id INTEGER PRIMARY KEY, date TEXT NOT NULL,
            sale_id INTEGER NOT NULL REFERENCES sales(id),
            product_id INTEGER NOT NULL REFERENCES products(id),
            customer TEXT NOT NULL DEFAULT '', qty REAL NOT NULL CHECK(qty>0),
            return_value REAL NOT NULL CHECK(return_value>0),
            cost_basis REAL NOT NULL DEFAULT 0,
            extra_reversed REAL NOT NULL DEFAULT 0,
            refund_amount INTEGER NOT NULL DEFAULT 0 CHECK(refund_amount>=0),
            reason TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS ix_sales_returns_sale ON sales_returns(sale_id);
        CREATE TABLE IF NOT EXISTS cash_accounts(
            id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, account_type TEXT NOT NULL DEFAULT 'cash',
            opening_balance INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS cash_movements(
            id INTEGER PRIMARY KEY, date TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('deposit','withdraw','transfer')),
            from_account_id INTEGER REFERENCES cash_accounts(id),
            to_account_id INTEGER REFERENCES cash_accounts(id),
            amount INTEGER NOT NULL CHECK(amount>0),
            party TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
            source_table TEXT NOT NULL DEFAULT '', source_id INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            CHECK((kind='deposit' AND from_account_id IS NULL AND to_account_id IS NOT NULL)
               OR (kind='withdraw' AND from_account_id IS NOT NULL AND to_account_id IS NULL)
               OR (kind='transfer' AND from_account_id IS NOT NULL AND to_account_id IS NOT NULL AND from_account_id<>to_account_id))
        );
        CREATE INDEX IF NOT EXISTS ix_cash_movements_date ON cash_movements(date,id);
        CREATE INDEX IF NOT EXISTS ix_cash_movements_source ON cash_movements(source_table,source_id);
        INSERT OR IGNORE INTO cash_accounts(id,name,account_type,opening_balance) VALUES
            (1,'صندوق نقدی','cash',0),(2,'حساب بانکی','bank',0);
        ''')
    # Safe additive migration; existing transactions and history are preserved.
    with conn() as c:
        # Table rebuilds below temporarily disable foreign-key enforcement on this connection.
        c.execute("PRAGMA foreign_keys=OFF")
        cols = {row['name'] for row in c.execute("PRAGMA table_info(products)")}
        for name, decl in {
            "category": "TEXT NOT NULL DEFAULT 'سایر'",
            "purchase_unit": "TEXT NOT NULL DEFAULT ''",
            "purchase_factor": "REAL NOT NULL DEFAULT 1",
            "sale_unit": "TEXT NOT NULL DEFAULT ''",
            "sale_factor": "REAL NOT NULL DEFAULT 1",
            "roll_weight": "REAL NOT NULL DEFAULT 0",
            "sheet_area": "REAL NOT NULL DEFAULT 0",
        }.items():
            if name not in cols:
                c.execute(f"ALTER TABLE products ADD COLUMN {name} {decl}")
        c.execute("UPDATE products SET purchase_unit=unit WHERE purchase_unit=''")
        c.execute("UPDATE products SET sale_unit=unit WHERE sale_unit=''")
        loan_cols = {row["name"] for row in c.execute("PRAGMA table_info(loans)")}
        for name, decl in {
            "interval_value": "INTEGER NOT NULL DEFAULT 1",
            "interval_unit": "TEXT NOT NULL DEFAULT 'month'",
        }.items():
            if name not in loan_cols:
                c.execute(f"ALTER TABLE loans ADD COLUMN {name} {decl}")
        # Add nullable foreign-key references so legacy text is preserved while records link to people.
        party_ref_specs = (
            ("purchases","supplier_person_id","supplier","supplier"),
            ("sales","customer_person_id","customer","customer"),
            ("services","customer_person_id","customer","customer"),
            ("settlements","person_id","party","both"),
            ("purchase_returns","supplier_person_id","supplier","supplier"),
            ("sales_returns","customer_person_id","customer","customer"),
        )
        for table_name, ref_column, text_column, party_kind in party_ref_specs:
            columns = {row["name"] for row in c.execute(f"PRAGMA table_info({table_name})")}
            if ref_column not in columns:
                c.execute(f"ALTER TABLE {table_name} ADD COLUMN {ref_column} INTEGER REFERENCES people(id)")
            for source_row in c.execute(
                f"SELECT id,{text_column} AS party_name FROM {table_name} WHERE {ref_column} IS NULL"
            ).fetchall():
                person_name = normalize_person(source_row["party_name"])
                if person_name:
                    person_id = ensure_person(c, person_name, party_kind)
                    c.execute(f"UPDATE {table_name} SET {ref_column}=? WHERE id=?", (person_id,source_row["id"]))
            c.execute(f"CREATE INDEX IF NOT EXISTS ix_{table_name}_{ref_column} ON {table_name}({ref_column})")
        # Keep party references linked even for records inserted/updated by an older code path.
        for table_name, ref_column, text_column, party_kind in party_ref_specs:
            c.execute(f"""CREATE TRIGGER IF NOT EXISTS trg_{table_name}_party_insert
                AFTER INSERT ON {table_name}
                WHEN TRIM(COALESCE(NEW.{text_column},''))<>'' AND NEW.{ref_column} IS NULL
                BEGIN
                    INSERT OR IGNORE INTO people(name,kind)
                        VALUES(TRIM(NEW.{text_column}),'{party_kind}');
                    UPDATE people SET kind=CASE
                        WHEN kind='both' THEN 'both'
                        WHEN '{party_kind}'='both' THEN kind
                        WHEN kind='{party_kind}' THEN kind ELSE 'both' END
                        WHERE name=TRIM(NEW.{text_column});
                    UPDATE {table_name}
                        SET {ref_column}=(SELECT id FROM people WHERE name=TRIM(NEW.{text_column}))
                        WHERE id=NEW.id AND {ref_column} IS NULL;
                END""")
            c.execute(f"""CREATE TRIGGER IF NOT EXISTS trg_{table_name}_party_update
                AFTER UPDATE OF {text_column} ON {table_name}
                WHEN TRIM(COALESCE(NEW.{text_column},''))<>''
                  AND (NEW.{ref_column} IS NULL OR NEW.{ref_column}<>(SELECT id FROM people WHERE name=TRIM(NEW.{text_column})))
                BEGIN
                    INSERT OR IGNORE INTO people(name,kind)
                        VALUES(TRIM(NEW.{text_column}),'{party_kind}');
                    UPDATE people SET kind=CASE
                        WHEN kind='both' THEN 'both'
                        WHEN '{party_kind}'='both' THEN kind
                        WHEN kind='{party_kind}' THEN kind ELSE 'both' END
                        WHERE name=TRIM(NEW.{text_column});
                    UPDATE {table_name}
                        SET {ref_column}=(SELECT id FROM people WHERE name=TRIM(NEW.{text_column}))
                        WHERE id=NEW.id;
                END""")
            c.execute(f"""CREATE TRIGGER IF NOT EXISTS trg_{table_name}_party_clear
                AFTER UPDATE OF {text_column} ON {table_name}
                WHEN TRIM(COALESCE(NEW.{text_column},''))=''
                  AND NEW.{ref_column} IS NOT NULL
                BEGIN
                    UPDATE {table_name} SET {ref_column}=NULL WHERE id=NEW.id;
                END""")
        # Seed the party directory from historical free-text names without rewriting source documents.
        for query, kind in (
            ("SELECT supplier FROM purchases", "supplier"),
            ("SELECT customer FROM sales", "customer"),
            ("SELECT customer FROM services", "customer"),
            ("SELECT party FROM settlements", "both"),
        ):
            for row in c.execute(query).fetchall():
                person_name = normalize_person(row[0])
                if person_name:
                    c.execute("INSERT OR IGNORE INTO people(name,kind) VALUES(?,?)", (person_name, kind))
        # Add lifecycle timestamps to legacy tables. Blank timestamps on old rows mean the
        # original creation time is unknown; new/updated rows are stamped automatically.
        timestamp_tables = (
            "products","purchases","sales","services","expenses","loans","loan_payments",
            "price_history","cash_events","people","cash_accounts","cash_movements",
            "settlements","inventory_adjustments","purchase_returns","sales_returns",
        )
        for table_name in timestamp_tables:
            columns = {row["name"] for row in c.execute(f"PRAGMA table_info({table_name})")}
            for column_name in ("created_at","updated_at"):
                if column_name not in columns:
                    c.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} TEXT NOT NULL DEFAULT ''")
            c.execute(f"""CREATE TRIGGER IF NOT EXISTS trg_{table_name}_stamp_insert
                AFTER INSERT ON {table_name}
                WHEN COALESCE(NEW.created_at,'')='' OR COALESCE(NEW.updated_at,'')=''
                BEGIN
                    UPDATE {table_name}
                    SET created_at=CASE WHEN COALESCE(NEW.created_at,'')='' THEN datetime('now','localtime') ELSE NEW.created_at END,
                        updated_at=CASE WHEN COALESCE(NEW.updated_at,'')='' THEN datetime('now','localtime') ELSE NEW.updated_at END
                    WHERE id=NEW.id;
                END""")
            c.execute(f"""CREATE TRIGGER IF NOT EXISTS trg_{table_name}_stamp_update
                AFTER UPDATE ON {table_name}
                WHEN NEW.updated_at=OLD.updated_at
                BEGIN
                    UPDATE {table_name} SET updated_at=datetime('now','localtime') WHERE id=NEW.id;
                END""")
        # A legacy opening-capital setting is an opening balance, not a transaction.
        opening = money_int(float(scalar(c, "SELECT amount FROM opening_capital WHERE id=1") or 0))
        current = scalar(c, "SELECT opening_balance FROM cash_accounts WHERE id=1")
        # A manual transfer must not prevent migration of the legacy opening cash balance.
        if opening and not current:
            c.execute("UPDATE cash_accounts SET opening_balance=?,updated_at=datetime('now','localtime') WHERE id=1", (opening,))
        migrated = backfill_legacy_cash_postings(c)
        if migrated:
            c.execute("INSERT INTO audit_log(action,details) VALUES(?,?)",
                      ("بازسازی گردش صندوق از اسناد قدیمی", json.dumps({"rows": migrated}, ensure_ascii=False)))
        fk_before=[tuple(row) for row in c.execute("PRAGMA foreign_key_check").fetchall()]
        converted_money_columns=migrate_money_columns_to_integer(c)
        fk_after=[tuple(row) for row in c.execute("PRAGMA foreign_key_check").fetchall()]
        if fk_after!=fk_before:
            raise RuntimeError("مهاجرت ستون‌های پولی باعث تغییر وضعیت کلیدهای خارجی شد؛ عملیات لغو شد.")
        c.commit()
        c.execute("PRAGMA foreign_keys=ON")

DIGIT_TRANSLATION = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
def num(v, default=0):
    try:
        cleaned = str(v).translate(DIGIT_TRANSLATION).replace(',', '').replace('٬', '').replace(' ', '').strip()
        return float(cleaned or default)
    except (ValueError, TypeError):
        return float(default)
def money_int(v, default=0):
    amount=num(v,default)
    # Round half away from zero consistently with SQLite ROUND() in the schema migration.
    return int(amount+0.5) if amount>=0 else int(amount-0.5)
def money(v): return f'{v:,.0f}'
def esc(v): return html.escape(str(v if v is not None else ''))
def fval(row,key,default=''):
    try:return row[key]
    except:return default

def scalar(c, sql, args=()):
    r=c.execute(sql,args).fetchone(); return (r[0] or 0) if r else 0

def normalize_person(value):
    """Normalize legacy free-text names for the directory, without changing transaction text."""
    return " ".join(str(value or "").split())

def account_balance(c, account_id):
    account = c.execute("SELECT opening_balance FROM cash_accounts WHERE id=?", (account_id,)).fetchone()
    if account is None:
        return 0
    incoming = scalar(c, "SELECT COALESCE(SUM(amount),0) FROM cash_movements WHERE to_account_id=?", (account_id,))
    outgoing = scalar(c, "SELECT COALESCE(SUM(amount),0) FROM cash_movements WHERE from_account_id=?", (account_id,))
    return int(account["opening_balance"] or 0) + int(incoming or 0) - int(outgoing or 0)

def sync_cash_posting(c, source_table, source_id, date, amount, direction, party="", note=""):
    """Idempotently mirror explicit paid/received cash amounts into the cash ledger."""
    c.execute("DELETE FROM cash_movements WHERE source_table=? AND source_id=?", (source_table, source_id))
    amount = money_int(float(amount or 0))
    if amount <= 0:
        return
    if direction == "in":
        c.execute("""INSERT INTO cash_movements(date,kind,to_account_id,amount,party,note,source_table,source_id)
                     VALUES(?,'deposit',1,?,?,?,?,?)""",
                  (date, amount, normalize_person(party), str(note or ""), source_table, source_id))
    elif direction == "out":
        c.execute("""INSERT INTO cash_movements(date,kind,from_account_id,amount,party,note,source_table,source_id)
                     VALUES(?,'withdraw',1,?,?,?,?,?)""",
                  (date, amount, normalize_person(party), str(note or ""), source_table, source_id))
    else:
        raise ValueError("جهت گردش نقدی نامعتبر است.")

def backfill_legacy_cash_postings(c):
    """Backfill only explicit historical receipts/payments; never infer return refunds."""
    specs = (
        ("purchases", "paid", "out", "supplier", "پرداخت خرید"),
        ("sales", "received", "in", "customer", "دریافت فروش"),
        ("services", "received", "in", "customer", "دریافت خدمات"),
        ("expenses", "amount", "out", "source", "پرداخت هزینه"),
        ("loan_payments", "amount", "out", "source", "پرداخت قسط وام"),
        ("purchase_returns", "cash_refund", "in", "supplier", "دریافت وجه مرجوعی خرید"),
        ("sales_returns", "refund_amount", "out", "customer", "پرداخت وجه مرجوعی فروش"),
    )
    inserted = 0
    for table, amount_col, direction, party_col, fallback in specs:
        rows = c.execute(
            f"""SELECT t.id,t.date,COALESCE(t.{amount_col},0) AS amount,
                       COALESCE(t.{party_col},'') AS party,COALESCE(t.notes,'') AS notes
                FROM {table} t
                WHERE COALESCE(t.{amount_col},0)>0
                  AND NOT EXISTS(SELECT 1 FROM cash_movements m
                                 WHERE m.source_table=? AND m.source_id=t.id)""",
            (table,),
        ).fetchall()
        for row in rows:
            sync_cash_posting(c, table, row["id"], row["date"], row["amount"], direction, row["party"], row["notes"] or fallback)
            inserted += 1
    for row in c.execute("""SELECT e.id,e.date,e.kind,e.amount,e.source,e.notes
            FROM cash_events e
            WHERE e.kind IN ('in','out') AND COALESCE(e.amount,0)>0
              AND NOT EXISTS(SELECT 1 FROM cash_movements m
                             WHERE m.source_table='cash_events' AND m.source_id=e.id)""").fetchall():
        sync_cash_posting(c, "cash_events", row["id"], row["date"], row["amount"], row["kind"], row["source"], row["notes"] or "رویداد نقدی")
        inserted += 1
    for row in c.execute("""SELECT s.id,s.date,s.kind,s.amount,s.party,s.notes
            FROM settlements s
            WHERE s.kind IN ('receive','pay') AND COALESCE(s.amount,0)>0
              AND NOT EXISTS(SELECT 1 FROM cash_movements m
                             WHERE m.source_table='settlements' AND m.source_id=s.id)""").fetchall():
        sync_cash_posting(c, "settlements", row["id"], row["date"], row["amount"],
                          "in" if row["kind"] == "receive" else "out",
                          row["party"], row["notes"] or "تسویه حساب")
        inserted += 1
    return inserted

def inventory_page(c, search='', page_num=1):
    limit,offset,page_num=page_window(page_num,50)
    query=str(search or '').strip(); pattern='%'+query+'%'
    total=scalar(c,"SELECT COUNT(*) FROM inventory_adjustments a JOIN products p ON p.id=a.product_id WHERE p.name LIKE ? OR a.reason LIKE ? OR a.notes LIKE ?",(pattern,pattern,pattern))
    products = options_products(c)
    body = f'''<h1>انبارگردانی و تعدیل موجودی</h1>
    <div class="card section"><h2>ثبت شمارش فیزیکی</h2>
      <form method="post" action="/inventory_adjust">
        <div class="formgrid">{field("تاریخ شمارش","date","date",TODAY,True)}
          {selectfield("کالا","product_id",products)}
          {field("موجودی شمارش‌شده به واحد پایه","counted_qty","number","0",True,"0.001")}
          {field("علت اختلاف/تعدیل","reason","text","",True)}
          {field("یادداشت","notes")}
        </div><div class="actions"><button>ثبت شمارش و اعمال تعدیل</button></div>
      </form>
      <p class="small">مقدار شمارش‌شده با موجودی دفتری مقایسه می‌شود. فقط اختلاف به‌عنوان گردش تعدیل ثبت می‌شود و بهای میانگین کالا دست‌کاری نمی‌شود. علت ثبت‌شده در سابقه باقی می‌ماند.</p>
    </div>'''
    rows = []
    for r in c.execute("""SELECT a.*,p.name,p.unit FROM inventory_adjustments a
                          JOIN products p ON p.id=a.product_id WHERE p.name LIKE ? OR a.reason LIKE ? OR a.notes LIKE ? ORDER BY a.date DESC,a.id DESC LIMIT ? OFFSET ?""",(pattern,pattern,pattern,limit,offset)):
        rows.append([show_date(r["date"]),esc(r["name"]),f'{r["expected_qty"]:g} {esc(r["unit"])}',
                     f'{r["counted_qty"]:g} {esc(r["unit"])}',
                     f'{r["delta_qty"]:+g} {esc(r["unit"])}',esc(r["reason"]),esc(r["notes"])])
    body += f'''<div class="card section"><h2>تاریخچه انبارگردانی</h2>
    <form method="get" action="/inventory" class="search-form"><label>جستجوی تعدیل</label><div class="formgrid"><input type="search" name="q" value="{esc(query)}" placeholder="کالا، علت یا یادداشت"><input type="hidden" name="page" value="1"><button>جستجو</button></div></form>
    {table(["تاریخ","کالا","موجودی دفتری","شمارش واقعی","اختلاف","علت","یادداشت"],rows,total)}{page_nav("inventory",query,page_num,total,limit)}</div>'''
    return page("انبارگردانی","".join([body]),"inventory")

def product_ledger_page(c, product_id, search="", page_num=1):
    p=c.execute("SELECT * FROM products WHERE id=?",(product_id,)).fetchone()
    if p is None:
        return page("کالا پیدا نشد",'<div class="notice">این کالا وجود ندارد.</div>',"products")
    limit,offset,page_num=page_window(page_num,50)
    query=str(search or '').strip(); pattern='%'+query+'%'
    movement_sql="""SELECT p.date AS date,p.id AS id,'purchase' AS source_type,'خرید' AS kind,
                           p.qty*COALESCE(pr.purchase_factor,1) AS delta,
                           'خرید #'||p.id||' · '||COALESCE(p.supplier,'') AS detail,
                           COALESCE(p.notes,'') AS notes
                    FROM purchases p JOIN products pr ON pr.id=p.product_id WHERE p.product_id=:pid
                    UNION ALL
                    SELECT s.date,s.id,'sale','فروش',-s.qty,
                           'فروش #'||s.id||' · '||COALESCE(s.customer,''),COALESCE(s.notes,'')
                    FROM sales s WHERE s.product_id=:pid
                    UNION ALL
                    SELECT r.date,r.id,'purchase_return','مرجوعی خرید',-r.qty,
                           'مرجوعی خرید #'||r.id||' · '||COALESCE(r.reason,''),COALESCE(r.notes,'')
                    FROM purchase_returns r WHERE r.product_id=:pid
                    UNION ALL
                    SELECT r.date,r.id,'sales_return','مرجوعی فروش',r.qty,
                           'مرجوعی فروش #'||r.id||' · '||COALESCE(r.reason,''),COALESCE(r.notes,'')
                    FROM sales_returns r WHERE r.product_id=:pid
                    UNION ALL
                    SELECT a.date,a.id,'adjustment','تعدیل انبار',a.delta_qty,
                           COALESCE(a.reason,''),COALESCE(a.notes,'')
                    FROM inventory_adjustments a WHERE a.product_id=:pid"""
    total_all,total_delta=c.execute(
        "SELECT COUNT(*),COALESCE(SUM(delta),0) FROM ("+movement_sql+") events",{"pid":product_id}
    ).fetchone()
    filtered_total=scalar(c,"SELECT COUNT(*) FROM ("+movement_sql+") e WHERE kind LIKE :pat OR detail LIKE :pat OR notes LIKE :pat",
                          {"pid":product_id,"pat":pattern})
    # Window aggregation is calculated before the outer search filter; searched results retain their true historical balances.
    event_rows=c.execute("""WITH events AS ("""+movement_sql+"""),
        rolled AS (
            SELECT events.*,
                   SUM(delta) OVER (ORDER BY date ASC,id ASC,source_type ASC
                                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_delta
            FROM events
        )
        SELECT * FROM rolled
        WHERE kind LIKE :pat OR detail LIKE :pat OR notes LIKE :pat
        ORDER BY date DESC,id DESC,source_type DESC LIMIT :limit OFFSET :offset""",
        {"pid":product_id,"pat":pattern,"limit":limit,"offset":offset}).fetchall()
    current=float(p["stock"] or 0)
    baseline=current-float(total_delta or 0)
    rows=[]
    for e in event_rows:
        delta=float(e["delta"] or 0)
        balance=baseline+float(e["running_delta"] or 0)
        rows.append([show_date(e["date"]),esc(e["kind"]),
                     f'{max(delta,0):g} {esc(p["unit"])}',
                     f'{max(-delta,0):g} {esc(p["unit"])}',
                     f'{balance:g} {esc(p["unit"])}',esc(e["detail"]),esc(e["notes"])])
    body=f'''<h1>کارت گردش کالا: {esc(p["name"])}</h1>
    <div class="grid section">
      <div class="card metric"><div class="label">موجودی فعلی</div><div class="value">{current:g} {esc(p["unit"])}</div></div>
      <div class="card metric"><div class="label">کل گردش‌های ثبت‌شده</div><div class="value">{int(total_all):,}</div></div>
      <div class="card metric"><div class="label">مانده پایه خارج از گردش ثبت‌شده</div><div class="value">{baseline:g} {esc(p["unit"])}</div><div class="muted">موجودی اولیه/تعدیلاتی که سند جداگانه ندارند</div></div>
    </div>
    <div class="card section"><p class="small">ماندهٔ هر ردیف از تمام گردش‌های قبلی محاسبه می‌شود؛ جستجو فقط ردیف‌های نمایشی را فیلتر می‌کند. در هر صفحه حداکثر ۵۰ گردش نمایش داده می‌شود.</p>
    <form method="get" action="/product_ledger" class="search-form"><input type="hidden" name="id" value="{int(product_id)}"><label>جستجوی گردش</label><div class="formgrid"><input type="search" name="q" value="{esc(query)}" placeholder="نوع گردش، طرف حساب یا یادداشت"><input type="hidden" name="page" value="1"><button>جستجو</button></div></form>
    {table(["تاریخ","نوع گردش","ورودی","خروجی","مانده پس از گردش","مرجع/طرف حساب","یادداشت"],rows,filtered_total)}
    {page_nav("product_ledger",query,page_num,filtered_total,limit,extra_params={"id":int(product_id)})}
    <div class="actions"><a class="btn secondary" href="/products">بازگشت به کالاها</a></div></div>'''
    return page("کارت گردش کالا",body,"products")

def cash_page(c, search='', page_num=1):
    limit,offset,page_num=page_window(page_num,50)
    query=str(search or '').strip(); pattern='%'+query+'%'
    total=scalar(c,"""SELECT COUNT(*) FROM cash_movements m
        LEFT JOIN cash_accounts fa ON fa.id=m.from_account_id
        LEFT JOIN cash_accounts ta ON ta.id=m.to_account_id
        WHERE COALESCE(fa.name,'') LIKE ? OR COALESCE(ta.name,'') LIKE ?
           OR COALESCE(m.party,'') LIKE ? OR COALESCE(m.note,'') LIKE ? OR m.kind LIKE ?""",
        (pattern,pattern,pattern,pattern,pattern))
    accounts = c.execute("SELECT * FROM cash_accounts ORDER BY id").fetchall()
    opts = "".join(f'<option value="{r["id"]}">{esc(r["name"])}</option>' for r in accounts)
    metrics = "".join(
        f'<div class="card metric"><div class="label">{esc(r["name"])}</div><div class="value">{money(account_balance(c,r["id"]))} تومان</div><div class="muted">مانده افتتاحیه: {money(r["opening_balance"])} تومان</div></div>'
        for r in accounts
    )
    rows = []
    for r in c.execute("""SELECT m.*,fa.name AS from_name,ta.name AS to_name
                          FROM cash_movements m
                          LEFT JOIN cash_accounts fa ON fa.id=m.from_account_id
                          LEFT JOIN cash_accounts ta ON ta.id=m.to_account_id
                          WHERE COALESCE(fa.name,'') LIKE ? OR COALESCE(ta.name,'') LIKE ?
                             OR COALESCE(m.party,'') LIKE ? OR COALESCE(m.note,'') LIKE ? OR m.kind LIKE ?
                          ORDER BY m.date DESC,m.id DESC LIMIT ? OFFSET ?""",
                       (pattern,pattern,pattern,pattern,pattern,limit,offset)):
        label = {"deposit":"واریز/دریافت","withdraw":"برداشت/پرداخت","transfer":"انتقال بین حساب‌ها"}.get(r["kind"],r["kind"])
        rows.append([show_date(r["date"]),label,esc(r["from_name"] or "—"),esc(r["to_name"] or "—"),
                     money(r["amount"]),esc(r["party"]),esc(r["note"]),
                     "ثبت خودکار" if r["source_table"] else "ثبت دستی"])
    body = f'''<h1>صندوق و حساب‌های بانکی</h1>
    <div class="grid section">{metrics}</div>
    <div class="card section"><h2>ثبت گردش دستی</h2>
      <form method="post" action="/add_cash_movement">
        <div class="formgrid">{field("تاریخ","date","date",TODAY,True)}
          {selectfield("نوع گردش","kind",[("deposit","واریز به حساب"),("withdraw","برداشت از حساب"),("transfer","انتقال بین حساب‌ها")])}
          <label>حساب مبدأ<select name="from_account_id"><option value="">— انتخاب حساب —</option>{opts}</select></label>
          <label>حساب مقصد<select name="to_account_id"><option value="">— انتخاب حساب —</option>{opts}</select></label>
          {field("مبلغ (تومان)","amount","number","0",True,"1")}
          {field("طرف حساب","party")}{field("شرح","note")}
        </div><div class="actions"><button>ثبت گردش</button></div>
      </form>
      <p class="small">مبالغ گردش صندوق به تومانِ صحیح ثبت می‌شوند. مبالغ پرداخت/دریافت ثبت‌شده در سندهای خرید، فروش، خدمات، هزینه و اقساط به‌طور خودکار وارد دفتر می‌شوند.</p>
    </div>
    <div class="card section"><h2>گردش‌های صندوق و بانک</h2>
    <form method="get" action="/cash" class="search-form"><label>جستجوی گردش</label><div class="formgrid">
    <input type="search" name="q" value="{esc(query)}" placeholder="حساب، طرف حساب یا شرح">
    <input type="hidden" name="page" value="1"><button>جستجو</button></div></form>
    {table(["تاریخ","نوع","از حساب","به حساب","مبلغ","طرف حساب","شرح","منبع"],rows,total)}
    {page_nav("cash",query,page_num,total,limit)}</div>'''
    return page("صندوق و بانک",body,"cash")

def ensure_person(c, name, kind="both", phone="", notes=""):
    name = normalize_person(name)
    if not name:
        return None
    row = c.execute("SELECT id,kind FROM people WHERE name=?", (name,)).fetchone()
    if row is None:
        cur = c.execute("INSERT INTO people(name,kind,phone,notes) VALUES(?,?,?,?)", (name,kind,phone,notes))
        return cur.lastrowid
    if kind and row["kind"] not in (kind,"both") and kind != "both":
        c.execute("UPDATE people SET kind='both',updated_at=datetime('now','localtime') WHERE id=?", (row["id"],))
    return row["id"]

def link_party(c, table_name, ref_column, record_id, name, kind="both"):
    """Create/reuse a party and persist its nullable foreign-key reference on a known ledger table."""
    allowed = {
        ("purchases","supplier_person_id"),("sales","customer_person_id"),
        ("services","customer_person_id"),("settlements","person_id"),
        ("purchase_returns","supplier_person_id"),("sales_returns","customer_person_id"),
    }
    if (table_name,ref_column) not in allowed:
        raise ValueError("ارتباط طرف حساب معتبر نیست.")
    person_id = ensure_person(c,name,kind)
    if record_id and person_id:
        c.execute(f"UPDATE {table_name} SET {ref_column}=? WHERE id=?", (person_id,int(record_id)))
    return person_id

def party_balances(c):
    balances = {}
    def add(name, key, amount):
        name = normalize_person(name) or "(بدون نام)"
        item = balances.setdefault(name, {"receivable": 0.0, "payable": 0.0})
        item[key] += float(amount or 0)
    for row in c.execute("SELECT TRIM(customer) name,SUM(qty*unit_price-received) amount FROM sales GROUP BY TRIM(customer)"):
        add(row["name"],"receivable",row["amount"])
    for row in c.execute("SELECT TRIM(customer) name,SUM(revenue-received) amount FROM services GROUP BY TRIM(customer)"):
        add(row["name"],"receivable",row["amount"])
    for row in c.execute("SELECT TRIM(party) name,SUM(amount) amount FROM settlements WHERE kind='receive' GROUP BY TRIM(party)"):
        add(row["name"],"receivable",-row["amount"])
    for row in c.execute("SELECT TRIM(customer) name,SUM(-return_value+refund_amount) amount FROM sales_returns GROUP BY TRIM(customer)"):
        add(row["name"],"receivable",row["amount"])
    for row in c.execute("SELECT TRIM(supplier) name,SUM(qty*unit_cost+extra_cost-paid) amount FROM purchases GROUP BY TRIM(supplier)"):
        add(row["name"],"payable",row["amount"])
    for row in c.execute("SELECT TRIM(party) name,SUM(amount) amount FROM settlements WHERE kind='pay' GROUP BY TRIM(party)"):
        add(row["name"],"payable",-row["amount"])
    for row in c.execute("SELECT TRIM(supplier) name,SUM(-return_value+cash_refund) amount FROM purchase_returns GROUP BY TRIM(supplier)"):
        add(row["name"],"payable",row["amount"])
    return balances

def parties_page(c, selected="", search="", page_num=1, statement_page=1):
    balances = party_balances(c)
    limit,offset,page_num=page_window(page_num,50)
    query=str(search or '').strip(); pattern='%'+query+'%'
    total=scalar(c,"SELECT COUNT(*) FROM people WHERE name LIKE ? OR phone LIKE ? OR notes LIKE ? OR kind LIKE ?",(pattern,pattern,pattern,pattern))
    people = c.execute("SELECT * FROM people WHERE name LIKE ? OR phone LIKE ? OR notes LIKE ? OR kind LIKE ? ORDER BY name LIMIT ? OFFSET ?",
                       (pattern,pattern,pattern,pattern,limit,offset)).fetchall()
    all_people = c.execute("SELECT name FROM people ORDER BY name").fetchall()
    rows = []
    from urllib.parse import quote
    for person in people:
        bal = balances.get(person["name"], {"receivable":0,"payable":0})
        rows.append([esc(person["name"]),esc(person["kind"]),esc(person["phone"]),
                     money(bal["receivable"]),money(bal["payable"]),
                     f'<a class="btn secondary" href="/parties?name={quote(person["name"])}">ریز حساب</a>'])
    person_opts = [(p["name"],p["name"]) for p in all_people]
    body = f'''<h1>طرف حساب‌ها و مانده اشخاص</h1>
    <div class="card section"><h2>ورود و خروج اکسل اشخاص</h2><div class="actions"><a class="btn" href="/export.xlsx">دانلود الگوی اکسل و اطلاعات</a></div>
    <form method="post" action="/import.xlsx" enctype="multipart/form-data"><input type="hidden" name="sheet" value="People"><div class="formgrid"><label>فایل XLSX اشخاص<input type="file" name="file" accept=".xlsx" required></label></div><div class="actions"><button>ورود اشخاص</button></div><p class="small">ستون‌های name، kind، phone و notes پشتیبانی می‌شوند. اشخاص با نام تکراری وارد نمی‌شوند.</p></form></div>
    <div class="card section"><h2>ثبت شخص جدید</h2><form method="post" action="/add_person"><div class="formgrid">
    {field("نام و نام خانوادگی/شرکت","name","text","",True)}
    {selectfield("نوع طرف حساب","kind",[("customer","مشتری"),("supplier","فروشنده"),("both","هر دو")])}
    {field("شماره تماس","phone")}{field("یادداشت","notes")}
    </div><div class="actions"><button>ثبت طرف حساب</button></div></form></div>
    <div class="card section"><h2>ثبت تسویه با شخص</h2><form method="post" action="/add_settlement"><div class="formgrid">
    {selectfield("طرف حساب","party",person_opts)}{selectfield("نوع تسویه","kind",[("receive","دریافت از مشتری"),("pay","پرداخت به فروشنده")])}
    {field("تاریخ","date","date",TODAY,True)}{field("مبلغ تسویه (تومان)","amount","number","0",True,"1")}
    {field("شرح/یادداشت","notes")}
    </div><div class="actions"><button>ثبت تسویه و به‌روزرسانی صندوق</button></div></form></div>
    <div class="card section"><h2>مانده اشخاص</h2>
    <form method="get" action="/parties" class="search-form"><label>جستجوی طرف حساب</label><div class="formgrid"><input type="search" name="q" value="{esc(query)}" placeholder="نام، نوع، تماس یا یادداشت"><input type="hidden" name="page" value="1"><button>جستجو</button></div></form>
    {table(["نام","نوع","تماس","طلب ما از شخص","بدهی ما به شخص","ریز حساب"],rows,total)}
    {page_nav("parties",query,page_num,total,limit)}</div>'''
    selected = normalize_person(selected)
    if selected:
        stmt_limit,stmt_offset,statement_page=page_window(statement_page,50)
        statement_sql="""SELECT id,date,'فروش کالا' AS kind,
                                  qty*unit_price AS total,received AS settled,notes,'sales' AS source_type,
                                  qty*unit_price-received AS receivable_delta,0 AS payable_delta
                           FROM sales WHERE TRIM(customer)=:person
                           UNION ALL
                           SELECT id,date,'خدمات',revenue,received,notes,'services',
                                  revenue-received,0
                           FROM services WHERE TRIM(customer)=:person
                           UNION ALL
                           SELECT id,date,'خرید',qty*unit_cost+extra_cost,paid,notes,'purchases',
                                  0,qty*unit_cost+extra_cost-paid
                           FROM purchases WHERE TRIM(supplier)=:person
                           UNION ALL
                           SELECT id,date,
                                  CASE WHEN kind='receive' THEN 'دریافت تسویه' ELSE 'پرداخت تسویه' END,
                                  -amount,0,notes,'settlements',
                                  CASE WHEN kind='receive' THEN -amount ELSE 0 END,
                                  CASE WHEN kind='pay' THEN -amount ELSE 0 END
                           FROM settlements WHERE TRIM(party)=:person
                           UNION ALL
                           SELECT id,date,'مرجوعی فروش',-return_value,-refund_amount,notes,'sales_returns',
                                  -return_value+refund_amount,0
                           FROM sales_returns WHERE TRIM(customer)=:person
                           UNION ALL
                           SELECT id,date,'مرجوعی خرید',-return_value,-cash_refund,notes,'purchase_returns',
                                  0,-return_value+cash_refund
                           FROM purchase_returns WHERE TRIM(supplier)=:person"""
        statement_params={"person":selected}
        statement_total=scalar(c,"SELECT COUNT(*) FROM ("+statement_sql+") statement_rows",statement_params)
        statement=c.execute("""WITH raw AS ("""+statement_sql+"""),
            rolled AS (
                SELECT raw.*,
                       (COALESCE(total,0)-COALESCE(settled,0)) AS effect,
                       SUM(receivable_delta) OVER (
                           ORDER BY date ASC,id ASC,source_type ASC
                           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS receivable_balance,
                       SUM(payable_delta) OVER (
                           ORDER BY date ASC,id ASC,source_type ASC
                           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS payable_balance
                FROM raw
            )
            SELECT * FROM rolled
            ORDER BY date DESC,id DESC,source_type DESC
            LIMIT :limit OFFSET :offset""",
            {**statement_params,"limit":stmt_limit,"offset":stmt_offset}).fetchall()
        details=[[show_date(r["date"]),esc(r["kind"]),money(r["total"]),money(r["settled"]),
                  money(r["effect"]),money(r["receivable_balance"]),money(r["payable_balance"]),esc(r["notes"] or "")]
                 for r in statement]
        body += f'''<div class="card section"><h2>ریز حساب: {esc(selected)}</h2>
        <p class="small">اثر هر سند بر مانده و دو ماندهٔ تجمعی دریافتنی/پرداختنی پیش از صفحه‌بندی با SQL محاسبه می‌شوند. مرجوعی و تسویه در گردش تجمعی لحاظ می‌شوند.</p>
        {table(["تاریخ","شرح","مبلغ سند","پرداخت/دریافت این سند","اثر بر مانده","مانده تجمعی دریافتنی","مانده تجمعی پرداختنی","یادداشت"],details,statement_total)}
        {page_nav("parties","",statement_page,statement_total,stmt_limit,extra_params={"name":selected},query_key=None,page_key="spage")}
        <div class="actions"><a class="btn secondary" href="/parties">بستن ریز حساب</a></div></div>'''
    return page("طرف حساب‌ها",body,"parties")

def calc(c, start=None, end=None):
    where=''; args=[]
    if start and end: where=' WHERE date BETWEEN ? AND ?'; args=[start,end]
    elif start: where=' WHERE date >= ?'; args=[start]
    elif end: where=' WHERE date <= ?'; args=[end]
    sales_rev=scalar(c,'SELECT COALESCE(SUM(qty*unit_price),0) FROM sales'+where,args)
    sales_cost=scalar(c,'SELECT COALESCE(SUM(qty*cost_basis),0) FROM sales'+where,args)
    sales_extra=scalar(c,'SELECT COALESCE(SUM(extra_cost),0) FROM sales'+where,args)
    sales_return_where=where.replace("date","date")
    sales_rev-=scalar(c,'SELECT COALESCE(SUM(return_value),0) FROM sales_returns'+sales_return_where,args)
    sales_cost-=scalar(c,'SELECT COALESCE(SUM(qty*cost_basis),0) FROM sales_returns'+sales_return_where,args)
    sales_extra-=scalar(c,'SELECT COALESCE(SUM(extra_reversed),0) FROM sales_returns'+sales_return_where,args)
    service_rev=scalar(c,'SELECT COALESCE(SUM(revenue),0) FROM services'+where,args)
    service_cost=scalar(c,'SELECT COALESCE(SUM(cost),0) FROM services'+where,args)
    exp=scalar(c,'SELECT COALESCE(SUM(amount),0) FROM expenses'+where+' AND business=1' if where else 'SELECT COALESCE(SUM(amount),0) FROM expenses WHERE business=1',args)
    # Only interest is an expense; principal repayments reduce cash/debt, not profit.
    interest=scalar(c,'SELECT COALESCE(SUM(interest_part),0) FROM loan_payments'+where,args)
    gross=(sales_rev-sales_cost-sales_extra)+(service_rev-service_cost)
    net=gross-exp-interest
    paid_exp=scalar(c,'SELECT COALESCE(SUM(amount),0) FROM expenses'+where,args)
    loan_paid=scalar(c,'SELECT COALESCE(SUM(amount),0) FROM loan_payments'+where,args)
    sales_received=scalar(c,'SELECT COALESCE(SUM(received),0) FROM sales'+where,args)
    services_received=scalar(c,'SELECT COALESCE(SUM(received),0) FROM services'+where,args)
    purchases_paid=scalar(c,'SELECT COALESCE(SUM(paid),0) FROM purchases'+where,args)
    return dict(sales_rev=sales_rev,sales_cost=sales_cost,sales_extra=sales_extra,service_rev=service_rev,service_cost=service_cost,exp=exp,interest=interest,gross=gross,net=net,paid_exp=paid_exp,loan_paid=loan_paid,sales_received=sales_received,services_received=services_received,purchases_paid=purchases_paid)

def dashboard_sales_chart(c, month_limit=6):
    """Compact CSS bar chart of sales/services grouped by Jalali month."""
    buckets={}
    def add(sql,key,sign=1):
        for row in c.execute(sql):
            if not row["date"]:
                continue
            try:
                gy,gm,gd=map(int,str(row["date"]).split("-")[:3])
                jy,jm,jd=gregorian_to_jalali(gy,gm,gd)
            except (TypeError,ValueError):
                continue
            b=buckets.setdefault((jy,jm),{"sales":0.0,"services":0.0})
            b[key]+=sign*float(row["value"] or 0)
    add("SELECT date,SUM(qty*unit_price) value FROM sales GROUP BY date","sales")
    add("SELECT date,SUM(return_value) value FROM sales_returns GROUP BY date","sales",-1)
    add("SELECT date,SUM(revenue) value FROM services GROUP BY date","services")
    latest=sorted(buckets.items(),key=lambda item:item[0],reverse=True)[:max(1,min(12,int(month_limit)))]
    latest=list(reversed(latest))
    max_value=max((max(0,b[k]) for _,b in latest for k in ("sales","services")),default=0)
    groups=[]
    for (jy,jm),b in latest:
        sales_pct=100*max(0,b["sales"])/max_value if max_value else 0
        service_pct=100*max(0,b["services"])/max_value if max_value else 0
        label=f"{jy:04d}/{jm:02d}"
        groups.append(f'''<div class="bar-chart-group" aria-label="ماه {label}">
          <div class="bar-chart-bars">
            <div class="bar-chart-item"><span class="bar-chart-value">{money(b["sales"])}</span><div class="bar-chart-track"><svg class="bar-chart-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><rect class="bar-chart-fill sales" x="0" y="{100-sales_pct:.1f}" width="100" height="{sales_pct:.1f}" rx="3"></rect></svg></div><small>فروش کالا</small></div>
            <div class="bar-chart-item"><span class="bar-chart-value">{money(b["services"])}</span><div class="bar-chart-track"><svg class="bar-chart-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><rect class="bar-chart-fill services" x="0" y="{100-service_pct:.1f}" width="100" height="{service_pct:.1f}" rx="3"></rect></svg></div><small>خدمات</small></div>
          </div><strong>{label}</strong></div>''')
    if not groups:
        return '<div class="card section"><h2>نمودار فروش ماهانه</h2><p class="empty">برای ترسیم نمودار، ابتدا فروش یا خدمات ثبت کن.</p></div>'
    return '<div class="card section"><h2>روند فروش ماهانه</h2><p class="small">جمع فروش کالا پس از کسر مرجوعی و درآمد خدمات، در ماه‌های شمسی دارای تراکنش. این نمودار درآمد است، نه سود خالص.</p><div class="bar-chart-legend"><span><i class="legend-swatch sales"></i> فروش خالص کالا</span><span><i class="legend-swatch services"></i> درآمد خدمات</span></div><div class="bar-chart">'+"".join(groups)+'</div></div>'

NAV_GROUPS=[
    ('روزانه',[('sales','فروش','receipt'),('purchases','خرید','cart'),('returns','مرجوعی‌ها','refresh-cw'),('services','خدمات','tool'),('expenses','هزینه‌ها','wallet')]),
    ('انبار',[('products','کالاها و موجودی','box'),('inventory','انبارگردانی','receipt'),('buy-advice','پیشنهاد خرید','cart'),('prices','قیمت روز','chart')]),
    ('گزارش‌ها',[('reports','گزارش‌ها','chart')]),
    ('مالی',[('cash','صندوق و بانک','wallet'),('parties','طرف حساب‌ها','users')]),
    ('مدیریت',[('loans','وام‌ها','calendar'),('audit','گزارش ممیزی','shield-check'),('settings','تنظیمات','settings'),('design','سیستم طراحی','grid')]),
]
def svg_icon(name, cls='icon'):
    return f'<svg class="{cls}" aria-hidden="true" focusable="false"><use href="/static/icons.svg#{esc(name)}"></use></svg>'

def page(title, body, active='', msg=''):
    groups=[]
    for group_label, items in NAV_GROUPS:
        links=[]
        for key, label, icon in items:
            href='/' if not key else f'/{key}'
            links.append(f'<a class="nav-link {"active" if key==active else ""}" href="{href}" title="{esc(label)}">{svg_icon(icon)}<span>{esc(label)}</span></a>')
        groups.append(f'<section class="nav-group"><h2 class="nav-group-label">{esc(group_label)}</h2>{"".join(links)}</section>')
    backup_items=sorted((DATA / 'backups').glob('business_*.db'), key=lambda p:p.stat().st_mtime, reverse=True) if (DATA / 'backups').exists() else []
    backup_label='پشتیبان ثبت نشده'; backup_class='backup-chip stale'
    if backup_items:
        age=datetime.datetime.now()-datetime.datetime.fromtimestamp(backup_items[0].stat().st_mtime)
        backup_class='backup-chip stale' if age.days>=7 else 'backup-chip'
        backup_label='آخرین پشتیبان: '+('کمتر از یک ساعت پیش' if age.total_seconds()<3600 else (f'{age.days} روز پیش' if age.days else f'{age.seconds//3600} ساعت پیش'))
    today_label=show_date(TODAY)
    return f'''<!doctype html><html lang="fa" dir="rtl" data-theme="light"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark"><title>{esc(title)} | آهن‌مدیریت</title><link rel="stylesheet" href="/static/tokens.css"><link rel="stylesheet" href="/static/app.css"><script src="/static/app.js" defer></script></head><body>
    <div class="app-shell"><aside class="sidebar" id="app-sidebar"><a class="brand" href="/"><span class="brand-mark">{svg_icon('grid')}</span><span>آهن‌مدیریت</span></a><button type="button" class="secondary sidebar-collapse" id="sidebar-collapse" aria-label="جمع کردن منو">{svg_icon('chevron')}</button><nav class="nav-groups">{"".join(groups)}</nav><div class="sidebar-bottom"><span class="status-chip">{svg_icon('shield')}اطلاعات روی همین دستگاه ذخیره می‌شود</span></div></aside>
    <div class="app-main"><header class="topbar"><button type="button" class="secondary mobile-menu" id="mobile-menu" aria-label="باز کردن منو">{svg_icon('menu')}</button><div class="topbar-heading"><strong>{esc(title)}</strong><span class="breadcrumb">خانه / {esc(title)}</span></div><label class="global-search">{svg_icon('search')}<input id="global-search" type="search" placeholder="جستجوی صفحه یا اقدام" aria-label="جستجوی سراسری"><kbd>Ctrl K</kbd></label><div class="topbar-actions"><span class="date-chip">{svg_icon('calendar')}<span>امروز {esc(today_label)}</span></span><span class="{backup_class}">{svg_icon('backup')}{esc(backup_label)}</span><button type="button" class="secondary" id="theme-toggle" aria-label="تغییر تم" title="تغییر تم">{svg_icon('moon')}</button><details class="quick-menu"><summary class="btn" title="ثبت سریع">{svg_icon('plus')}ثبت سریع</summary><div class="quick-items"><a href="/sales">فروش جدید</a><a href="/purchases">خرید جدید</a><a href="/expenses">ثبت هزینه</a><a href="/settings">پشتیبان‌گیری</a></div></details><button type="button" class="secondary" id="command-open" aria-label="جستجوی فرمان‌ها" title="جستجوی فرمان‌ها">{svg_icon('command')}</button></div></header>
    <main><div class="page-body">{f'<div class="success" role="status">{esc(msg)}</div>' if msg else ''}{body}</div></main><footer class="statusbar"><span>پایگاه داده: {esc(DB.name)}</span><span>همه‌چیز روی همین دستگاه ذخیره می‌شود</span><span>آهن‌مدیریت · نسخه ۳</span></footer></div></div>
    <div class="command-overlay" id="command-palette" aria-hidden="true"><section class="command-dialog" role="dialog" aria-modal="true" aria-labelledby="command-title"><div class="command-head"><h2 id="command-title">جستجو و اقدامات</h2><button type="button" class="secondary" id="command-close" aria-label="بستن">{svg_icon('close')}</button></div><input id="command-input" type="search" placeholder="نام صفحه یا اقدام را بنویس"><div id="command-list" class="command-list"></div><p class="small">میان‌بر: Ctrl+K · بستن: Esc</p></section></div>
    <dialog id="confirm-dialog" class="confirm-dialog"><h2 id="confirm-title">تأیید عملیات</h2><p id="confirm-description">این عملیات را تأیید می‌کنی؟</p><label>برای ادامه عبارت تأیید را وارد کن<input id="confirm-phrase" autocomplete="off"></label><div class="actions"><button type="button" class="secondary" id="confirm-cancel">انصراف</button><button type="button" class="danger" id="confirm-accept" disabled>تأیید</button></div></dialog>
    </body></html>'''
def design_page(c=None):
    body='''<h1>سیستم طراحی</h1><section class="section"><p class="muted">این صفحه برای مرور چشمی توکن‌ها، اجزای پایه و حالت‌های رابط ساخته شده است. رنگ‌ها و فاصله‌ها از فایل‌های محلی سیستم طراحی می‌آیند.</p></section>
    <section class="card section"><h2>پالت رنگ</h2><div class="palette-grid"><div><h3>برند</h3><div class="swatch swatch-brand"><span>Brand</span></div></div><div><h3>خنثی</h3><div class="swatch swatch-neutral"><span>Neutral</span></div></div><div><h3>وضعیت‌های معنایی</h3><div class="state-row"><span class="badge success">موفق · بستانکار</span><span class="badge warning">هشدار · نزدیک سررسید</span><span class="badge danger">خطر · بدهکار</span><span class="badge info">اطلاع · پیش‌نویس</span></div></div></div></section>
    <section class="card section"><h2>حالت دکمه‌ها</h2><div class="state-row"><button>اصلی</button><button class="secondary">ثانویه</button><button class="neutral">خنثی</button><button class="ghost">متنی</button><button class="danger">خطرناک</button><button disabled>غیرفعال</button><button><span class="spinner" aria-hidden="true"></span>در حال ذخیره</button></div><div class="actions"><button class="sm secondary">کوچک</button><button class="secondary">معمولی</button><button class="lg secondary">بزرگ</button></div></section>
    <section class="card section"><h2>فیلدها و خطا</h2><div class="formgrid"><div class="field"><label for="demo-name">نام کالا</label><input id="demo-name" value="پروفیل ۲ میلی‌متر"><span class="help">برچسب بالای ورودی و راهنما زیر آن</span></div><div class="field"><label for="demo-amount">مبلغ (تومان)</label><input id="demo-amount" value="۲٬۵۰۰٬۰۰۰" inputmode="numeric"><span class="help">قالب‌بندی نمونه مبلغ</span></div><div class="field error"><label for="demo-error">حالت خطا</label><input id="demo-error" aria-invalid="true" value="تاریخ نامعتبر"><span class="error">تاریخ معتبر نیست؛ مقدار را اصلاح کن.</span></div></div></section>
    <section class="card section"><h2>جدول و شمارنده</h2><div class="tablewrap"><table><thead><tr><th>کالا</th><th>موجودی</th><th>وضعیت</th><th>مانده</th></tr></thead><tbody><tr><td>پروفیل ۲ میلی‌متر</td><td>۱۲۰ شاخه</td><td><span class="badge success">موجود</span></td><td>− ۳٬۰۰۰٬۰۰۰ · بدهکار</td></tr><tr><td>ورق روغنی</td><td>۵ برگ</td><td><span class="badge warning">کم‌موجودی</span></td><td>+ ۸۵۰٬۰۰۰ · بستانکار</td></tr></tbody></table></div><div class="table-count">نمایش ۱ تا ۲ از ۱٬۲۴۰ مورد · صفحه ۱ از ۶۲۰</div></section>
    <section class="twocol section"><div class="card"><h2>حالت خالی</h2><div class="empty"><strong>هنوز فروشی ثبت نشده است.</strong><span class="small">اولین فروش را ثبت کن.</span><a class="btn" href="/sales">ثبت فروش</a></div></div><div class="card"><h2>در حال بارگذاری</h2><span class="loading-skeleton"></span><span class="loading-skeleton"></span><span class="loading-skeleton"></span></div></section>
    <section class="card section"><h2>وضعیت پیام‌ها</h2><div class="success" role="status">ذخیره شد؛ اطلاعات ثبت شدند.</div><div class="notice err" role="alert">ذخیره انجام نشد؛ پایگاه داده قفل است. کمی بعد دوباره تلاش کن.</div></section>'''
    return page('سیستم طراحی',body,'design')

MONEY_FIELDS = {'unit_cost','unit_price','extra_cost','paid','received','revenue','cost','amount','principal','remaining','installment','principal_part','interest_part','market_price','avg_cost','capital','refund_amount','cash_refund'}
def field(label,name,typ='text',value='',required=False,step=None,placeholder=''):
    req='required' if required else ''
    st=f' step="{step}"' if step and typ != 'date' else ''
    attrs=''
    if typ == 'date':
        typ = 'text'
        value = show_date(value) if value else show_date(TODAY)
        placeholder = placeholder or '۱۴۰۵/۰۷/۰۱'
        today_value=show_date(TODAY)
        yesterday_value=show_date((datetime.date.today()-datetime.timedelta(days=1)).isoformat())
        attrs = f' data-date-input="true" data-today="{today_value}" data-yesterday="{yesterday_value}" autocomplete="off"'
    if typ == 'number':
        typ = 'text'
        attrs += ' inputmode="decimal" data-numeric="true"'
        if name in MONEY_FIELDS:
            attrs += ' data-money="true" data-unit="تومان"'
    ph=f' placeholder="{esc(placeholder)}"' if placeholder else ''
    safe_name=esc(name)
    monetary = f'<span class="field-unit">تومان</span><span class="amount-words" data-words-for="{safe_name}" aria-live="polite"></span>' if name in MONEY_FIELDS and 'data-money="true"' in attrs else ''
    return f'<div class="field"><label for="field-{safe_name}">{label}</label><div class="input-wrap"><input id="field-{safe_name}" name="{safe_name}" type="{typ}" value="{esc(value)}" {req}{st}{attrs}{ph}></div>{monetary}</div>'
def selectfield(label,name,opts,required=True,value=None):
    opt=''.join(f'<option value="{esc(v)}" {"selected" if value is not None and str(v)==str(value) else ""}>{esc(t)}</option>' for v,t in opts)
    safe_name=esc(name)
    return f'<div class="field"><label for="field-{safe_name}">{label}</label><select id="field-{safe_name}" name="{safe_name}" {"required" if required else ""}>{opt}</select></div>'
XLSX_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XLSX_OFFICE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
XLSX_PACKAGE_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
XLSX_CONTENT_TYPES = "http://schemas.openxmlformats.org/package/2006/content-types"
ET.register_namespace("", XLSX_MAIN)
ET.register_namespace("r", XLSX_OFFICE_REL)

def _xlsx_column_name(number):
    name = ""
    while number:
        number, rem = divmod(number-1, 26)
        name = chr(65+rem) + name
    return name

def _xlsx_sheet_xml(rows):
    root = ET.Element(f"{{{XLSX_MAIN}}}worksheet")
    data = ET.SubElement(root, f"{{{XLSX_MAIN}}}sheetData")
    for row_num, values in enumerate(rows, 1):
        row = ET.SubElement(data, f"{{{XLSX_MAIN}}}row", {"r": str(row_num)})
        for col_num, value in enumerate(values, 1):
            if value is None:
                value = ""
            cell = ET.SubElement(row, f"{{{XLSX_MAIN}}}c", {"r": f"{_xlsx_column_name(col_num)}{row_num}"})
            if isinstance(value, bool):
                value = int(value)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                node = ET.SubElement(cell, f"{{{XLSX_MAIN}}}v")
                node.text = str(value)
            else:
                cell.set("t", "inlineStr")
                inline = ET.SubElement(cell, f"{{{XLSX_MAIN}}}is")
                node = ET.SubElement(inline, f"{{{XLSX_MAIN}}}t")
                node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                node.text = str(value)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)

def build_xlsx_workbook(sheets):
    """Build a standards-based XLSX file using only the Python standard library."""
    if not sheets:
        raise ValueError("برای ساخت فایل اکسل، حداقل یک برگه لازم است.")
    out = io.BytesIO()
    content_types = ET.Element(f"{{{XLSX_CONTENT_TYPES}}}Types")
    ET.SubElement(content_types, f"{{{XLSX_CONTENT_TYPES}}}Default", {"Extension":"rels","ContentType":"application/vnd.openxmlformats-package.relationships+xml"})
    ET.SubElement(content_types, f"{{{XLSX_CONTENT_TYPES}}}Default", {"Extension":"xml","ContentType":"application/xml"})
    ET.SubElement(content_types, f"{{{XLSX_CONTENT_TYPES}}}Override", {"PartName":"/xl/workbook.xml","ContentType":"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"})
    rels_root = ET.Element(f"{{{XLSX_PACKAGE_REL}}}Relationships")
    ET.SubElement(rels_root, f"{{{XLSX_PACKAGE_REL}}}Relationship", {
        "Id":"rId1","Type":"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument","Target":"xl/workbook.xml"
    })
    workbook = ET.Element(f"{{{XLSX_MAIN}}}workbook")
    sheet_nodes = ET.SubElement(workbook, f"{{{XLSX_MAIN}}}sheets")
    workbook_rels = ET.Element(f"{{{XLSX_PACKAGE_REL}}}Relationships")
    prepared=[]
    for idx, (name, rows) in enumerate(sheets, 1):
        safe_name = str(name or f"Sheet{idx}")[:31]
        ET.SubElement(sheet_nodes, f"{{{XLSX_MAIN}}}sheet", {
            "name":safe_name,"sheetId":str(idx),f"{{{XLSX_OFFICE_REL}}}id":f"rId{idx}"
        })
        ET.SubElement(workbook_rels, f"{{{XLSX_PACKAGE_REL}}}Relationship", {
            "Id":f"rId{idx}","Type":"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet","Target":f"worksheets/sheet{idx}.xml"
        })
        ET.SubElement(content_types, f"{{{XLSX_CONTENT_TYPES}}}Override", {
            "PartName":f"/xl/worksheets/sheet{idx}.xml","ContentType":"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
        })
        prepared.append((idx, rows))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", ET.tostring(content_types, encoding="utf-8", xml_declaration=True))
        archive.writestr("_rels/.rels", ET.tostring(rels_root, encoding="utf-8", xml_declaration=True))
        archive.writestr("xl/workbook.xml", ET.tostring(workbook, encoding="utf-8", xml_declaration=True))
        archive.writestr("xl/_rels/workbook.xml.rels", ET.tostring(workbook_rels, encoding="utf-8", xml_declaration=True))
        for idx, rows in prepared:
            archive.writestr(f"xl/worksheets/sheet{idx}.xml", _xlsx_sheet_xml(rows))
    return out.getvalue()

def parse_xlsx_workbook(payload):
    """Read common Excel XLSX files (shared strings, inline strings and numeric cells)."""
    if not payload or len(payload) > 10*1024*1024:
        raise ValueError("فایل اکسل خالی است یا از سقف ۱۰ مگابایت بیشتر است.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError("فایل انتخاب‌شده یک فایل XLSX معتبر نیست.") from exc
    with archive:
        infos=archive.infolist()
        if len(infos)>512:
            raise ValueError("فایل اکسل بیش از حد فایل داخلی دارد.")
        total_uncompressed=sum(int(item.file_size or 0) for item in infos)
        if total_uncompressed>40*1024*1024:
            raise ValueError("حجم بازشدهٔ محتوای اکسل از سقف ۴۰ مگابایت بیشتر است.")
        for item in infos:
            expanded=int(item.file_size or 0)
            compressed=int(item.compress_size or 0)
            if expanded>16*1024*1024:
                raise ValueError("یکی از بخش‌های اکسل از سقف ۱۶ مگابایت بیشتر است.")
            if expanded>1*1024*1024 and (compressed==0 or expanded/max(1,compressed)>500):
                raise ValueError("نسبت فشرده‌سازی فایل اکسل غیرعادی است.")
            if item.flag_bits & 0x1:
                raise ValueError("فایل اکسل رمزگذاری‌شده پشتیبانی نمی‌شود.")
        names = set(archive.namelist())
        if "xl/workbook.xml" not in names:
            raise ValueError("ساختار فایل XLSX شناسایی نشد.")
        shared=[]
        if "xl/sharedStrings.xml" in names:
            shared_root=ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared=["".join(t.text or "" for t in item.iter(f"{{{XLSX_MAIN}}}t")) for item in shared_root.findall(f"{{{XLSX_MAIN}}}si")]
        book=ET.fromstring(archive.read("xl/workbook.xml"))
        rel_root=ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets={rel.attrib.get("Id"):rel.attrib.get("Target","") for rel in rel_root.findall(f"{{{XLSX_PACKAGE_REL}}}Relationship")}
        result={}
        sheet_nodes=book.find(f"{{{XLSX_MAIN}}}sheets")
        if sheet_nodes is None:
            raise ValueError("هیچ برگه‌ای در فایل اکسل وجود ندارد.")
        for sheet in sheet_nodes:
            name=sheet.attrib.get("name","")
            rid=sheet.attrib.get(f"{{{XLSX_OFFICE_REL}}}id","")
            target=targets.get(rid,"")
            if not target:
                continue
            target=target.lstrip("/")
            if not target.startswith("xl/"):
                target="xl/"+target
            target=re.sub(r"/\./","/",target)
            if target not in names:
                continue
            root=ET.fromstring(archive.read(target))
            rows=[]
            for row_node in root.iter(f"{{{XLSX_MAIN}}}row"):
                cells={}
                highest=-1
                for cell in row_node.findall(f"{{{XLSX_MAIN}}}c"):
                    ref=cell.attrib.get("r","A1")
                    col_letters=re.match(r"[A-Z]+",ref.upper())
                    col_idx=0
                    if col_letters:
                        for ch in col_letters.group(0):
                            col_idx=col_idx*26+(ord(ch)-64)
                        col_idx-=1
                    cell_type=cell.attrib.get("t","")
                    val_node=cell.find(f"{{{XLSX_MAIN}}}v")
                    if cell_type=="inlineStr":
                        value="".join(t.text or "" for t in cell.iter(f"{{{XLSX_MAIN}}}t"))
                    elif val_node is None:
                        value=""
                    else:
                        value=val_node.text or ""
                        if cell_type=="s":
                            try: value=shared[int(value)]
                            except (ValueError,IndexError): value=""
                    cells[col_idx]=value
                    highest=max(highest,col_idx)
                values=[""]*(highest+1)
                for idx,value in cells.items():
                    values[idx]=value
                rows.append(values)
            result[name]=rows
        return result

def table(headers, rows, total=None):
    shown = len(rows)
    if total is None:
        count_html = f'<div class="table-count" role="status">تعداد ردیف‌های نمایش‌داده‌شده: {shown:,}</div>'
    else:
        count_html = f'<div class="table-count" role="status">نمایش {shown:,} رکورد از مجموع {int(total):,} رکورد</div>'
    if not rows:
        return count_html + '<div class="empty">هنوز اطلاعاتی برای نمایش وجود ندارد.</div>'
    return count_html + '<div class="tablewrap"><table><thead><tr>'+''.join(f'<th>{h}</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{v}</td>' for v in row)+'</tr>' for row in rows)+'</tbody></div>'

def page_window(page_num=1, per_page=50):
    try: page_num=max(1,int(page_num))
    except (TypeError,ValueError): page_num=1
    per_page=max(1,min(100,int(per_page)))
    return per_page,(page_num-1)*per_page,page_num

def page_nav(path, query, page_num, total, per_page=50, extra_params=None, query_key="q", page_key="page"):
    pages=max(1,(int(total)+per_page-1)//per_page)
    if pages<=1:return ''
    from urllib.parse import quote
    base=[]
    for key,value in (extra_params or {}).items():
        if value is not None:
            base.append(f'{quote(str(key),safe="")}={quote(str(value),safe="")}')
    if query_key is not None:
        base.append(f'{quote(str(query_key),safe="")}={quote(str(query or ""),safe="")}')
    def href(target_page):
        params=base+[f'{quote(str(page_key),safe="")}={int(target_page)}']
        return f'/{path}?'+'&amp;'.join(params)
    links=[]
    if page_num>1: links.append(f'<a class="btn secondary sm" href="{href(page_num-1)}">صفحه قبلی</a>')
    links.append(f'<span class="small">صفحه {page_num} از {pages}</span>')
    if page_num<pages: links.append(f'<a class="btn secondary sm" href="{href(page_num+1)}">صفحه بعدی</a>')
    return '<nav class="pagination" aria-label="صفحه‌بندی">'+' '.join(links)+'</nav>'
def options_products(c): return [(r['id'],f"{r['name']} (موجودی: {r['stock']:g} {r['unit']})") for r in c.execute('SELECT * FROM products ORDER BY name')]
def options_loans(c): return [(r['id'],r['title']) for r in c.execute('SELECT * FROM loans ORDER BY title')]
def dash(c):
    now=datetime.date.today(); week=(now-datetime.timedelta(days=now.weekday())).isoformat(); month=jalali_month_start_iso(); year=jalali_year_start_iso()
    d=calc(c,now.isoformat(),now.isoformat()); m=calc(c,month,now.isoformat()); y=calc(c,year,now.isoformat())
    stock_value=scalar(c,'SELECT SUM(stock*avg_cost) FROM products'); market_value=scalar(c,'SELECT SUM(stock*market_price) FROM products'); stock_delta=market_value-stock_value
    cash_in=scalar(c,'SELECT COALESCE(SUM(received),0) FROM sales')+scalar(c,'SELECT COALESCE(SUM(received),0) FROM services')
    cash_out=scalar(c,'SELECT COALESCE(SUM(paid),0) FROM purchases')+scalar(c,'SELECT COALESCE(SUM(amount),0) FROM expenses')+scalar(c,'SELECT COALESCE(SUM(amount),0) FROM loan_payments')
    sales_chart=dashboard_sales_chart(c,6)
    low=c.execute('SELECT name,stock,min_stock,unit FROM products WHERE stock<=min_stock ORDER BY name').fetchall()
    due=c.execute("SELECT title,installment,next_date FROM loans WHERE remaining>0 ORDER BY next_date LIMIT 5").fetchall()
    def metric(label,val,note='',cls=''):
        return f'<div class="card metric"><div class="label">{label}</div><div class="value {cls}">{money(val)} تومان</div><div class="muted">{note}</div></div>'
    body=f'''<h1>داشبورد مدیریتی</h1><div class="small">تاریخ شمسی: {show_date(now.isoformat())} · مبالغ به تومان هستند. اعداد فقط بر اساس تراکنش‌های ثبت‌شده محاسبه می‌شوند.</div>
    <div class="grid section">{metric('سود خالص امروز',d['net'],'فروش و خدمات منهای هزینه‌ها و سود وام','positive' if d['net']>=0 else 'negative')}{metric('سود خالص این ماه',m['net'],'از ابتدای ماه تا امروز','positive' if m['net']>=0 else 'negative')}{metric('سود خالص امسال',y['net'],'از ابتدای سال شمسی تا امروز','positive' if y['net']>=0 else 'negative')}{metric('ارزش موجودی به بهای خرید',stock_value,'برآورد بر اساس میانگین بهای ثبت‌شده')}</div>
    <div class="grid section">{metric('ارزش موجودی به قیمت روز',market_value,'با آخرین قیمت روز واردشده')}{metric('تغییر ارزش برآوردی انبار',stock_delta,'جدا از سود نقدی فروش','positive' if stock_delta>=0 else 'negative')}{metric('کل اقساط پرداخت‌شده',scalar(c,'SELECT COALESCE(SUM(amount),0) FROM loan_payments'),'اصل و سود؛ خروج وجه نقد')}{metric('مانده اصل وام‌ها',scalar(c,'SELECT COALESCE(SUM(remaining),0) FROM loans'),'مانده ثبت‌شده وام‌ها')}</div>
    <div class="twocol section"><div class="card"><h2>هشدار موجودی کم</h2>{table(['کالا','موجودی','حداقل'],[[esc(r['name']),f"{r['stock']:g} {esc(r['unit'])}",f"{r['min_stock']:g}"] for r in low])}</div><div class="card"><h2>وام‌ها و اقساط آینده</h2>{table(['وام','قسط','سررسید بعدی'],[[esc(r['title']),money(r['installment'])+' تومان',esc(show_date(r['next_date']) if r['next_date'] else 'ثبت نشده')] for r in due])}</div></div>
    {sales_chart}
    <div class="notice section"><b>تفسیر درست:</b> سود خالص با تغییر ارزش انبار یکی نیست. خرید کالا به‌خودی‌خود هزینه کامل سودوزیان محسوب نمی‌شود؛ بهای کالا هنگام فروش در سود معامله منظور می‌شود. پرداخت اصل وام نیز هزینه سودوزیان نیست، اما از نقدینگی کم می‌کند. این نسخه «بودجه خرج امن» را به‌صورت قطعی تعیین نمی‌کند مگر اینکه موجودی نقد آغاز دوره، مطالبات، بدهی‌های سررسیدشده و ذخیره خرید مجدد را هم دقیق ثبت کنی.</div>'''
    return page('داشبورد',body,'')

def products(c, search='', page_num=1):
    limit,offset,page_num=page_window(page_num,50)
    query=str(search or '').strip()
    pattern='%'+query+'%'
    total=scalar(c,"SELECT COUNT(*) FROM products WHERE name LIKE ? OR code LIKE ? OR category LIKE ?",(pattern,pattern,pattern))
    rows=[]
    for r in c.execute('SELECT * FROM products WHERE name LIKE ? OR code LIKE ? OR category LIKE ? ORDER BY name LIMIT ? OFFSET ?',(pattern,pattern,pattern,limit,offset)):
        status='<span class="pill badge danger">موجودی کم</span>' if r['stock']<=r['min_stock'] else '<span class="pill">عادی</span>'
        edit=f'<a class="btn secondary" href="/edit_product?id={r["id"]}">ویرایش</a> <a class="btn secondary" href="/product_ledger?id={r["id"]}">کارت گردش</a>'
        rows.append([esc(r['name']),esc(r['category']),esc(r['code']),f"{r['stock']:g} {esc(r['unit'])}",money(r['avg_cost']),money(r['market_price']),money(r['stock']*r['avg_cost']),status,edit])
    units=[('کیلوگرم','کیلوگرم'),('تن','تن'),('شاخه','شاخه'),('متر','متر'),('مترمربع','مترمربع'),('عدد','عدد'),('ورق','ورق')]
    cats=[('رابیتس','رابیتس'),('طلق','طلق'),('سیم مفتول','سیم مفتول'),('پروفیل','پروفیل'),('ورق','ورق'),('سایر','سایر')]
    body=f'''<h1>کالاها و موجودی انبار</h1>
    <div class="grid section"><div class="card metric"><div class="label">تعداد انواع کالا</div><div class="value">{scalar(c,'SELECT COUNT(*) FROM products')}</div></div><div class="card metric"><div class="label">ارزش موجودی به بهای خرید</div><div class="value">{money(scalar(c,'SELECT COALESCE(SUM(stock*avg_cost),0) FROM products'))}</div><div class="muted">تومان</div></div><div class="card metric"><div class="label">کالاهای کم‌موجودی</div><div class="value">{scalar(c,'SELECT COUNT(*) FROM products WHERE stock<=min_stock')}</div></div></div>
    <div class="card section"><h2>ثبت کالای جدید</h2><form method="post" action="/add_product"><div class="formgrid">
    {field('نام کالا','name',required=True)}{field('کد کالا','code')}{selectfield('دسته‌بندی','category',cats)}
    {selectfield('واحد پایه موجودی','unit',units)}{field('واحد خرید (بسته/برگ/رول)','purchase_unit',value='عدد')}
    {field('ضریب خرید به واحد پایه','purchase_factor','number','1',True,'0.001')}{field('واحد فروش','sale_unit',value='عدد')}
    {field('ضریب فروش به واحد پایه','sale_factor','number','1',True,'0.001')}{field('وزن هر رول (کیلوگرم)','roll_weight','number','0',False,'0.001')}
    {field('مساحت هر برگ (مترمربع)','sheet_area','number','0',False,'0.001')}{field('موجودی اولیه به واحد پایه','stock','number','0',True,'0.001')}
    {field('بهای خرید متوسط هر واحد پایه (تومان)','avg_cost','number','0',True,'0.01')}{field('قیمت روز هر واحد پایه (تومان)','market_price','number','0',True,'0.01')}
    {field('حداقل موجودی هشدار','min_stock','number','0',False,'0.001')}{field('یادداشت','notes')}
    </div><p class="small">نمونه: رابیتس بسته ۱۰ عددی = ضریب ۱۰؛ طلق برگ ۶×۲٫۱۰ متر = ضریب ۱۲٫۶؛ سیم مفتول رول = ضریب برابر وزن رول.</p><div class="actions"><button>ثبت کالا</button></div></form></div>
    <div class="card section"><h2>فهرست کالاها</h2>
      <div class="actions"><a class="btn" href="/export.xlsx">دانلود اکسل کالاها و اشخاص</a></div>
      <form method="post" action="/import.xlsx" enctype="multipart/form-data" class="search-form"><input type="hidden" name="sheet" value="Products"><label for="products-import-file">ورود کالاها از اکسل (.xlsx)</label><div class="formgrid"><input id="products-import-file" type="file" name="file" accept=".xlsx" required><button>ورود کالاها</button></div><p class="small">کالاهای هم‌نام اضافه نمی‌شوند؛ برای جلوگیری از بازنویسی تصادفی موجودی، ردیف‌های تکراری رد خواهند شد.</p></form>
      <form method="get" action="/products" class="search-form"><label for="product-q">جستجوی کالا</label><div class="formgrid"><input id="product-q" type="search" name="q" value="{esc(query)}" placeholder="نام، کد یا دسته‌بندی"><input type="hidden" name="page" value="1"><button>جستجو</button></div></form>
      {table(['کالا','دسته‌بندی','کد','موجودی','بهای پایه','قیمت روز پایه','ارزش موجودی','وضعیت','عملیات'],rows,total)}
      {page_nav('products',query,page_num,total,limit)}</div>'''
    return page('کالاها',body,'products')

def product_editor(c, pid):
    p=c.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone()
    if not p: return page('کالا پیدا نشد','<div class="notice">این کالا وجود ندارد.</div>','products')
    units=[('کیلوگرم','کیلوگرم'),('تن','تن'),('شاخه','شاخه'),('متر','متر'),('مترمربع','مترمربع'),('عدد','عدد'),('ورق','ورق')]
    cats=[('رابیتس','رابیتس'),('طلق','طلق'),('سیم مفتول','سیم مفتول'),('پروفیل','پروفیل'),('ورق','ورق'),('سایر','سایر')]
    def inp(label,name,value,typ='text',step=None):
        return field(label,name,typ,str(value if value is not None else ''),name in ('name','unit','purchase_unit','purchase_factor','sale_unit','sale_factor'),step)
    def sel(label,name,opts,value):
        out=''.join(f'<option value="{esc(v)}" {"selected" if str(v)==str(value) else ""}>{esc(t)}</option>' for v,t in opts)
        return f'<div class="field"><label>{label}</label><select name="{name}" required>{out}</select></div>'
    body=f'''<h1>ویرایش کالا: {esc(p['name'])}</h1><div class="card section"><div class="notice">واحد پایه کالای دارای سابقه خرید یا فروش را بدون تبدیل کنترل‌شده تغییر ندهید. موجودی و مبالغ این فرم در واحد پایه ثبت می‌شوند.</div><form method="post" action="/update_product"><input type="hidden" name="product_id" value="{pid}"><div class="formgrid">
    {inp('نام کالا','name',p['name'])}{inp('کد کالا','code',p['code'])}{sel('دسته‌بندی','category',cats,p['category'])}{sel('واحد پایه موجودی','unit',units,p['unit'])}
    {inp('واحد خرید','purchase_unit',p['purchase_unit'])}{inp('ضریب خرید به واحد پایه','purchase_factor',p['purchase_factor'],'number','0.001')}
    {inp('واحد فروش','sale_unit',p['sale_unit'])}{inp('ضریب فروش به واحد پایه','sale_factor',p['sale_factor'],'number','0.001')}
    {inp('وزن هر رول (کیلوگرم)','roll_weight',p['roll_weight'],'number','0.001')}{inp('مساحت هر برگ (مترمربع)','sheet_area',p['sheet_area'],'number','0.001')}
    {inp('موجودی فعلی به واحد پایه','stock',p['stock'],'number','0.001')}{inp('میانگین بهای خرید هر واحد پایه','avg_cost',p['avg_cost'],'number','0.01')}
    {inp('قیمت روز هر واحد پایه','market_price',p['market_price'],'number','0.01')}{inp('حداقل موجودی هشدار','min_stock',p['min_stock'],'number','0.001')}{inp('یادداشت','notes',p['notes'])}
    </div><div class="actions"><button>ذخیره تغییرات</button><a class="btn secondary" href="/products">بازگشت</a></div></form></div>'''
    return page('ویرایش کالا',body,'products')
def record_actions(record_id, edit_path, delete_path, label):
    confirm = esc(f"حذف {label}؟ اگر این سند روی موجودی یا صندوق اثر دارد، اثر آن نیز برمی‌گردد.")
    return (f'<div class="row-actions"><a class="btn secondary sm" href="/{edit_path}?id={int(record_id)}">ویرایش</a>'
            f'<form method="post" action="/{delete_path}" data-confirm-submit="1" data-confirm-message="{confirm}">'
            f'<input type="hidden" name="record_id" value="{int(record_id)}"><button class="danger sm" type="submit">حذف</button></form></div>')

def purchase_editor(c, record_id):
    r = c.execute("SELECT p.*,pr.name,pr.unit,pr.purchase_unit,pr.purchase_factor FROM purchases p JOIN products pr ON pr.id=p.product_id WHERE p.id=?",(record_id,)).fetchone()
    if r is None:
        return page("خرید پیدا نشد",'<div class="notice">سند خرید وجود ندارد.</div>',"purchases")
    body = f'''<h1>ویرایش خرید: {esc(r["name"])}</h1><div class="card section">
    <div class="notice">برای جلوگیری از بازنویسی گردش‌های بعدی، ویرایش فقط زمانی مجاز است که سند خرید آخرین گردش موجودی آن کالا باشد و گردش دیگری در همان تاریخ ثبت نشده باشد.</div>
    <p class="small">تاریخ و کالا ثابت نگه داشته می‌شوند. واحد خرید: {esc(r["purchase_unit"])}؛ واحد پایه: {esc(r["unit"])}.</p>
    <form method="post" action="/update_purchase"><input type="hidden" name="record_id" value="{r["id"]}">
    <div class="formgrid">{field("مقدار خرید","qty","number",str(r["qty"]),True,"0.001")}
    {field("قیمت خرید هر واحد خرید","unit_cost","number",str(r["unit_cost"]),True,"0.01")}
    {field("هزینه جانبی کل","extra_cost","number",str(r["extra_cost"]),False,"0.01")}
    {field("مبلغ پرداخت‌شده","paid","number",str(r["paid"]),True,"0.01")}
    {field("فروشنده","supplier",value=str(r["supplier"] or ""))}
    {field("یادداشت","notes",value=str(r["notes"] or ""))}</div>
    <div class="actions"><button>ذخیره اصلاح خرید</button><a class="btn secondary" href="/purchases">انصراف</a></div></form></div>'''
    return page("ویرایش خرید",body,"purchases")

def sale_editor(c, record_id):
    r = c.execute("SELECT s.*,p.name,p.unit FROM sales s JOIN products p ON p.id=s.product_id WHERE s.id=?",(record_id,)).fetchone()
    if r is None:
        return page("فروش پیدا نشد",'<div class="notice">سند فروش وجود ندارد.</div>',"sales")
    body = f'''<h1>ویرایش فروش: {esc(r["name"])}</h1><div class="card section">
    <div class="notice">مقدار و قیمت در واحد پایهٔ کالا ثبت شده‌اند. ویرایش فقط وقتی مجاز است که بعد از این تاریخ، خرید یا تعدیل موجودی برای این کالا ثبت نشده باشد.</div>
    <form method="post" action="/update_sale"><input type="hidden" name="record_id" value="{r["id"]}">
    <div class="formgrid">{field("مقدار فروش در واحد پایه","qty","number",str(r["qty"]),True,"0.001")}
    {field("قیمت فروش هر واحد پایه","unit_price","number",str(r["unit_price"]),True,"0.01")}
    {field("هزینه مستقیم فروش","extra_cost","number",str(r["extra_cost"]),False,"0.01")}
    {field("وجه دریافت‌شده","received","number",str(r["received"]),True,"0.01")}
    {field("مشتری","customer",value=str(r["customer"] or ""))}
    {field("یادداشت","notes",value=str(r["notes"] or ""))}</div>
    <div class="actions"><button>ذخیره اصلاح فروش</button><a class="btn secondary" href="/sales">انصراف</a></div></form></div>'''
    return page("ویرایش فروش",body,"sales")

def expense_editor(c, record_id):
    r = c.execute("SELECT * FROM expenses WHERE id=?",(record_id,)).fetchone()
    if r is None:
        return page("هزینه پیدا نشد",'<div class="notice">سند هزینه وجود ندارد.</div>',"expenses")
    body = f'''<h1>ویرایش هزینه/برداشت</h1><div class="card section"><form method="post" action="/update_expense">
    <input type="hidden" name="record_id" value="{r["id"]}"><div class="formgrid">
    {field("تاریخ","date","date",show_date(r["date"]),True)}
    {field("شرح/دسته هزینه","category",value=str(r["category"] or ""),required=True)}
    {field("مبلغ (تومان)","amount","number",str(r["amount"]),True,"0.01")}
    {selectfield("نوع","business",[("1","هزینه کسب‌وکار"),("0","برداشت شخصی/خانوادگی")],value=str(r["business"]))}
    {field("منبع پرداخت","source",value=str(r["source"] or ""))}
    {field("توضیحات","notes",value=str(r["notes"] or ""))}</div>
    <div class="actions"><button>ذخیره اصلاح هزینه</button><a class="btn secondary" href="/expenses">انصراف</a></div></form></div>'''
    return page("ویرایش هزینه",body,"expenses")

def assert_purchase_reversible(c, row):
    pid, date, rid = row["product_id"], row["date"], row["id"]
    if scalar(c,"SELECT COUNT(*) FROM purchase_returns WHERE purchase_id=?",(rid,)):
        raise ValueError("این خرید دارای سند مرجوعی است؛ برای حفظ ارتباط حسابداری ابتدا مرجوعی را مستقل اصلاح کن.")
    later = (
        scalar(c,"SELECT COUNT(*) FROM purchases WHERE product_id=? AND date>=? AND id<>?",(pid,date,rid)) +
        scalar(c,"SELECT COUNT(*) FROM sales WHERE product_id=? AND date>=?",(pid,date)) +
        scalar(c,"SELECT COUNT(*) FROM inventory_adjustments WHERE product_id=? AND date>=?",(pid,date))
    )
    if later:
        raise ValueError("این خرید گردش دیگری در همان تاریخ یا پس از آن دارد؛ ابتدا سندهای وابسته را اصلاح کن.")

def assert_sale_reversible(c, row):
    pid, date = row["product_id"], row["date"]
    if scalar(c,"SELECT COUNT(*) FROM sales_returns WHERE sale_id=?",(row["id"],)):
        raise ValueError("این فروش دارای سند مرجوعی است؛ برای حفظ ریزحساب و موجودی فروش اصلی را ویرایش یا حذف نکن.")
    later = (
        scalar(c,"SELECT COUNT(*) FROM purchases WHERE product_id=? AND date>=?",(pid,date)) +
        scalar(c,"SELECT COUNT(*) FROM inventory_adjustments WHERE product_id=? AND date>=?",(pid,date))
    )
    if later:
        raise ValueError("پس از این فروش خرید یا تعدیل موجودی ثبت شده؛ برای حفظ میانگین موزون، اصلاح/حذف خودکار ایمن نیست.")

def submission_token(c, action):
    """Issue a one-use token for a state-changing finance form."""
    c.execute("DELETE FROM form_submission_tokens WHERE created_at < datetime('now','-30 days')")
    token=secrets.token_urlsafe(32)
    c.execute("INSERT INTO form_submission_tokens(token,action) VALUES(?,?)",(token,action))
    return f'<input type="hidden" name="_submission_token" value="{token}">'

def purchases(c, search='', page_num=1):
    limit,offset,page_num=page_window(page_num,50)
    query=str(search or '').strip(); pattern='%'+query+'%'
    total=scalar(c,"SELECT COUNT(*) FROM purchases p JOIN products pr ON pr.id=p.product_id WHERE pr.name LIKE ? OR p.supplier LIKE ? OR p.notes LIKE ?",(pattern,pattern,pattern))
    prods=options_products(c); opt=[(v,t) for v,t in prods]
    body=f'''<h1>ثبت خرید</h1><div class="card section"><form method="post" action="/add_purchase">{submission_token(c,'add_purchase')}<div class="formgrid">{field('تاریخ خرید','date','date',TODAY,True)}{selectfield('کالا','product_id',opt)}{field('مقدار خرید','qty','number','1',True,'0.001')}{field('قیمت خرید هر واحد (تومان)','unit_cost','number','0',True,'0.01')}{field('هزینه جانبی کل (حمل/تخلیه)','extra_cost','number','0',False,'0.01')}{field('مبلغ پرداخت‌شده','paid','number','0',True,'0.01')}{field('فروشنده','supplier')}{field('یادداشت','notes')}</div><div class="actions"><button>ثبت خرید و افزایش موجودی</button></div></form><p class="small">پس از ثبت خرید، موجودی و میانگین موزون بهای خرید به‌روزرسانی می‌شود. هزینه جانبی به بهای تمام‌شده خرید اضافه می‌شود.</p></div>'''
    rows=[[show_date(r['date']),esc(r['name']),f"{r['qty']:g}",money(r['unit_cost']),money(r['extra_cost']),money(r['qty']*r['unit_cost']+r['extra_cost']),esc(r['supplier']),money(r['paid']),record_actions(r['id'],'edit_purchase','delete_purchase','خرید')] for r in c.execute('SELECT p.*,pr.name FROM purchases p JOIN products pr ON pr.id=p.product_id WHERE pr.name LIKE ? OR p.supplier LIKE ? OR p.notes LIKE ? ORDER BY p.date DESC,p.id DESC LIMIT ? OFFSET ?',(pattern,pattern,pattern,limit,offset))]
    body+=f'<div class="card section"><h2>خریدها</h2><form method="get" action="/purchases" class="search-form"><label>جستجوی خرید</label><div class="formgrid"><input type="search" name="q" value="{esc(query)}" placeholder="کالا، فروشنده یا یادداشت"><input type="hidden" name="page" value="1"><button>جستجو</button></div></form>{table(["تاریخ","کالا","مقدار","قیمت واحد","هزینه جانبی","جمع بهای خرید","فروشنده","پرداخت‌شده","عملیات"],rows,total)}{page_nav("purchases",query,page_num,total,limit)}</div>'
    return page('خرید',body,'purchases')
def sales(c, search='', page_num=1):
    limit,offset,page_num=page_window(page_num,50)
    query=str(search or '').strip(); pattern='%'+query+'%'
    total=scalar(c,"SELECT COUNT(*) FROM sales s JOIN products p ON p.id=s.product_id WHERE p.name LIKE ? OR s.customer LIKE ? OR s.notes LIKE ?",(pattern,pattern,pattern))
    body=f'''<h1>ثبت فروش کالا</h1><div class="card section"><form method="post" action="/add_sale">{submission_token(c,'add_sale')}<div class="formgrid">{field('تاریخ فروش','date','date',TODAY,True)}{selectfield('کالا','product_id',options_products(c))}{field('مقدار فروش','qty','number','1',True,'0.001')}{field('قیمت فروش هر واحد (تومان)','unit_price','number','0',True,'0.01')}{field('هزینه مستقیم فروش','extra_cost','number','0',False,'0.01')}{field('وجه دریافت‌شده','received','number','0',True,'0.01')}{field('مشتری','customer')}{field('یادداشت','notes')}</div><div class="actions"><button>ثبت فروش و کسر موجودی</button></div></form><p class="small">بهای تمام‌شده از میانگین بهای خرید ثبت‌شده در همان لحظه ذخیره می‌شود تا گزارش سود فروش تاریخی با خریدهای بعدی تغییر نکند.</p></div>'''
    rows=[[show_date(r['date']),esc(r['name']),f"{r['qty']:g}",money(r['unit_price']),money(r['cost_basis']),money(r['qty']*(r['unit_price']-r['cost_basis'])-r['extra_cost']),esc(r['customer']),money(r['received']),record_actions(r['id'],'edit_sale','delete_sale','فروش')] for r in c.execute('SELECT s.*,p.name FROM sales s JOIN products p ON p.id=s.product_id WHERE p.name LIKE ? OR s.customer LIKE ? OR s.notes LIKE ? ORDER BY s.date DESC,s.id DESC LIMIT ? OFFSET ?',(pattern,pattern,pattern,limit,offset))]
    body+=f'<div class="card section"><h2>فروش‌ها</h2><form method="get" action="/sales" class="search-form"><label>جستجوی فروش</label><div class="formgrid"><input type="search" name="q" value="{esc(query)}" placeholder="کالا، مشتری یا یادداشت"><input type="hidden" name="page" value="1"><button>جستجو</button></div></form>{table(["تاریخ","کالا","مقدار","قیمت فروش","بهای تمام‌شده","سود معامله پس از هزینه مستقیم","مشتری","دریافت‌شده","عملیات"],rows,total)}{page_nav("sales",query,page_num,total,limit)}</div>'
    return page('فروش',body,'sales')
def services(c, search='', page_num=1):
    limit,offset,page_num=page_window(page_num,50)
    query=str(search or '').strip(); pattern='%'+query+'%'
    total=scalar(c,"SELECT COUNT(*) FROM services WHERE title LIKE ? OR customer LIKE ? OR notes LIKE ?",(pattern,pattern,pattern))
    body=f'''<h1>درآمد خدماتی</h1><div class="card section"><form method="post" action="/add_service"><div class="formgrid">{field('تاریخ','date','date',TODAY,True)}{field('شرح خدمت','title',required=True)}{field('درآمد خدمت (تومان)','revenue','number','0',True,'0.01')}{field('هزینه اجرای خدمت','cost','number','0',True,'0.01')}{field('وجه دریافت‌شده','received','number','0',True,'0.01')}{field('مشتری','customer')}{field('یادداشت','notes')}</div><div class="actions"><button>ثبت خدمت</button></div></form></div>'''
    rows=[[show_date(r['date']),esc(r['title']),money(r['revenue']),money(r['cost']),money(r['revenue']-r['cost']),money(r['received']),esc(r['customer'])] for r in c.execute('SELECT * FROM services WHERE title LIKE ? OR customer LIKE ? OR notes LIKE ? ORDER BY date DESC,id DESC LIMIT ? OFFSET ?',(pattern,pattern,pattern,limit,offset))]
    body+=f'<div class="card section"><h2>خدمات ثبت‌شده</h2><form method="get" action="/services" class="search-form"><label>جستجوی خدمت</label><div class="formgrid"><input type="search" name="q" value="{esc(query)}" placeholder="شرح، مشتری یا یادداشت"><input type="hidden" name="page" value="1"><button>جستجو</button></div></form>{table(["تاریخ","خدمت","درآمد","هزینه اجرا","سود خدمت","دریافتی","مشتری"],rows,total)}{page_nav("services",query,page_num,total,limit)}</div>'
    return page('خدمات',body,'services')
def expenses(c, search='', page_num=1):
    limit,offset,page_num=page_window(page_num,50)
    query=str(search or '').strip(); pattern='%'+query+'%'
    total=scalar(c,"SELECT COUNT(*) FROM expenses WHERE category LIKE ? OR source LIKE ? OR notes LIKE ?",(pattern,pattern,pattern))
    body=f'''<h1>هزینه‌ها و برداشت‌های شخصی</h1><div class="card section"><form method="post" action="/add_expense">{submission_token(c,'add_expense')}<div class="formgrid">{field('تاریخ','date','date',TODAY,True)}{field('شرح/دسته هزینه','category',required=True)}{field('مبلغ (تومان)','amount','number','0',True,'0.01')}{selectfield('نوع','business',[('1','هزینه کسب‌وکار'),('0','برداشت شخصی/خانوادگی')])}{selectfield('منبع پرداخت','source',[('سود/درآمد جاری','سود/درآمد جاری'),('سرمایه/پس‌انداز','سرمایه/پس‌انداز'),('نامشخص','نامشخص')])}{field('توضیحات','notes')}</div><div class="actions"><button>ثبت پرداخت</button></div></form><p class="small">هزینه کسب‌وکار در سودوزیان کسر می‌شود؛ برداشت شخصی سود عملیاتی را کم نمی‌کند، اما از نقدینگی و سرمایه قابل‌استفاده کم می‌کند. منبع پرداخت یک تخصیص مدیریتی است و باید با موجودی نقد تطبیق داده شود.</p></div>'''
    rows=[[show_date(r['date']),esc(r['category']),money(r['amount']), 'هزینه کسب‌وکار' if r['business'] else 'برداشت شخصی',esc(r['source']),esc(r['notes']),record_actions(r['id'],'edit_expense','delete_expense','هزینه')] for r in c.execute('SELECT * FROM expenses WHERE category LIKE ? OR source LIKE ? OR notes LIKE ? ORDER BY date DESC,id DESC LIMIT ? OFFSET ?',(pattern,pattern,pattern,limit,offset))]
    body+=f'<div class="card section"><h2>پرداخت‌ها و برداشت‌ها</h2><form method="get" action="/expenses" class="search-form"><label>جستجوی هزینه</label><div class="formgrid"><input type="search" name="q" value="{esc(query)}" placeholder="شرح، منبع یا یادداشت"><input type="hidden" name="page" value="1"><button>جستجو</button></div></form>{table(["تاریخ","شرح","مبلغ","نوع","منبع","توضیحات","عملیات"],rows,total)}{page_nav("expenses",query,page_num,total,limit)}</div>'
    return page('هزینه‌ها',body,'expenses')
def loans(c, search='', page_num=1):
    body=f'''<h1>وام‌ها و اقساط</h1><div class="twocol section"><div class="card"><h2>ثبت وام</h2><form method="post" action="/add_loan"><div class="formgrid">{field('نام وام','title',required=True)}{field('مبلغ اولیه وام','principal','number','0',True,'0.01')}{field('مانده اصل بدهی','remaining','number','0',True,'0.01')}{field('مبلغ قسط','installment','number','0',True,'0.01')}{field('سررسید بعدی','next_date','date',TODAY)}{field('فاصلهٔ هر سررسید','interval_value','number','1',True,'1')}{selectfield('واحد فاصلهٔ سررسید','interval_unit',[('day','روز'),('week','هفته'),('month','ماه'),('year','سال')])}{field('توضیح نرخ/شرایط','rate_note')}{field('یادداشت','notes')}</div><div class="actions"><button>ثبت وام</button></div></form></div><div class="card"><h2>ثبت پرداخت قسط</h2><form method="post" action="/add_payment"><div class="formgrid">{selectfield('وام','loan_id',options_loans(c))}{field('تاریخ پرداخت','date','date',TODAY,True)}{field('کل مبلغ پرداخت','amount','number','0',True,'0.01')}{field('سهم اصل وام','principal_part','number','0',True,'0.01')}{field('سهم سود/کارمزد','interest_part','number','0',True,'0.01')}{selectfield('منبع پرداخت','source',[('سود/درآمد جاری','سود/درآمد جاری'),('سرمایه/پس‌انداز','سرمایه/پس‌انداز'),('نامشخص','نامشخص')])}{field('یادداشت','notes')}</div><div class="actions"><button>ثبت پرداخت قسط</button></div></form><p class="small">مبلغ قسط باید برابر مجموع سهم اصل و سهم سود/کارمزد باشد. فقط سود/کارمزد هزینه سودوزیان است؛ اصل قسط بدهی را کم می‌کند.</p></div></div>'''
    limit,offset,page_num=page_window(page_num,50)
    query=str(search or '').strip(); pattern='%'+query+'%'
    total_loans=scalar(c,"SELECT COUNT(*) FROM loans WHERE title LIKE ? OR rate_note LIKE ? OR notes LIKE ?",(pattern,pattern,pattern))
    rows=[]
    for r in c.execute("SELECT * FROM loans WHERE title LIKE ? OR rate_note LIKE ? OR notes LIKE ? ORDER BY next_date LIMIT ? OFFSET ?",(pattern,pattern,pattern,limit,offset)):
        interval_label={"day":"روز","week":"هفته","month":"ماه","year":"سال"}.get(r["interval_unit"],r["interval_unit"])
        rows.append([r['title'],money(r['principal']),money(r['remaining']),money(r['installment']),esc(show_date(r['next_date']) if r['next_date'] else ''),f'{r["interval_value"]} {interval_label}',esc(r['rate_note'])])
    body+=f'<div class="card section"><h2>وضعیت وام‌ها</h2><form method="get" action="/loans" class="search-form"><label>جستجوی وام</label><div class="formgrid"><input type="search" name="q" value="{esc(query)}" placeholder="نام وام یا شرایط"><input type="hidden" name="page" value="1"><button>جستجو</button></div></form>{table(["وام","اصل اولیه","مانده اصل","مبلغ قسط","سررسید بعدی","دوره پرداخت","شرایط"],rows,total_loans)}{page_nav("loans",query,page_num,total_loans,limit)}</div>'
    total_payments=scalar(c,"SELECT COUNT(*) FROM loan_payments lp JOIN loans l ON l.id=lp.loan_id WHERE l.title LIKE ? OR lp.source LIKE ? OR lp.notes LIKE ?",(pattern,pattern,pattern))
    payments=[[show_date(r['date']),esc(r['title']),money(r['amount']),money(r['principal_part']),money(r['interest_part']),esc(r['source'])] for r in c.execute("SELECT lp.*,l.title FROM loan_payments lp JOIN loans l ON l.id=lp.loan_id WHERE l.title LIKE ? OR lp.source LIKE ? OR lp.notes LIKE ? ORDER BY lp.date DESC,lp.id DESC LIMIT ? OFFSET ?",(pattern,pattern,pattern,limit,offset))]
    body+=f'<div class="card section"><h2>تاریخچه پرداخت اقساط</h2>{table(["تاریخ","وام","پرداخت کل","اصل","سود/کارمزد","منبع"],payments,total_payments)}{page_nav("loans",query,page_num,total_payments,limit)}</div>'
    return page('وام‌ها',body,'loans')
def prices(c, selected_product_id=0, search='', page_num=1):
    product_options=options_products(c)
    try:
        selected_product_id=int(selected_product_id or 0)
    except (TypeError,ValueError):
        selected_product_id=0
    if selected_product_id and not c.execute("SELECT 1 FROM products WHERE id=?",(selected_product_id,)).fetchone():
        selected_product_id=0
    if not selected_product_id:
        latest=c.execute("SELECT product_id FROM price_history ORDER BY date DESC,id DESC LIMIT 1").fetchone()
        if latest:
            selected_product_id=int(latest["product_id"])
    selected_product=c.execute("SELECT * FROM products WHERE id=?",(selected_product_id,)).fetchone() if selected_product_id else None
    trend_rows=[]
    if selected_product:
        trend_rows=c.execute("""SELECT date,market_price,notes FROM price_history WHERE product_id=?
                                ORDER BY date DESC,id DESC LIMIT 24""",(selected_product_id,)).fetchall()
        trend_rows=list(reversed(trend_rows))
    chart=""
    if trend_rows:
        values=[float(r["market_price"] or 0) for r in trend_rows]
        low=min(values); high=max(values); span=high-low or 1.0
        width=760; left=56; right=738; top=22; bottom=160
        count=len(trend_rows)
        points=[]
        dots=[]
        labels=[]
        for i,r in enumerate(trend_rows):
            x=left+(right-left)*(i/(count-1) if count>1 else 0.5)
            y=bottom-(float(r["market_price"] or 0)-low)/span*(bottom-top)
            points.append(f"{x:.1f},{y:.1f}")
            dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4"><title>{esc(show_date(r["date"]))}: {money(r["market_price"])} تومان</title></circle>')
            label=show_date(r["date"])
            short_label=label[5:] if len(label)>=10 else label
            labels.append(f'<text x="{x:.1f}" y="190" text-anchor="middle">{esc(short_label)}</text>')
        chart=f'''<div class="card section"><h2>روند قیمت: {esc(selected_product["name"])}</h2>
          <p class="small">حداکثر ۲۴ ثبت قیمت اخیر؛ برای مشاهدهٔ مقدار هر نقطه، نشانگر را روی آن قرار بده.</p>
          <div class="price-chart-wrap"><svg class="price-chart" viewBox="0 0 {width} 210" role="img" aria-label="نمودار روند قیمت {esc(selected_product["name"])}">
            <line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" class="chart-axis"/>
            <line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" class="chart-axis"/>
            <text x="8" y="{top+4}">{money(high)}</text><text x="8" y="{bottom}">{money(low)}</text>
            <polyline points="{" ".join(points)}" class="price-line"/>
            {"".join(dots)}{"".join(labels)}
          </svg></div>
        </div>'''
    limit,offset,page_num=page_window(page_num,50)
    query=str(search or '').strip(); pattern='%'+query+'%'
    total_prices=scalar(c,"SELECT COUNT(*) FROM price_history h JOIN products p ON p.id=h.product_id WHERE p.name LIKE ? OR h.notes LIKE ?",(pattern,pattern))
    history_rows=c.execute("SELECT h.*,p.name FROM price_history h JOIN products p ON p.id=h.product_id WHERE p.name LIKE ? OR h.notes LIKE ? ORDER BY h.date DESC,h.id DESC LIMIT ? OFFSET ?",(pattern,pattern,limit,offset)).fetchall()
    body=f'''<h1>قیمت روز بازار</h1>
    <div class="card section"><form method="post" action="/add_price"><div class="formgrid">{field('تاریخ قیمت','date','date',TODAY,True)}{selectfield('کالا','product_id',product_options)}{field('قیمت بازار هر واحد (تومان)','market_price','number','0',True,'0.01')}{field('منبع/یادداشت','notes')}</div><div class="actions"><button>ثبت قیمت روز و به‌روزرسانی کالا</button></div></form>
    <p class="small">ثبت قیمت جدید، قیمت روز فعلی کالا را به‌روزرسانی می‌کند ولی سود تحقق‌یافته معاملات قبلی را تغییر نمی‌دهد.</p></div>
    <div class="card section"><h2>انتخاب کالا برای نمودار قیمت</h2><form method="get" action="/prices"><div class="formgrid">{selectfield('کالا','product_id',product_options,value=selected_product_id)}<button>نمایش روند قیمت</button></div></form></div>
    {chart}
    <div class="card section"><h2>تاریخچه قیمت‌ها</h2><form method="get" action="/prices" class="search-form"><label>جستجوی تاریخچه قیمت</label><div class="formgrid"><input type="search" name="q" value="{esc(query)}" placeholder="نام کالا یا منبع قیمت"><input type="hidden" name="product_id" value="{selected_product_id}"><input type="hidden" name="page" value="1"><button>جستجو</button></div></form>
    {table(["تاریخ","کالا","قیمت روز","یادداشت"],[[show_date(r['date']),esc(r['name']),money(r['market_price']),esc(r['notes'])] for r in history_rows],total_prices)}
    {page_nav("prices",query,page_num,total_prices,limit,extra_params={"product_id":selected_product_id})}</div>'''
    return page('قیمت روز',body,'prices')
def report_detail_sections(c):
    # Product profitability, net of sales returns, sorted by true numeric profit.
    product_metrics=[]
    for r in c.execute("""SELECT p.id,p.name,
        COALESCE(s.rev,0) AS sold_rev, COALESCE(s.cost,0) AS sold_cost, COALESCE(s.extra,0) AS sold_extra,
        COALESCE(sr.rev,0) AS return_rev, COALESCE(sr.cost,0) AS return_cost, COALESCE(sr.extra,0) AS return_extra
        FROM products p
        LEFT JOIN (SELECT product_id,SUM(qty*unit_price) rev,SUM(qty*cost_basis) cost,SUM(extra_cost) extra FROM sales GROUP BY product_id) s ON s.product_id=p.id
        LEFT JOIN (SELECT product_id,SUM(return_value) rev,SUM(qty*cost_basis) cost,SUM(extra_reversed) extra FROM sales_returns GROUP BY product_id) sr ON sr.product_id=p.id
        WHERE COALESCE(s.rev,0)>0 OR COALESCE(sr.rev,0)>0"""):
        revenue=float(r["sold_rev"] or 0)-float(r["return_rev"] or 0)
        cost=float(r["sold_cost"] or 0)-float(r["return_cost"] or 0)
        extra=float(r["sold_extra"] or 0)-float(r["return_extra"] or 0)
        product_metrics.append({"name":r["name"],"revenue":revenue,"cost":cost,"extra":extra,"profit":revenue-cost-extra})
    product_metrics.sort(key=lambda item:item["profit"],reverse=True)
    product_rows=[[esc(r["name"]),money(r["revenue"]),money(r["cost"]),money(r["extra"]),money(r["profit"])] for r in product_metrics]

    # Customer profit includes goods, returned goods, and services.
    customer_stats={}
    def customer_bucket(name):
        name=normalize_person(name) or "(بدون نام)"
        return customer_stats.setdefault(name,{"sales_rev":0.0,"sales_cost":0.0,"sales_extra":0.0,"service_rev":0.0,"service_cost":0.0})
    for r in c.execute("SELECT TRIM(customer) customer,SUM(qty*unit_price) rev,SUM(qty*cost_basis) cost,SUM(extra_cost) extra FROM sales GROUP BY TRIM(customer)"):
        b=customer_bucket(r["customer"])
        b["sales_rev"]+=float(r["rev"] or 0); b["sales_cost"]+=float(r["cost"] or 0); b["sales_extra"]+=float(r["extra"] or 0)
    for r in c.execute("SELECT TRIM(customer) customer,SUM(return_value) rev,SUM(qty*cost_basis) cost,SUM(extra_reversed) extra FROM sales_returns GROUP BY TRIM(customer)"):
        b=customer_bucket(r["customer"])
        b["sales_rev"]-=float(r["rev"] or 0); b["sales_cost"]-=float(r["cost"] or 0); b["sales_extra"]-=float(r["extra"] or 0)
    for r in c.execute("SELECT TRIM(customer) customer,SUM(revenue) rev,SUM(cost) cost FROM services GROUP BY TRIM(customer)"):
        b=customer_bucket(r["customer"])
        b["service_rev"]+=float(r["rev"] or 0); b["service_cost"]+=float(r["cost"] or 0)
    customer_metrics=[]
    for name,b in customer_stats.items():
        sales_profit=b["sales_rev"]-b["sales_cost"]-b["sales_extra"]
        service_profit=b["service_rev"]-b["service_cost"]
        customer_metrics.append({"name":name,"sales_rev":b["sales_rev"],"sales_profit":sales_profit,
                                 "service_rev":b["service_rev"],"service_profit":service_profit,
                                 "profit":sales_profit+service_profit})
    customer_metrics.sort(key=lambda item:item["profit"],reverse=True)
    customer_rows=[[esc(r["name"]),money(r["sales_rev"]),money(r["sales_profit"]),money(r["service_rev"]),money(r["service_profit"]),money(r["profit"])] for r in customer_metrics]

    # Aggregate by Jalali month, converting stored Gregorian ISO dates at the boundary.
    months={}
    def month_bucket(key):
        return months.setdefault(key,{"sales_rev":0.0,"sales_cost":0.0,"sales_extra":0.0,
                                      "service_rev":0.0,"service_cost":0.0,"expenses":0.0,"interest":0.0})
    def add_monthly(sql, key, sign=1):
        for row in c.execute(sql):
            if not row["date"]:
                continue
            try:
                gy,gm,gd=map(int,str(row["date"]).split("-")[:3])
                jy,jm,jd=gregorian_to_jalali(gy,gm,gd)
            except (TypeError,ValueError):
                continue
            month_key=(jy,jm)
            month_bucket(month_key)[key]+=sign*float(row["value"] or 0)
    monthly_queries=[
        ("SELECT date,SUM(qty*unit_price) value FROM sales GROUP BY date","sales_rev",1),
        ("SELECT date,SUM(qty*cost_basis) value FROM sales GROUP BY date","sales_cost",1),
        ("SELECT date,SUM(extra_cost) value FROM sales GROUP BY date","sales_extra",1),
        ("SELECT date,SUM(return_value) value FROM sales_returns GROUP BY date","sales_rev",-1),
        ("SELECT date,SUM(qty*cost_basis) value FROM sales_returns GROUP BY date","sales_cost",-1),
        ("SELECT date,SUM(extra_reversed) value FROM sales_returns GROUP BY date","sales_extra",-1),
        ("SELECT date,SUM(revenue) value FROM services GROUP BY date","service_rev",1),
        ("SELECT date,SUM(cost) value FROM services GROUP BY date","service_cost",1),
        ("SELECT date,SUM(amount) value FROM expenses WHERE business=1 GROUP BY date","expenses",1),
        ("SELECT date,SUM(interest_part) value FROM loan_payments GROUP BY date","interest",1),
    ]
    for sql,key,sign in monthly_queries:
        add_monthly(sql,key,sign)
    monthly_rows=[]
    for (jy,jm),b in sorted(months.items(),reverse=True)[:24]:
        sales_profit=b["sales_rev"]-b["sales_cost"]-b["sales_extra"]
        service_profit=b["service_rev"]-b["service_cost"]
        net=sales_profit+service_profit-b["expenses"]-b["interest"]
        monthly_rows.append([f"{jy:04d}/{jm:02d}",money(b["sales_rev"]),money(sales_profit),money(service_profit),
                             money(b["expenses"]),money(b["interest"]),money(net)])
    return f'''<div class="card section"><h2>سود تفصیلی به تفکیک کالا</h2><p class="small">مرجوعی فروش از فروش، بهای تمام‌شده و هزینه مستقیم کسر شده است.</p>{table(["کالا","فروش خالص","بهای تمام‌شده خالص","هزینه مستقیم خالص","سود فروش کالا"],product_rows,len(product_rows))}</div>
    <div class="card section"><h2>سود به تفکیک مشتری</h2>{table(["مشتری","فروش کالای خالص","سود فروش کالا","درآمد خدمات","سود خدمات","سود کل مشتری"],customer_rows,len(customer_rows))}</div>
    <div class="card section"><h2>سود خالص ماهانه (تقویم شمسی)</h2>{table(["ماه شمسی","فروش کالای خالص","سود فروش کالا","سود خدمات","هزینه کسب‌وکار","سود/کارمزد وام","سود خالص"],monthly_rows,len(monthly_rows))}</div>'''

def reports(c):
    start=html.escape(jalali_month_start_iso()); end=TODAY
    # query date range submitted by GET
    rows=[]
    for label,s,e in [('امروز',TODAY,TODAY),('این هفته',(datetime.date.today()-datetime.timedelta(days=datetime.date.today().weekday())).isoformat(),TODAY),('این ماه',jalali_month_start_iso(),TODAY),('امسال',jalali_year_start_iso(),TODAY)]:
        x=calc(c,s,e); rows.append([label,money(x['sales_rev']),money(x['sales_rev']-x['sales_cost']-x['sales_extra']),money(x['service_rev']-x['service_cost']),money(x['exp']),money(x['interest']),money(x['net'])])
    body=f'''<h1>گزارش سود، زیان و جریان نقدی</h1><div class="card section"><h2>مقایسه دوره‌ها (تاریخ بر اساس تقویم سیستم)</h2>{table(["دوره","فروش کالا","سود فروش کالا پس از هزینه مستقیم","سود خدمات","هزینه کسب‌وکار","سود/کارمزد وام","سود خالص"],rows)}</div>
    <div class="card section"><h2>گزارش بازه دلخواه</h2><form method="get" action="/reports"><div class="formgrid">{field('از تاریخ','start','date',start,True)}{field('تا تاریخ','end','date',end,True)}</div><div class="actions"><button>محاسبه بازه</button><a class="btn secondary" href="/export.csv">خروجی CSV تراکنش‌ها</a></div></form></div>'''
    body += report_detail_sections(c)
    qs=parse_qs(urlparse('').query)
    # handler sets range via special global? handled in do_GET before call
    return page('گزارش‌ها',body,'reports')
def audit_page(c, search='', page_num=1):
    limit,offset,page_num=page_window(page_num,50)
    query=str(search or '').strip(); pattern='%'+query+'%'
    total=scalar(c,"SELECT COUNT(*) FROM audit_log WHERE action LIKE ? OR details LIKE ?",(pattern,pattern))
    rows=[]
    for r in c.execute("SELECT id,created_at,action,details FROM audit_log WHERE action LIKE ? OR details LIKE ? ORDER BY id DESC LIMIT ? OFFSET ?",(pattern,pattern,limit,offset)):
        try:
            details=json.loads(r["details"] or "{}")
        except (TypeError,ValueError):
            details={}
        fields=details.get("fields",[])
        if isinstance(fields,list):
            fields_text="، ".join(str(x) for x in fields)
        else:
            fields_text=str(fields or "")
        record_id=details.get("record_id","")
        actor=details.get("actor","legacy/system")
        label={
            "add_purchase":"ثبت خرید","update_purchase":"اصلاح خرید","delete_purchase":"حذف خرید",
            "add_sale":"ثبت فروش","update_sale":"اصلاح فروش","delete_sale":"حذف فروش",
            "add_expense":"ثبت هزینه","update_expense":"اصلاح هزینه","delete_expense":"حذف هزینه",
            "add_person":"ثبت طرف حساب","add_settlement":"ثبت تسویه",
            "add_sales_return":"مرجوعی فروش","add_purchase_return":"مرجوعی خرید",
            "add_cash_movement":"گردش دستی صندوق","inventory_adjust":"انبارگردانی",
            "restore_backup":"بازیابی پشتیبان","import.xlsx":"ورود اکسل",
            "بازسازی گردش صندوق از اسناد قدیمی":"مهاجرت گردش نقدی",
        }.get(r["action"],r["action"])
        rows.append([esc(r["created_at"] or "زمان ثبت قدیمی در دسترس نیست"),esc(label),
                     esc(actor),esc(record_id or "—"),esc(fields_text or "—")])
    body=f'''<h1>گزارش ممیزی فعالیت‌ها</h1>
    <div class="notice">برای حفظ حریم داده، گزارش ممیزی نام عملیات، زمان ثبت رخداد، شناسهٔ سند و نام فیلدهای ارسالی را ذخیره می‌کند؛ مقدار واقعی فرم‌ها در ممیزی کپی نمی‌شود. داده‌های قدیمی که پیش از فعال‌شدن timestamp ثبت شده‌اند، زمان ایجاد اصلی ندارند.</div>
    <div class="card section"><h2>رخدادهای ممیزی</h2><form method="get" action="/audit" class="search-form"><label>جستجوی رخداد</label><div class="formgrid"><input type="search" name="q" value="{esc(query)}" placeholder="نوع عملیات یا شناسه/جزئیات"><input type="hidden" name="page" value="1"><button>جستجو</button></div></form>{table(["زمان رخداد","عملیات","عامل","شناسه سند","فیلدهای درخواست"],rows,total)}{page_nav("audit",query,page_num,total,limit)}</div>'''
    return page("گزارش ممیزی",body,"audit")

def settings(c):
    capital=c.execute('SELECT * FROM opening_capital WHERE id=1').fetchone()
    body=f'''<h1>تنظیمات و سرمایه اولیه</h1><div class="card section"><h2>ثبت سرمایه و وجه نقد آغاز دوره</h2><form method="post" action="/save_capital"><div class="formgrid">{field('سرمایه/وجه نقد آغاز دوره (تومان)','amount','number',str(capital['amount']),True,'0.01')}{field('تاریخ آغاز دوره','date','date',capital['date'],True)}</div><div class="actions"><button>ذخیره تنظیمات</button></div></form><p class="small">این مقدار برای شروع ثبت سوابق استفاده می‌شود؛ سرمایه اولیه با سود سالانه یکی نیست. برای محاسبه دقیق «چقدر از سرمایه خرج شده»، موجودی نقد، مطالبات، بدهی‌ها و موجودی کالا نیز باید کامل و درست ثبت شوند.</p></div><div class="card section"><h2>پشتیبان‌گیری</h2><p>پشتیبان خودکار پیش از شروع برنامه ساخته می‌شود و ۷ نسخه آخر در پوشه <code>data/backups</code> می‌ماند. برای نگهداری خارج از دستگاه، فایل پشتیبان را نیز جداگانه کپی کن.</p><div class="actions"><a class="btn" href="/backup">دریافت نسخه پشتیبان پایگاه داده</a></div><p class="small">دیتابیس با حالت WAL اجرا می‌شود. هنگام بازیابی، ابتدا از دیتابیس فعلی یک پشتیبان جداگانه ساخته می‌شود.</p>
    <form method="post" action="/restore_backup" enctype="multipart/form-data" data-confirm-submit="1" data-confirm-message="با بازیابی، داده‌های فعلی جایگزین می‌شوند. ادامه می‌دهی؟">
      <div class="formgrid"><label>انتخاب فایل پشتیبان (.db)<input type="file" name="backup_file" accept=".db,application/octet-stream" required></label></div>
      <div class="actions"><button class="danger" type="submit">اعتبارسنجی و بازیابی پشتیبان</button></div>
    </form></div>'''
    return page('تنظیمات',body,'settings')

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def _host_is_loopback(self):
        try:
            from urllib.parse import urlsplit
            host=urlsplit("//"+str(self.headers.get("Host",""))).hostname
            return host is not None and host.lower() in ("127.0.0.1","localhost","::1")
        except (TypeError,ValueError):
            return False
    def _same_origin_url(self,value):
        if not value:
            return True
        try:
            from urllib.parse import urlsplit
            source=urlsplit(str(value))
            host=urlsplit("//"+str(self.headers.get("Host","")))
            if source.scheme.lower()!="http" or source.hostname is None or host.hostname is None:
                return False
            allowed=("127.0.0.1","localhost","::1")
            if source.hostname.lower() not in allowed or host.hostname.lower() not in allowed:
                return False
            source_port=source.port or 80
            host_port=host.port or 80
            return source_port==host_port
        except (TypeError,ValueError):
            return False
    def _request_security_error(self,method):
        if not self._host_is_loopback():
            return "Host header is not a permitted loopback host"
        fetch_site=str(self.headers.get("Sec-Fetch-Site","")).lower().strip()
        if fetch_site=="cross-site":
            return "Cross-site request blocked"
        if method=="POST" and fetch_site=="none":
            return "Untrusted POST navigation blocked"
        if method=="POST":
            origin=self.headers.get("Origin")
            referer=self.headers.get("Referer")
            # Some same-origin browser form POSTs can carry Origin: null
            # under a no-referrer policy. Accept that opaque Origin only when
            # Fetch Metadata independently confirms same-origin; cross-site and
            # unknown-site requests remain rejected.
            if origin and origin.strip().lower()=="null":
                if fetch_site!="same-origin":
                    return "Cross-origin POST blocked"
            elif origin and not self._same_origin_url(origin):
                return "Cross-origin POST blocked"
            if not origin and referer and not self._same_origin_url(referer):
                return "Cross-origin POST blocked"
        elif self.headers.get("Origin") and not self._same_origin_url(self.headers.get("Origin")):
            return "Cross-origin request blocked"
        return ""
    def send(self,content,typ='text/html; charset=utf-8',status=200):
        raw=content if isinstance(content,bytes) else content.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type',typ)
        self.send_header('Content-Length',str(len(raw)))
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Permissions-Policy','camera=(), microphone=(), geolocation=()')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
        if typ.startswith('text/html'):
            self.send_header('Cache-Control','no-store')
        self.end_headers()
        self.wfile.write(raw)
    def redirect(self,path,msg=''):
        from urllib.parse import quote
        self.send_response(303); self.send_header('Location',path+('&' if '?' in path else '?')+'msg='+quote(msg)); self.end_headers()
    def do_GET(self):
        security_error=self._request_security_error("GET")
        if security_error:
            self.send("درخواست رد شد.","text/plain; charset=utf-8",403)
            return
        u=urlparse(self.path); path=u.path.strip('/'); q=parse_qs(u.query); msg=q.get('msg',[''])[0]
        if path.startswith('static/'):
            try:
                target=(STATIC_DIR / path.removeprefix('static/')).resolve()
                target.relative_to(STATIC_DIR.resolve())
                if not target.is_file(): raise FileNotFoundError
                mime='font/woff2' if target.suffix.lower()=='.woff2' else (mimetypes.guess_type(str(target))[0] or 'application/octet-stream')
                if mime.startswith('text/') or mime in ('application/javascript','application/json','image/svg+xml'): mime += '; charset=utf-8'
                self.send(target.read_bytes(),mime); return
            except (ValueError, OSError):
                self.send('Not Found','text/plain; charset=utf-8',404); return
        with LOCK, conn() as c:
            if path=='backup':
                try:
                    snapshot=create_startup_backup()
                    if snapshot is None or not snapshot.is_file():
                        raise FileNotFoundError("هنوز پایگاه داده‌ای برای پشتیبان‌گیری وجود ندارد.")
                    data=snapshot.read_bytes()
                    self.send_response(200)
                    self.send_header('Content-Type','application/octet-stream')
                    self.send_header('Content-Disposition','attachment; filename="business-backup.db"')
                    self.send_header('Content-Length',str(len(data)))
                    self.send_header('X-Content-Type-Options','nosniff')
                    self.end_headers()
                    self.wfile.write(data)
                except Exception as e:self.send(str(e),status=500)
                return
            if path=='export.xlsx':
                try:
                    product_rows=[["name","code","unit","stock","avg_cost","market_price","min_stock","category","purchase_unit","purchase_factor","sale_unit","sale_factor","roll_weight","sheet_area","notes"]]
                    for r in c.execute("""SELECT name,code,unit,stock,avg_cost,market_price,min_stock,category,purchase_unit,purchase_factor,sale_unit,sale_factor,roll_weight,sheet_area,notes FROM products ORDER BY name"""):
                        product_rows.append([r[k] for k in ("name","code","unit","stock","avg_cost","market_price","min_stock","category","purchase_unit","purchase_factor","sale_unit","sale_factor","roll_weight","sheet_area","notes")])
                    people_rows=[["name","kind","phone","notes"]]
                    for r in c.execute("SELECT name,kind,phone,notes FROM people ORDER BY name"):
                        people_rows.append([r[k] for k in ("name","kind","phone","notes")])
                    payload=build_xlsx_workbook([("Products",product_rows),("People",people_rows)])
                    self.send_response(200)
                    self.send_header("Content-Type","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                    self.send_header("Content-Disposition",'attachment; filename="AhanModiriat-Export.xlsx"')
                    self.send_header("Content-Length",str(len(payload)))
                    self.send_header("X-Content-Type-Options","nosniff")
                    self.end_headers()
                    self.wfile.write(payload)
                except Exception as e:
                    self.send(str(e),"text/plain; charset=utf-8",500)
                return
            if path=='export.csv':
                import csv, io
                out=io.StringIO(); w=csv.writer(out); w.writerow(['نوع','تاریخ','شرح','مبلغ/درآمد','هزینه/اصل','یادداشت'])
                for r in c.execute('SELECT date, name, qty*unit_price, qty*cost_basis+extra_cost, notes FROM sales JOIN products ON products.id=sales.product_id'):w.writerow(['فروش کالا',*r])
                for r in c.execute('SELECT date,title,revenue,cost,notes FROM services'):w.writerow(['خدمت',*r])
                for r in c.execute('SELECT date,category,amount,business,notes FROM expenses'):w.writerow(['پرداخت',*r])
                self.send('\ufeff'+out.getvalue(),'text/csv; charset=utf-8'); return
            if path=='reports':
                start=to_iso_date(q.get('start',[show_date(jalali_month_start_iso())])[0]); end=to_iso_date(q.get('end',[show_date(TODAY)])[0])
                try:
                    x=calc(c,start,end)
                    body=f'''<h1>گزارش بازه انتخابی</h1><div class="small">از {esc(show_date(start))} تا {esc(show_date(end))}</div><div class="grid section"><div class="card metric"><div class="label">فروش کالا</div><div class="value">{money(x['sales_rev'])}</div></div><div class="card metric"><div class="label">سود فروش کالا</div><div class="value">{money(x['sales_rev']-x['sales_cost']-x['sales_extra'])}</div></div><div class="card metric"><div class="label">سود خدمات</div><div class="value">{money(x['service_rev']-x['service_cost'])}</div></div><div class="card metric"><div class="label">سود خالص</div><div class="value {'positive' if x['net']>=0 else 'negative'}">{money(x['net'])}</div></div></div><div class="card section">{table(['شرح','مبلغ تومان'],[['فروش کالا',money(x['sales_rev'])],['بهای تمام‌شده کالای فروخته‌شده',money(x['sales_cost'])],['هزینه مستقیم فروش',money(x['sales_extra'])],['درآمد خدمات',money(x['service_rev'])],['هزینه اجرای خدمات',money(x['service_cost'])],['هزینه‌های کسب‌وکار',money(x['exp'])],['سود/کارمزد اقساط',money(x['interest'])],['سود خالص این بازه',money(x['net'])],['وجه دریافت‌شده از فروش کالا',money(x['sales_received'])],['وجه دریافت‌شده خدمات',money(x['services_received'])],['پرداخت خرید ثبت‌شده',money(x['purchases_paid'])],['کل اقساط پرداختی (خروج نقد)',money(x['loan_paid'])]])}</div><div class="actions"><a class="btn secondary" href="/reports">بازگشت به گزارش‌های دوره‌ای</a></div>'''
                    self.send(page('گزارش بازه',body,'reports',msg)); return
                except Exception:self.send(page('گزارش‌ها','<div class="notice">تاریخ‌ها را به شکل شمسی ۱۴۰۵/۰۷/۰۱ وارد کنید.</div>','reports'));return
            if path=='edit_product':
                try: self.send(product_editor(c,int(parse_qs(urlparse(self.path).query).get('id',['0'])[0])))
                except Exception: self.send(page('خطا','<div class="notice">شناسه کالا نامعتبر است.</div>','products'))
                return
            if path=='product_ledger':
                try:
                    product_id=int(q.get('id',['0'])[0])
                    page_num=int(q.get('page',['1'])[0])
                    self.send(product_ledger_page(c,product_id,q.get('q',[''])[0],page_num))
                except Exception: self.send(page('خطا','<div class="notice">شناسه کالا نامعتبر است.</div>','products'))
                return
            if path in ('edit_purchase','edit_sale','edit_expense'):
                try:
                    record_id=int(q.get('id',['0'])[0])
                    editor={'edit_purchase':purchase_editor,'edit_sale':sale_editor,'edit_expense':expense_editor}[path]
                    self.send(editor(c,record_id))
                except Exception:
                    self.send(page('خطا','<div class="notice">شناسه سند نامعتبر است.</div>'))
                return
            pages={'':dash,'products':products,'purchases':purchases,'sales':sales,'services':services,'expenses':expenses,'loans':loans,'prices':prices,'reports':reports,'settings':settings,'design':design_page,'cash':cash_page,'parties':parties_page,'inventory':inventory_page,'buy-advice':purchase_advice,'returns':returns_page,'audit':audit_page}
            fn=pages.get(path)
            if not fn:self.send(page('یافت نشد','<h1>صفحه پیدا نشد</h1>'));return
            if path=='parties':
                try:
                    page_num=int(q.get('page',['1'])[0])
                    statement_page=int(q.get('spage',['1'])[0])
                except (TypeError,ValueError):
                    page_num=1; statement_page=1
                self.send(parties_page(c,q.get('name',[''])[0],q.get('q',[''])[0],page_num,statement_page))
            elif path in ('products','purchases','sales','services','expenses','cash','inventory','audit','returns'):
                try: page_num=int(q.get('page',['1'])[0])
                except (TypeError,ValueError): page_num=1
                self.send(fn(c,q.get('q',[''])[0],page_num))
            elif path=='prices':
                try:
                    selected_product_id=int(q.get('product_id',['0'])[0])
                    page_num=int(q.get('page',['1'])[0])
                except (TypeError,ValueError):
                    selected_product_id=0; page_num=1
                self.send(prices(c,selected_product_id,q.get('q',[''])[0],page_num))
            elif path=='loans':
                try: page_num=int(q.get('page',['1'])[0])
                except (TypeError,ValueError): page_num=1
                self.send(loans(c,q.get('q',[''])[0],page_num))
            else:
                self.send(fn(c))
    def do_POST(self):
        security_error=self._request_security_error("POST")
        if security_error:
            self.send("درخواست رد شد.","text/plain; charset=utf-8",403)
            return
        path=urlparse(self.path).path.strip('/')
        try:
            n=int(self.headers.get('Content-Length','0'))
        except (TypeError,ValueError):
            self.send("اندازه درخواست معتبر نیست.","text/plain; charset=utf-8",400)
            return
        if n < 0 or n > 105 * 1024 * 1024:
            self.redirect('/settings','اندازه درخواست معتبر نیست.')
            return
        raw_bytes=self.rfile.read(n)
        if path=='restore_backup':
            candidate_path=None
            try:
                content_type=self.headers.get('Content-Type','')
                header=(f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n").encode('ascii','strict')
                message=BytesParser(policy=email_policy).parsebytes(header+raw_bytes)
                if not message.is_multipart():
                    raise ValueError('فرم بارگذاری فایل معتبر نیست.')
                payload=None
                for part in message.iter_parts():
                    if part.get_param('name',header='content-disposition')=='backup_file':
                        payload=part.get_payload(decode=True)
                        break
                if not payload:
                    raise ValueError('فایل پشتیبان انتخاب نشده یا خالی است.')
                if len(payload)>100*1024*1024:
                    raise ValueError('حجم فایل پشتیبان از سقف ۱۰۰ مگابایت بیشتر است.')
                with tempfile.NamedTemporaryFile(prefix='.restore_candidate_',suffix='.db',dir=DATA,delete=False) as tmp:
                    tmp.write(payload)
                    candidate_path=Path(tmp.name)
                with LOCK:
                    restore_database_from_file(candidate_path)
                    with conn() as c:
                        details=json.dumps({"fields":["backup_file"],"bytes":len(payload)},ensure_ascii=False)
                        c.execute("INSERT INTO audit_log(action,details) VALUES(?,?)",("restore_backup",details))
                self.redirect('/settings','پشتیبان با موفقیت اعتبارسنجی و بازیابی شد؛ از اطلاعات قبلی نیز پشتیبان نگه داشته شد.')
            except Exception as e:
                self.redirect('/settings',str(e))
            finally:
                if candidate_path:
                    try: candidate_path.unlink(missing_ok=True)
                    except OSError: pass
            return
        if path=='import.xlsx':
            target_page='/products'
            try:
                content_type=self.headers.get('Content-Type','')
                header=(f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n").encode('ascii','strict')
                message=BytesParser(policy=email_policy).parsebytes(header+raw_bytes)
                if not message.is_multipart():
                    raise ValueError("فرم بارگذاری اکسل معتبر نیست.")
                payload=None; filename=""; sheet_choice="Products"
                for part in message.iter_parts():
                    field_name=part.get_param('name',header='content-disposition')
                    if field_name=='file':
                        payload=part.get_payload(decode=True) or b""
                        filename=part.get_filename() or ""
                    elif field_name=='sheet':
                        sheet_choice=(part.get_payload(decode=True) or b"Products").decode('utf-8','replace').strip()
                target_page='/parties' if sheet_choice.lower() in ('people','customers','اشخاص','طرف‌حساب‌ها') else '/products'
                if not filename.lower().endswith('.xlsx'):
                    raise ValueError("فقط فایل XLSX قابل ورود است.")
                workbook=parse_xlsx_workbook(payload)
                sheet_name=next((name for name in workbook if name.lower()==sheet_choice.lower()),None)
                if sheet_name is None:
                    wanted="People" if target_page=='/parties' else "Products"
                    sheet_name=next((name for name in workbook if name.lower()==wanted.lower()),None)
                if sheet_name is None:
                    raise ValueError("برگهٔ موردنظر در فایل اکسل پیدا نشد.")
                records=workbook[sheet_name]
                if len(records)<2:
                    raise ValueError("برگهٔ اکسل، ردیف داده‌ای برای ورود ندارد.")
                headers=[str(x or '').strip().lower() for x in records[0]]
                imported=0; skipped=0
                with LOCK, conn() as c:
                    for row_values in records[1:]:
                        row_values=(row_values+[""]*len(headers))[:len(headers)]
                        record={headers[i]:row_values[i] for i in range(len(headers)) if headers[i]}
                        name=str(record.get("name","") or "").strip()
                        if not name:
                            skipped+=1; continue
                        exists=c.execute("SELECT id FROM products WHERE name=?",(name,)).fetchone() if target_page=='/products' else c.execute("SELECT id FROM people WHERE name=?",(name,)).fetchone()
                        if exists:
                            skipped+=1; continue
                        if target_page=='/products':
                            unit=str(record.get("unit") or "کیلوگرم").strip()
                            stock=num(record.get("stock",0),0)
                            avg_cost=money_int(record.get("avg_cost",0),0)
                            market_price=money_int(record.get("market_price",0),0)
                            min_stock=num(record.get("min_stock",0),0)
                            pf=num(record.get("purchase_factor",1),1) or 1
                            sf=num(record.get("sale_factor",1),1) or 1
                            if stock<0 or min_stock<0 or pf<=0 or sf<=0 or avg_cost<0 or market_price<0:
                                skipped+=1; continue
                            c.execute("""INSERT INTO products(name,code,unit,stock,avg_cost,market_price,min_stock,category,purchase_unit,purchase_factor,sale_unit,sale_factor,roll_weight,sheet_area,notes)
                                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                      (name,str(record.get("code","") or ""),unit,stock,avg_cost,market_price,min_stock,
                                       str(record.get("category","سایر") or "سایر"),str(record.get("purchase_unit") or unit),pf,
                                       str(record.get("sale_unit") or unit),sf,num(record.get("roll_weight",0),0),
                                       num(record.get("sheet_area",0),0),str(record.get("notes","") or "")))
                        else:
                            kind=str(record.get("kind","both") or "both").strip().lower()
                            if kind not in ('customer','supplier','both'): kind='both'
                            c.execute("INSERT INTO people(name,kind,phone,notes) VALUES(?,?,?,?)",
                                      (name,kind,str(record.get("phone","") or ""),str(record.get("notes","") or "")))
                        imported+=1
                    audit_details=json.dumps({"sheet":sheet_name,"imported":imported,"skipped":skipped,"rows":max(0,len(records)-1)},ensure_ascii=False)
                    c.execute("INSERT INTO audit_log(action,details) VALUES(?,?)",("import.xlsx",audit_details))
                self.redirect(target_page,f"ورود اکسل انجام شد؛ {imported} ردیف افزوده و {skipped} ردیف رد شد (ردیف تکراری یا نامعتبر).")
            except Exception as e:
                self.redirect(target_page,str(e))
            return
        raw=raw_bytes.decode('utf-8')
        d={k:v[-1] for k,v in parse_qs(raw,keep_blank_values=True).items()}
        def v(k,default=''):return d.get(k,default).strip()
        try:
            with LOCK, conn() as c:
                if path in ('add_purchase','add_sale','add_expense'):
                    submission=d.get('_submission_token','').strip()
                    if not submission:
                        raise ValueError('فرم ثبت تراکنش شناسهٔ معتبر ندارد؛ صفحه را تازه‌سازی کن و دوباره ثبت کن.')
                    token_update=c.execute("UPDATE form_submission_tokens SET consumed_at=datetime('now','localtime') WHERE token=? AND action=? AND consumed_at IS NULL",(submission,path))
                    if token_update.rowcount!=1:
                        raise ValueError('این فرم قبلاً ارسال شده یا منقضی است؛ برای جلوگیری از ثبت تکراری، صفحه را تازه‌سازی کن.')
                if path=='add_product':
                    product_name=normalize_person(v('name'))
                    pf=num(v('purchase_factor',1)); sf=num(v('sale_factor',1))
                    if not product_name or pf<=0 or sf<=0: raise ValueError('نام کالا و ضرایب تبدیل معتبر الزامی هستند.')
                    duplicate=any(normalize_person(row['name']).casefold()==product_name.casefold() for row in c.execute('SELECT name FROM products'))
                    if duplicate: raise ValueError('این کالا قبلاً ثبت شده است؛ برای تغییر مشخصات، همان کالا را ویرایش کن.')
                    product_cur=c.execute('INSERT INTO products(name,code,unit,stock,avg_cost,market_price,min_stock,notes,category,purchase_unit,purchase_factor,sale_unit,sale_factor,roll_weight,sheet_area) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(product_name,v('code'),v('unit','کیلوگرم'),num(v('stock')),money_int(v('avg_cost')),money_int(v('market_price')),num(v('min_stock')),v('notes'),v('category','سایر'),v('purchase_unit',v('unit','کیلوگرم')),pf,v('sale_unit',v('unit','کیلوگرم')),sf,num(v('roll_weight')),num(v('sheet_area'))))
                    new_product_id=product_cur.lastrowid
                    dest='/products'; msg='کالا ثبت شد.'
                elif path=='update_product':
                    pid=int(v('product_id')); p=c.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone()
                    if not p: raise ValueError('کالا پیدا نشد.')
                    product_name=normalize_person(v('name'))
                    pf=num(v('purchase_factor')); sf=num(v('sale_factor')); new_stock=num(v('stock'),-1)
                    if not product_name or pf<=0 or sf<=0: raise ValueError('نام و ضرایب تبدیل باید معتبر باشند.')
                    duplicate=any(normalize_person(row['name']).casefold()==product_name.casefold() for row in c.execute('SELECT name FROM products WHERE id<>?',(pid,)))
                    if duplicate: raise ValueError('نام این کالا با کالای دیگری تکراری است.')
                    has_movement=any(scalar(c,f'SELECT COUNT(*) FROM {table} WHERE product_id=?',(pid,)) for table in ('purchases','sales','inventory_adjustments','purchase_returns','sales_returns'))
                    unit_mapping_changed=(
                        v('unit')!=p['unit'] or
                        abs(pf-float(p['purchase_factor'] or 1))>0.000001 or
                        abs(sf-float(p['sale_factor'] or 1))>0.000001 or
                        v('purchase_unit')!=p['purchase_unit'] or
                        v('sale_unit')!=p['sale_unit']
                    )
                    if has_movement and unit_mapping_changed:
                        raise ValueError('این کالا سابقهٔ گردش دارد؛ تغییر واحد پایه، واحد خرید/فروش یا ضریب تبدیل مسدود است تا مانده‌های تاریخی خراب نشوند.')
                    if new_stock<0: raise ValueError('موجودی کالا نمی‌تواند منفی باشد.')
                    old_stock=float(p['stock'] or 0); stock_delta=new_stock-old_stock
                    c.execute('UPDATE products SET name=?,code=?,unit=?,stock=?,avg_cost=?,market_price=?,min_stock=?,notes=?,category=?,purchase_unit=?,purchase_factor=?,sale_unit=?,sale_factor=?,roll_weight=?,sheet_area=? WHERE id=?',
                              (product_name,v('code'),v('unit'),new_stock,money_int(v('avg_cost')),money_int(v('market_price')),num(v('min_stock')),v('notes'),v('category','سایر'),v('purchase_unit'),pf,v('sale_unit'),sf,num(v('roll_weight')),num(v('sheet_area')),pid))
                    if abs(stock_delta)>0.000001:
                        c.execute("""INSERT INTO inventory_adjustments(date,product_id,expected_qty,counted_qty,delta_qty,reason,notes)
                                     VALUES(?,?,?,?,?,?,?)""",
                                  (to_iso_date(jalali_today()),pid,old_stock,new_stock,stock_delta,
                                   'اصلاح موجودی از فرم ویرایش کالا',v('notes') or 'تعدیل خودکار از صفحه ویرایش کالا'))
                    dest='/products'; msg='مشخصات کالا به‌روزرسانی شد؛ تغییر موجودی نیز در کارت گردش ثبت شد.' if abs(stock_delta)>0.000001 else 'مشخصات کالا به‌روزرسانی شد.'
                elif path=='add_purchase':
                    pid=int(v('product_id')); qty=num(v('qty')); cost=money_int(v('unit_cost')); extra=money_int(v('extra_cost')); paid=money_int(v('paid')); p=c.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone()
                    if not p or qty<=0 or cost<0 or extra<0 or paid<0: raise ValueError('کالا، مقدار یا قیمت/هزینه خرید نامعتبر است؛ مبالغ جانبی و پرداخت نباید منفی باشند.')
                    factor=num(p['purchase_factor'] if 'purchase_factor' in p.keys() else 1)
                    if factor<=0: raise ValueError('ضریب تبدیل واحد خرید باید بیشتر از صفر باشد.')
                    base_qty=qty*factor
                    newstock=p['stock']+base_qty; oldvalue=p['stock']*p['avg_cost']; newavg=(oldvalue+qty*cost+extra)/newstock if newstock else 0
                    purchase_cur=c.execute('INSERT INTO purchases(date,product_id,qty,unit_cost,extra_cost,supplier,paid,notes) VALUES(?,?,?,?,?,?,?,?)',(to_iso_date(v('date',jalali_today())),pid,qty,cost,extra,v('supplier'),paid,v('notes')))
                    purchase_id=purchase_cur.lastrowid
                    link_party(c,"purchases","supplier_person_id",purchase_id,v('supplier'),'supplier')
                    sync_cash_posting(c,"purchases",purchase_id,to_iso_date(v('date',jalali_today())),paid,"out",v('supplier'),v('notes') or "پرداخت خرید")
                    c.execute('UPDATE products SET stock=?,avg_cost=? WHERE id=?',(newstock,newavg,pid)); dest='/purchases';msg=f'خرید ثبت شد؛ {qty:g} {p["purchase_unit"]} معادل {base_qty:g} {p["unit"]} به موجودی اضافه شد.'
                elif path=='add_sale':
                    pid=int(v('product_id')); qty=num(v('qty')); price=money_int(v('unit_price')); extra=money_int(v('extra_cost')); received=money_int(v('received')); p=c.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone()
                    if not p or qty<=0 or price<=0 or extra<0 or received<0:raise ValueError('کالا، مقدار یا قیمت/هزینه فروش نامعتبر است؛ هزینه و دریافتی نباید منفی باشند.')
                    base_qty=qty*num(p['sale_factor'] if 'sale_factor' in p.keys() else 1)
                    if base_qty>p['stock']:raise ValueError(f"موجودی کافی نیست؛ موجودی فعلی {p['stock']:g} {p['unit']} است.")
                    base_price=price/num(p['sale_factor'] if 'sale_factor' in p.keys() else 1)
                    sale_cur=c.execute('INSERT INTO sales(date,product_id,qty,unit_price,extra_cost,customer,received,notes,cost_basis) VALUES(?,?,?,?,?,?,?,?,?)',(to_iso_date(v('date',jalali_today())),pid,base_qty,base_price,extra,v('customer'),received,v('notes'),p['avg_cost']))
                    sale_id=sale_cur.lastrowid
                    link_party(c,"sales","customer_person_id",sale_id,v('customer'),'customer')
                    sync_cash_posting(c,"sales",sale_id,to_iso_date(v('date',jalali_today())),received,"in",v('customer'),v('notes') or "دریافت فروش")
                    c.execute('UPDATE products SET stock=stock-? WHERE id=?',(base_qty,pid)); dest='/sales';msg=f'فروش ثبت شد؛ {qty:g} {p["sale_unit"]} معادل {base_qty:g} {p["unit"]} از موجودی کم شد.'
                elif path=='add_service':
                    service_cur=c.execute('INSERT INTO services(date,title,revenue,cost,received,customer,notes) VALUES(?,?,?,?,?,?,?)',(to_iso_date(v('date',jalali_today())),v('title'),money_int(v('revenue')),money_int(v('cost')),money_int(v('received')),v('customer'),v('notes')))
                    service_id=service_cur.lastrowid
                    link_party(c,"services","customer_person_id",service_id,v('customer'),'customer')
                    sync_cash_posting(c,"services",service_id,to_iso_date(v('date',jalali_today())),num(v('received')),"in",v('customer'),v('notes') or "دریافت خدمات")
                    dest='/services';msg='درآمد خدمات ثبت شد.'
                elif path=='add_expense':
                    date=to_iso_date(v('date',jalali_today())); category=normalize_person(v('category')); amount=money_int(v('amount'),-1)
                    business=v('business','1'); source=v('source','نامشخص')
                    if not category or amount<=0 or business not in ('0','1'):
                        raise ValueError('شرح، مبلغ یا نوع هزینه معتبر نیست؛ مبلغ باید بیشتر از صفر باشد.')
                    expense_cur=c.execute('INSERT INTO expenses(date,category,amount,source,business,notes) VALUES(?,?,?,?,?,?)',(date,category,amount,source,int(business),v('notes')))
                    expense_id=expense_cur.lastrowid
                    sync_cash_posting(c,"expenses",expense_id,date,amount,"out",source,v('notes') or "پرداخت هزینه")
                    dest='/expenses';msg='پرداخت هزینه ثبت شد.'
                elif path=='add_loan':
                    interval_value=int(num(v('interval_value',1)))
                    interval_unit=v('interval_unit','month')
                    if interval_value<1 or interval_value>365 or interval_unit not in ('day','week','month','year'):
                        raise ValueError('فاصله سررسید باید بین ۱ تا ۳۶۵ و واحد آن معتبر باشد.')
                    loan_cur=c.execute('INSERT INTO loans(title,principal,remaining,installment,next_date,rate_note,notes,interval_value,interval_unit) VALUES(?,?,?,?,?,?,?,?,?)',(v('title'),money_int(v('principal')),money_int(v('remaining')),money_int(v('installment')),to_iso_date(v('next_date')) if v('next_date') else '',v('rate_note'),v('notes'),interval_value,interval_unit))
                    new_loan_id=loan_cur.lastrowid
                    dest='/loans';msg='وام ثبت شد.'
                elif path=='add_payment':
                    lid=int(v('loan_id')); amount=money_int(v('amount')); principal=money_int(v('principal_part')); interest=money_int(v('interest_part')); loan=c.execute('SELECT * FROM loans WHERE id=?',(lid,)).fetchone()
                    if not loan:raise ValueError('وام انتخاب‌شده پیدا نشد.')
                    if abs(amount-principal-interest)>1:raise ValueError('مبلغ قسط باید با مجموع اصل و سود/کارمزد برابر باشد.')
                    if principal>loan['remaining']+0.01:raise ValueError('سهم اصل قسط از مانده اصل وام بیشتر است.')
                    payment_cur=c.execute('INSERT INTO loan_payments(loan_id,date,amount,principal_part,interest_part,source,notes) VALUES(?,?,?,?,?,?,?)',(lid,to_iso_date(v('date',jalali_today())),amount,principal,interest,v('source','نامشخص'),v('notes')))
                    payment_id=payment_cur.lastrowid
                    sync_cash_posting(c,"loan_payments",payment_id,to_iso_date(v('date',jalali_today())),amount,"out",v('source'),v('notes') or "پرداخت قسط وام")
                    nextdate=add_interval_date(loan['next_date'],loan['interval_value'],loan['interval_unit'])
                    c.execute('UPDATE loans SET remaining=MAX(0,remaining-?),next_date=? WHERE id=?',(principal,nextdate,lid));dest='/loans';msg='پرداخت قسط ثبت شد و مانده اصل و سررسید بعدی به‌روزرسانی شد.'
                elif path=='add_price':
                    pid=int(v('product_id')); price=money_int(v('market_price')); p=c.execute('SELECT id FROM products WHERE id=?',(pid,)).fetchone()
                    if not p:raise ValueError('کالا پیدا نشد.')
                    price_cur=c.execute('INSERT INTO price_history(date,product_id,market_price,notes) VALUES(?,?,?,?)',(to_iso_date(v('date',jalali_today())),pid,price,v('notes')))
                    price_id=price_cur.lastrowid
                    c.execute('UPDATE products SET market_price=? WHERE id=?',(price,pid));dest='/prices';msg='قیمت روز ثبت شد.'
                elif path=='add_person':
                    name=normalize_person(v('name')); kind=v('kind','both')
                    if not name: raise ValueError('نام طرف حساب الزامی است.')
                    if kind not in ('customer','supplier','both'): raise ValueError('نوع طرف حساب معتبر نیست.')
                    existing=c.execute('SELECT id FROM people WHERE name=?',(name,)).fetchone()
                    if existing: raise ValueError('این طرف حساب قبلاً ثبت شده است.')
                    person_id=ensure_person(c,name,kind,v('phone'),v('notes'))
                    dest='/parties';msg='طرف حساب ثبت شد.'
                elif path=='add_settlement':
                    party=normalize_person(v('party')); kind=v('kind'); amount=money_int(v('amount'))
                    if not party: raise ValueError('طرف حساب را انتخاب کن.')
                    if kind not in ('receive','pay') or amount<=0: raise ValueError('نوع یا مبلغ تسویه نامعتبر است.')
                    person_id=ensure_person(c,party,'both')
                    date=to_iso_date(v('date',jalali_today()))
                    cur=c.execute('INSERT INTO settlements(date,party,kind,amount,notes) VALUES(?,?,?,?,?)',(date,party,kind,amount,v('notes')))
                    settlement_id=cur.lastrowid
                    c.execute("UPDATE settlements SET person_id=? WHERE id=?",(person_id,settlement_id))
                    sync_cash_posting(c,'settlements',settlement_id,date,amount,'in' if kind=='receive' else 'out',party,v('notes') or 'تسویه حساب')
                    dest='/parties';msg='تسویه ثبت شد و دفتر صندوق به‌روز شد.'
                elif path=='update_purchase':
                    rid=int(v('record_id'))
                    row=c.execute("SELECT * FROM purchases WHERE id=?",(rid,)).fetchone()
                    if row is None: raise ValueError('سند خرید پیدا نشد.')
                    assert_purchase_reversible(c,row)
                    product=c.execute("SELECT * FROM products WHERE id=?",(row["product_id"],)).fetchone()
                    qty=num(v("qty"),-1); cost=money_int(v("unit_cost"),-1); extra=money_int(v("extra_cost")); paid=money_int(v("paid"),-1)
                    if qty<=0 or cost<0 or extra<0 or paid<0: raise ValueError('مقدار و مبالغ خرید باید معتبر و غیرمنفی باشند.')
                    factor=num(product["purchase_factor"] or 1,1) or 1
                    stock_before=float(product["stock"] or 0)-float(row["qty"])*factor
                    if stock_before < -0.000001: raise ValueError('برگشت این خرید موجودی منفی ایجاد می‌کند؛ بررسی دستی لازم است.')
                    value_before=float(product["stock"] or 0)*float(product["avg_cost"] or 0)-(float(row["qty"])*float(row["unit_cost"])+float(row["extra_cost"]))
                    if value_before < -0.05: raise ValueError('بهای خرید قبلی با ارزش موجودی فعلی سازگار نیست؛ اصلاح خودکار ایمن نیست.')
                    value_before=max(value_before,0.0)
                    new_stock=stock_before+qty*factor
                    new_value=value_before+qty*cost+extra
                    new_avg=new_value/new_stock if new_stock>0.000001 else 0
                    c.execute("UPDATE purchases SET qty=?,unit_cost=?,extra_cost=?,paid=?,supplier=?,notes=? WHERE id=?",
                              (qty,cost,extra,paid,v("supplier"),v("notes"),rid))
                    c.execute("UPDATE products SET stock=?,avg_cost=? WHERE id=?",(new_stock,new_avg,row["product_id"]))
                    link_party(c,"purchases","supplier_person_id",rid,v("supplier"),"supplier")
                    sync_cash_posting(c,"purchases",rid,row["date"],paid,"out",v("supplier"),v("notes") or "اصلاح پرداخت خرید")
                    dest='/purchases';msg='خرید اصلاح شد و موجودی/میانگین موزون بازسازی شد.'
                elif path=='delete_purchase':
                    rid=int(v('record_id'))
                    row=c.execute("SELECT * FROM purchases WHERE id=?",(rid,)).fetchone()
                    if row is None: raise ValueError('سند خرید پیدا نشد.')
                    assert_purchase_reversible(c,row)
                    product=c.execute("SELECT * FROM products WHERE id=?",(row["product_id"],)).fetchone()
                    factor=num(product["purchase_factor"] or 1,1) or 1
                    new_stock=float(product["stock"] or 0)-float(row["qty"])*factor
                    if new_stock < -0.000001: raise ValueError('حذف این خرید موجودی منفی ایجاد می‌کند.')
                    new_value=float(product["stock"] or 0)*float(product["avg_cost"] or 0)-(float(row["qty"])*float(row["unit_cost"])+float(row["extra_cost"]))
                    if new_value < -0.05: raise ValueError('بهای خرید با ارزش موجودی فعلی سازگار نیست؛ حذف خودکار ایمن نیست.')
                    new_avg=max(new_value,0.0)/new_stock if new_stock>0.000001 else 0
                    c.execute("DELETE FROM cash_movements WHERE source_table='purchases' AND source_id=?",(rid,))
                    c.execute("DELETE FROM purchases WHERE id=?",(rid,))
                    c.execute("UPDATE products SET stock=?,avg_cost=? WHERE id=?",(max(new_stock,0.0),new_avg,row["product_id"]))
                    dest='/purchases';msg='خرید حذف شد و موجودی/میانگین موزون برگشت داده شد.'
                elif path=='update_sale':
                    rid=int(v('record_id'))
                    row=c.execute("SELECT * FROM sales WHERE id=?",(rid,)).fetchone()
                    if row is None: raise ValueError('سند فروش پیدا نشد.')
                    assert_sale_reversible(c,row)
                    product=c.execute("SELECT * FROM products WHERE id=?",(row["product_id"],)).fetchone()
                    qty=num(v("qty"),-1); price=money_int(v("unit_price"),-1); extra=money_int(v("extra_cost")); received=money_int(v("received"),-1)
                    if qty<=0 or price<0 or extra<0 or received<0: raise ValueError('مقدار و مبالغ فروش باید معتبر و غیرمنفی باشند.')
                    new_stock=float(product["stock"] or 0)+float(row["qty"])-qty
                    if new_stock < -0.000001: raise ValueError('اصلاح مقدار فروش موجودی منفی ایجاد می‌کند.')
                    c.execute("UPDATE sales SET qty=?,unit_price=?,extra_cost=?,received=?,customer=?,notes=? WHERE id=?",
                              (qty,price,extra,received,v("customer"),v("notes"),rid))
                    c.execute("UPDATE products SET stock=? WHERE id=?",(max(new_stock,0.0),row["product_id"]))
                    link_party(c,"sales","customer_person_id",rid,v("customer"),"customer")
                    sync_cash_posting(c,"sales",rid,row["date"],received,"in",v("customer"),v("notes") or "اصلاح دریافت فروش")
                    dest='/sales';msg='فروش اصلاح شد و اختلاف موجودی برگشت داده شد.'
                elif path=='delete_sale':
                    rid=int(v('record_id'))
                    row=c.execute("SELECT * FROM sales WHERE id=?",(rid,)).fetchone()
                    if row is None: raise ValueError('سند فروش پیدا نشد.')
                    assert_sale_reversible(c,row)
                    product=c.execute("SELECT * FROM products WHERE id=?",(row["product_id"],)).fetchone()
                    new_stock=float(product["stock"] or 0)+float(row["qty"])
                    c.execute("DELETE FROM cash_movements WHERE source_table='sales' AND source_id=?",(rid,))
                    c.execute("DELETE FROM sales WHERE id=?",(rid,))
                    c.execute("UPDATE products SET stock=? WHERE id=?",(new_stock,row["product_id"]))
                    dest='/sales';msg='فروش حذف شد و موجودی برگشت داده شد.'
                elif path=='update_expense':
                    rid=int(v('record_id'))
                    row=c.execute("SELECT * FROM expenses WHERE id=?",(rid,)).fetchone()
                    if row is None: raise ValueError('سند هزینه پیدا نشد.')
                    date=to_iso_date(v('date',jalali_today())); category=v('category'); amount=money_int(v('amount'),-1)
                    business=v('business','1'); source=v('source','نامشخص')
                    if not category or amount<=0 or business not in ('0','1'): raise ValueError('شرح، مبلغ یا نوع هزینه معتبر نیست؛ مبلغ باید بیشتر از صفر باشد.')
                    c.execute("UPDATE expenses SET date=?,category=?,amount=?,source=?,business=?,notes=? WHERE id=?",
                              (date,category,amount,source,int(business),v('notes'),rid))
                    sync_cash_posting(c,"expenses",rid,date,amount,"out",source,v('notes') or "اصلاح هزینه")
                    dest='/expenses';msg='هزینه/برداشت اصلاح شد.'
                elif path=='delete_expense':
                    rid=int(v('record_id'))
                    row=c.execute("SELECT id FROM expenses WHERE id=?",(rid,)).fetchone()
                    if row is None: raise ValueError('سند هزینه پیدا نشد.')
                    c.execute("DELETE FROM cash_movements WHERE source_table='expenses' AND source_id=?",(rid,))
                    c.execute("DELETE FROM expenses WHERE id=?",(rid,))
                    dest='/expenses';msg='هزینه/برداشت حذف شد.'
                elif path=='add_sales_return':
                    sale_id=int(v("sale_id")); qty=num(v("qty"),-1); refund=money_int(v("refund_amount"),-1)
                    reason=normalize_person(v("reason"))
                    sale=c.execute("SELECT s.*,p.name,p.unit,p.stock,p.avg_cost FROM sales s JOIN products p ON p.id=s.product_id WHERE s.id=?",(sale_id,)).fetchone()
                    if sale is None: raise ValueError("سند فروش اصلی پیدا نشد.")
                    if qty<=0 or refund<0 or not reason: raise ValueError("مقدار، وجه برگشتی یا علت مرجوعی معتبر نیست.")
                    already=float(scalar(c,"SELECT COALESCE(SUM(qty),0) FROM sales_returns WHERE sale_id=?",(sale_id,)) or 0)
                    remaining=float(sale["qty"])-already
                    if qty>remaining+0.000001: raise ValueError(f"مقدار مرجوعی از ماندهٔ قابل برگشت بیشتر است؛ مانده {remaining:g} {sale['unit']} است.")
                    return_value=money_int(qty*float(sale["unit_price"]))
                    if refund>return_value:
                        raise ValueError("وجه برگشتی از ارزش فروش مرجوع‌شده بیشتر است؛ مبلغ اضافه را جداگانه به‌عنوان هزینه ثبت کن.")
                    cost_value=qty*float(sale["cost_basis"])
                    extra_reversed=float(sale["extra_cost"] or 0)*qty/float(sale["qty"])
                    c.execute("""INSERT INTO sales_returns(date,sale_id,product_id,customer,qty,return_value,cost_basis,extra_reversed,refund_amount,reason,notes)
                                 VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                              (to_iso_date(v("date",jalali_today())),sale_id,sale["product_id"],sale["customer"] or "",qty,return_value,float(sale["cost_basis"] or 0),extra_reversed,refund,reason,v("notes")))
                    return_id=c.execute("SELECT last_insert_rowid()").fetchone()[0]
                    product=c.execute("SELECT stock,avg_cost FROM products WHERE id=?",(sale["product_id"],)).fetchone()
                    old_stock=float(product["stock"] or 0); old_value=old_stock*float(product["avg_cost"] or 0)
                    new_stock=old_stock+qty; new_avg=(old_value+cost_value)/new_stock if new_stock>0 else 0
                    c.execute("UPDATE products SET stock=?,avg_cost=? WHERE id=?",(new_stock,new_avg,sale["product_id"]))
                    link_party(c,"sales_returns","customer_person_id",return_id,sale["customer"],"customer")
                    sync_cash_posting(c,"sales_returns",return_id,to_iso_date(v("date",jalali_today())),refund,"out",sale["customer"],reason)
                    dest='/returns';msg='مرجوعی فروش ثبت شد؛ موجودی، سود و صندوق به‌روزرسانی شد.'
                elif path=='add_purchase_return':
                    purchase_id=int(v("purchase_id")); qty=num(v("qty"),-1); cash_refund=money_int(v("cash_refund"),-1)
                    reason=normalize_person(v("reason"))
                    purchase=c.execute("""SELECT p.*,pr.name,pr.unit,pr.stock,pr.avg_cost,pr.purchase_factor
                                           FROM purchases p JOIN products pr ON pr.id=p.product_id WHERE p.id=?""",(purchase_id,)).fetchone()
                    if purchase is None: raise ValueError("سند خرید اصلی پیدا نشد.")
                    if qty<=0 or cash_refund<0 or not reason: raise ValueError("مقدار، وجه برگشتی یا علت مرجوعی معتبر نیست.")
                    factor=float(purchase["purchase_factor"] or 1)
                    if factor<=0: raise ValueError("ضریب تبدیل واحد خرید معتبر نیست.")
                    bought_base=float(purchase["qty"])*factor
                    already=float(scalar(c,"SELECT COALESCE(SUM(qty),0) FROM purchase_returns WHERE purchase_id=?",(purchase_id,)) or 0)
                    remaining=max(0.0,bought_base-already)
                    if qty>remaining+0.000001: raise ValueError(f"مقدار مرجوعی از خرید اصلی بیشتر است؛ مانده {remaining:g} {purchase['unit']} است.")
                    if qty>float(purchase["stock"] or 0)+0.000001: raise ValueError("موجودی فعلی برای این مرجوعی کافی نیست.")
                    unit_base_cost=float(purchase["unit_cost"] or 0)/factor
                    extra_per_base=float(purchase["extra_cost"] or 0)/bought_base if bought_base else 0
                    return_value=money_int(qty*(unit_base_cost+extra_per_base))
                    if cash_refund>return_value+0.99: raise ValueError("وجه دریافتی از فروشنده نمی‌تواند از ارزش مرجوعی بیشتر باشد.")
                    product=c.execute("SELECT stock,avg_cost FROM products WHERE id=?",(purchase["product_id"],)).fetchone()
                    old_stock=float(product["stock"] or 0); new_stock=old_stock-qty
                    if new_stock < -0.000001: raise ValueError("موجودی فعلی از مقدار مرجوعی کمتر است.")
                    new_stock=max(0.0,new_stock); new_avg=float(product["avg_cost"] or 0) if new_stock>0 else 0
                    cur=c.execute("""INSERT INTO purchase_returns(date,purchase_id,product_id,supplier,qty,return_value,cash_refund,reason,notes)
                                     VALUES(?,?,?,?,?,?,?,?,?)""",
                                  (to_iso_date(v("date",jalali_today())),purchase_id,purchase["product_id"],purchase["supplier"] or "",qty,return_value,cash_refund,reason,v("notes")))
                    return_id=cur.lastrowid
                    c.execute("UPDATE products SET stock=?,avg_cost=? WHERE id=?",(new_stock,new_avg,purchase["product_id"]))
                    link_party(c,"purchase_returns","supplier_person_id",return_id,purchase["supplier"],"supplier")
                    sync_cash_posting(c,"purchase_returns",return_id,to_iso_date(v("date",jalali_today())),cash_refund,"in",purchase["supplier"],reason)
                    dest='/returns';msg='مرجوعی خرید ثبت شد؛ موجودی، حساب فروشنده و صندوق به‌روزرسانی شد.'
                elif path=='inventory_adjust':
                    pid=int(v('product_id')); counted=num(v('counted_qty'),-1)
                    product=c.execute("SELECT * FROM products WHERE id=?",(pid,)).fetchone()
                    reason=normalize_person(v('reason'))
                    if product is None: raise ValueError('کالا پیدا نشد.')
                    if counted<0: raise ValueError('موجودی شمارش‌شده نمی‌تواند منفی باشد.')
                    if not reason: raise ValueError('علت انبارگردانی را وارد کن.')
                    expected=float(product['stock'] or 0); delta=counted-expected
                    if abs(delta)<0.000001: raise ValueError('موجودی شمارش‌شده با موجودی دفتری برابر است؛ تعدیلی برای ثبت وجود ندارد.')
                    date=to_iso_date(v('date',jalali_today()))
                    adjustment_cur=c.execute("""INSERT INTO inventory_adjustments(date,product_id,expected_qty,counted_qty,delta_qty,reason,notes)
                                 VALUES(?,?,?,?,?,?,?)""",(date,pid,expected,counted,delta,reason,v('notes')))
                    adjustment_id=adjustment_cur.lastrowid
                    c.execute("UPDATE products SET stock=? WHERE id=?",(counted,pid))
                    dest='/inventory';msg=f'انبارگردانی ثبت شد؛ اختلاف {delta:+g} {product["unit"]} اعمال شد.'
                elif path=='add_cash_movement':
                    kind=v('kind'); amount=money_int(v('amount'))
                    if amount<=0: raise ValueError('مبلغ گردش باید عدد صحیح بزرگ‌تر از صفر باشد.')
                    date=to_iso_date(v('date',jalali_today())); src=v('from_account_id'); dst=v('to_account_id')
                    src_id=int(src) if src else None; dst_id=int(dst) if dst else None
                    if kind=='deposit':
                        if not dst_id: raise ValueError('حساب مقصد برای واریز را انتخاب کن.')
                        c.execute("INSERT INTO cash_movements(date,kind,to_account_id,amount,party,note) VALUES(?,'deposit',?,?,?,?)",(date,dst_id,amount,normalize_person(v('party')),v('note')))
                    elif kind=='withdraw':
                        if not src_id: raise ValueError('حساب مبدأ برای برداشت را انتخاب کن.')
                        c.execute("INSERT INTO cash_movements(date,kind,from_account_id,amount,party,note) VALUES(?,'withdraw',?,?,?,?)",(date,src_id,amount,normalize_person(v('party')),v('note')))
                    elif kind=='transfer':
                        if not src_id or not dst_id or src_id==dst_id: raise ValueError('برای انتقال، دو حساب متفاوت انتخاب کن.')
                        c.execute("INSERT INTO cash_movements(date,kind,from_account_id,to_account_id,amount,party,note) VALUES(?,'transfer',?,?,?,?,?)",(date,src_id,dst_id,amount,normalize_person(v('party')),v('note')))
                    else: raise ValueError('نوع گردش نقدی نامعتبر است.')
                    cash_movement_id=c.execute("SELECT last_insert_rowid()").fetchone()[0]
                    dest='/cash';msg='گردش حساب ثبت شد.'
                elif path=='save_capital':
                    amount=money_int(v('amount')); capital_date=to_iso_date(v('date',jalali_today()))
                    c.execute('UPDATE opening_capital SET amount=?,date=? WHERE id=1',(amount,capital_date))
                    c.execute("UPDATE cash_accounts SET opening_balance=?,updated_at=datetime('now','localtime') WHERE id=1",(amount,))
                    dest='/settings';msg='تنظیمات سرمایه اولیه ذخیره شد.'
                else:raise ValueError('درخواست نامعتبر است.')
                audit_record_id = (
                    d.get("record_id") or locals().get("return_id") or locals().get("purchase_id")
                    or locals().get("sale_id") or locals().get("service_id") or locals().get("expense_id")
                    or locals().get("payment_id") or locals().get("new_loan_id") or locals().get("price_id")
                    or locals().get("settlement_id") or locals().get("person_id")
                    or locals().get("cash_movement_id") or locals().get("adjustment_id")
                    or locals().get("new_product_id") or d.get("product_id") or d.get("loan_id") or ""
                )
                audit_details = json.dumps({
                    "actor": "local_user",
                    "record_id": audit_record_id,
                    "fields": sorted(str(key) for key in d.keys()),
                    "values_stored": False,
                }, ensure_ascii=False)
                c.execute('INSERT INTO audit_log(action,details) VALUES(?,?)',(path, audit_details))
            self.redirect(dest,msg)
        except Exception as e:
            self.redirect('/'+({'add_product':'products','update_product':'products','add_purchase':'purchases','update_purchase':'purchases','delete_purchase':'purchases','add_sale':'sales','update_sale':'sales','delete_sale':'sales','add_service':'services','add_expense':'expenses','update_expense':'expenses','delete_expense':'expenses','add_loan':'loans','add_payment':'loans','add_price':'prices','save_capital':'settings','add_cash_movement':'cash','add_person':'parties','add_settlement':'parties','add_sales_return':'returns','add_purchase_return':'returns','inventory_adjust':'inventory'}.get(path,'')),str(e))

def main():
    init(); host='127.0.0.1'; port=int(os.environ.get('AHAN_PORT','8765'))
    server=ThreadingHTTPServer((host,port),Handler)
    print('\nآهن‌مدیریت آماده است. مرورگر را باز کنید: http://127.0.0.1:%s' % port)
    print('اطلاعات در این مسیر ذخیره می‌شوند: %s' % DB)
    print('برای توقف برنامه، در این پنجره Ctrl+C را بزنید.\n')
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
if __name__=='__main__': main()
