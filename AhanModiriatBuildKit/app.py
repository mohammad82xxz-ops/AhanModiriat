# -*- coding: utf-8 -*-
"""AhanModiriat - local-first Persian steel inventory and cash/profit tracker.
Python standard library only. Data stays in ./data/business.db.
"""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from pathlib import Path
import sqlite3, json, datetime, html, os, threading, webbrowser, sys

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
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
        return
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

def init():
    create_startup_backup()
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, name TEXT NOT NULL, code TEXT DEFAULT '', unit TEXT NOT NULL DEFAULT 'کیلوگرم', stock REAL NOT NULL DEFAULT 0, avg_cost REAL NOT NULL DEFAULT 0, market_price REAL NOT NULL DEFAULT 0, min_stock REAL NOT NULL DEFAULT 0, notes TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS purchases(id INTEGER PRIMARY KEY, date TEXT NOT NULL, product_id INTEGER NOT NULL REFERENCES products(id), qty REAL NOT NULL, unit_cost REAL NOT NULL, extra_cost REAL NOT NULL DEFAULT 0, supplier TEXT DEFAULT '', paid REAL NOT NULL DEFAULT 0, notes TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS sales(id INTEGER PRIMARY KEY, date TEXT NOT NULL, product_id INTEGER NOT NULL REFERENCES products(id), qty REAL NOT NULL, unit_price REAL NOT NULL, extra_cost REAL NOT NULL DEFAULT 0, customer TEXT DEFAULT '', received REAL NOT NULL DEFAULT 0, notes TEXT DEFAULT '', cost_basis REAL NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS services(id INTEGER PRIMARY KEY, date TEXT NOT NULL, title TEXT NOT NULL, revenue REAL NOT NULL, cost REAL NOT NULL DEFAULT 0, received REAL NOT NULL DEFAULT 0, customer TEXT DEFAULT '', notes TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS expenses(id INTEGER PRIMARY KEY, date TEXT NOT NULL, category TEXT NOT NULL, amount REAL NOT NULL, source TEXT NOT NULL DEFAULT 'نامشخص', business INTEGER NOT NULL DEFAULT 1, notes TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS loans(id INTEGER PRIMARY KEY, title TEXT NOT NULL, principal REAL NOT NULL, remaining REAL NOT NULL, installment REAL NOT NULL, next_date TEXT DEFAULT '', rate_note TEXT DEFAULT '', notes TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS loan_payments(id INTEGER PRIMARY KEY, loan_id INTEGER NOT NULL REFERENCES loans(id), date TEXT NOT NULL, amount REAL NOT NULL, principal_part REAL NOT NULL, interest_part REAL NOT NULL, source TEXT NOT NULL DEFAULT 'نامشخص', notes TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS cash_events(id INTEGER PRIMARY KEY, date TEXT NOT NULL, kind TEXT NOT NULL, amount REAL NOT NULL, source TEXT NOT NULL DEFAULT '', notes TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS price_history(id INTEGER PRIMARY KEY, date TEXT NOT NULL, product_id INTEGER NOT NULL REFERENCES products(id), market_price REAL NOT NULL, notes TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit_log(
            id INTEGER PRIMARY KEY, created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            action TEXT NOT NULL, details TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS opening_capital(id INTEGER PRIMARY KEY CHECK(id=1), amount REAL NOT NULL DEFAULT 0, date TEXT NOT NULL);
        INSERT OR IGNORE INTO opening_capital(id,amount,date) VALUES(1,0,date('now'));
        ''')
    # Safe additive migration; existing transactions and history are preserved.
    with conn() as c:
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

def num(v, default=0):
    try: return float(str(v).replace(',','').strip() or default)
    except: return float(default)
def money(v): return f'{v:,.0f}'
def esc(v): return html.escape(str(v if v is not None else ''))
def fval(row,key,default=''):
    try:return row[key]
    except:return default

def scalar(c, sql, args=()):
    r=c.execute(sql,args).fetchone(); return (r[0] or 0) if r else 0

def calc(c, start=None, end=None):
    where=''; args=[]
    if start and end: where=' WHERE date BETWEEN ? AND ?'; args=[start,end]
    elif start: where=' WHERE date >= ?'; args=[start]
    elif end: where=' WHERE date <= ?'; args=[end]
    sales_rev=scalar(c,'SELECT COALESCE(SUM(qty*unit_price),0) FROM sales'+where,args)
    sales_cost=scalar(c,'SELECT COALESCE(SUM(qty*cost_basis),0) FROM sales'+where,args)
    sales_extra=scalar(c,'SELECT COALESCE(SUM(extra_cost),0) FROM sales'+where,args)
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

CSS='''
:root{--bg:#f3f5f8;--card:#fff;--ink:#172033;--muted:#667085;--line:#e3e7ef;--accent:#126b55;--accent2:#0d4e40;--bad:#b42318;--gold:#b7791f}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:Tahoma,"Segoe UI",sans-serif;direction:rtl}header{background:#132c2a;color:white;padding:18px max(18px,calc((100% - 1180px)/2));display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap}header strong{font-size:22px}header small{color:#c7ddd7}nav{background:#fff;border-bottom:1px solid var(--line);padding:10px max(12px,calc((100% - 1180px)/2));display:flex;gap:7px;flex-wrap:wrap}nav a{padding:9px 12px;border-radius:9px;color:#344054;text-decoration:none;font-size:13px}nav a:hover,nav a.active{background:#e3f2ed;color:#075e49}main{max-width:1180px;margin:22px auto;padding:0 16px 40px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.card{background:var(--card);border:1px solid var(--line);border-radius:15px;padding:17px;box-shadow:0 2px 8px #10182808}.metric .label{font-size:13px;color:var(--muted)}.metric .value{font-size:23px;font-weight:700;margin:10px 0 4px;overflow-wrap:anywhere}.muted{color:var(--muted);font-size:12px}.positive{color:var(--accent)}.negative{color:var(--bad)}h1{font-size:24px;margin:0 0 8px}h2{font-size:17px;margin:0 0 14px}.section{margin-top:18px}.twocol{display:grid;grid-template-columns:1fr 1fr;gap:14px}.formgrid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:11px}.field{display:flex;flex-direction:column;gap:6px}.field label{font-size:12px;color:#475467}input,select,textarea{font:inherit;border:1px solid #d0d5dd;border-radius:8px;padding:10px;background:white;color:#101828;min-width:0;width:100%}textarea{min-height:70px}button,.btn{background:var(--accent);border:0;border-radius:9px;color:white;padding:11px 15px;font:inherit;cursor:pointer;text-decoration:none;display:inline-block}button:hover,.btn:hover{background:var(--accent2)}.btn.secondary{background:#eef2f6;color:#344054}.btn.warn{background:#a33d23}.actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:12px}.tablewrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:right;padding:11px 9px;border-bottom:1px solid var(--line);white-space:nowrap}th{color:#475467;background:#f8fafc;font-weight:600}.notice{padding:12px 14px;border-radius:10px;background:#fff7e6;border:1px solid #ffe2a8;color:#7a4a00;font-size:13px;line-height:1.8}.success{padding:12px 14px;border-radius:10px;background:#e9f7f0;color:#126044;margin-bottom:12px}.small{font-size:12px;color:var(--muted);line-height:1.8}.pill{display:inline-block;padding:4px 8px;border-radius:30px;background:#eef2f6;font-size:11px}.empty{padding:25px;text-align:center;color:var(--muted)}footer{text-align:center;color:var(--muted);font-size:11px;padding:20px}@media(max-width:850px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.formgrid{grid-template-columns:repeat(2,minmax(0,1fr))}.twocol{grid-template-columns:1fr}}@media(max-width:520px){header strong{font-size:18px}.grid{grid-template-columns:1fr 1fr;gap:8px}.metric .value{font-size:18px}.card{padding:12px}.formgrid{grid-template-columns:1fr}main{padding:0 10px 25px}nav{gap:2px}nav a{padding:8px;font-size:12px}}
'''
NAV=[('','داشبورد'),('products','کالاها'),('purchases','خرید'),('sales','فروش'),('services','خدمات'),('expenses','هزینه‌ها'),('loans','وام‌ها'),('prices','قیمت روز'),('reports','گزارش‌ها'),('settings','تنظیمات')]
def page(title, body, active='', msg=''):
    nav=''.join(f'<a class="{"active" if key==active else ""}" href="/{key}">{label}</a>' for key,label in NAV)
    return f'''<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} | آهن‌مدیریت</title><style>{CSS}</style></head><body><header><div><strong>آهن‌مدیریت</strong><br><small>مدیریت محلی انبار، سود، سرمایه و نقدینگی</small></div><div class="small" style="color:#d2e3de">ذخیره روی همین کامپیوتر · بدون نیاز به اینترنت</div></header><nav>{nav}</nav><main>{f'<div class="success">{esc(msg)}</div>' if msg else ''}{body}</main><footer>آهن‌مدیریت · نسخه اولیه محلی · قبل از ثبت اطلاعات واقعی، از پایگاه داده پشتیبان بگیرید.</footer></body></html>'''
def field(label,name,typ='text',value='',required=False,step=None,placeholder=''):
    req='required' if required else ''; st=f' step="{step}"' if step else ''
    if typ == 'date':
        typ = 'text'
        value = show_date(value) if value else show_date(TODAY)
        placeholder = placeholder or '۱۴۰۵/۰۷/۰۱'
    ph=f' placeholder="{esc(placeholder)}"' if placeholder else ''
    return f'<div class="field"><label>{label}</label><input name="{name}" type="{typ}" value="{esc(value)}" {req}{st}{ph}></div>'
def selectfield(label,name,opts,required=True):
    opt=''.join(f'<option value="{esc(v)}">{esc(t)}</option>' for v,t in opts)
    return f'<div class="field"><label>{label}</label><select name="{name}" {"required" if required else ""}>{opt}</select></div>'
def table(headers, rows):
    if not rows:return '<div class="empty">هنوز اطلاعاتی ثبت نشده است.</div>'
    return '<div class="tablewrap"><table><thead><tr>'+''.join(f'<th>{h}</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{v}</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'
def options_products(c): return [(r['id'],f"{r['name']} (موجودی: {r['stock']:g} {r['unit']})") for r in c.execute('SELECT * FROM products ORDER BY name')]
def options_loans(c): return [(r['id'],r['title']) for r in c.execute('SELECT * FROM loans ORDER BY title')]
def dash(c):
    now=datetime.date.today(); week=(now-datetime.timedelta(days=now.weekday())).isoformat(); month=jalali_month_start_iso(); year=jalali_year_start_iso()
    d=calc(c,now.isoformat(),now.isoformat()); m=calc(c,month,now.isoformat()); y=calc(c,year,now.isoformat())
    stock_value=scalar(c,'SELECT SUM(stock*avg_cost) FROM products'); market_value=scalar(c,'SELECT SUM(stock*market_price) FROM products'); stock_delta=market_value-stock_value
    cash_in=scalar(c,'SELECT COALESCE(SUM(received),0) FROM sales')+scalar(c,'SELECT COALESCE(SUM(received),0) FROM services')
    cash_out=scalar(c,'SELECT COALESCE(SUM(paid),0) FROM purchases')+scalar(c,'SELECT COALESCE(SUM(amount),0) FROM expenses')+scalar(c,'SELECT COALESCE(SUM(amount),0) FROM loan_payments')
    low=c.execute('SELECT name,stock,min_stock,unit FROM products WHERE stock<=min_stock ORDER BY name').fetchall()
    due=c.execute("SELECT title,installment,next_date FROM loans WHERE remaining>0 ORDER BY next_date LIMIT 5").fetchall()
    def metric(label,val,note='',cls=''):
        return f'<div class="card metric"><div class="label">{label}</div><div class="value {cls}">{money(val)} تومان</div><div class="muted">{note}</div></div>'
    body=f'''<h1>داشبورد مدیریتی</h1><div class="small">تاریخ شمسی: {show_date(now.isoformat())} · مبالغ به تومان هستند. اعداد فقط بر اساس تراکنش‌های ثبت‌شده محاسبه می‌شوند.</div>
    <div class="grid section">{metric('سود خالص امروز',d['net'],'فروش و خدمات منهای هزینه‌ها و سود وام','positive' if d['net']>=0 else 'negative')}{metric('سود خالص این ماه',m['net'],'از ابتدای ماه تا امروز','positive' if m['net']>=0 else 'negative')}{metric('سود خالص امسال',y['net'],'از ابتدای سال شمسی تا امروز','positive' if y['net']>=0 else 'negative')}{metric('ارزش موجودی به بهای خرید',stock_value,'برآورد بر اساس میانگین بهای ثبت‌شده')}</div>
    <div class="grid section">{metric('ارزش موجودی به قیمت روز',market_value,'با آخرین قیمت روز واردشده')}{metric('تغییر ارزش برآوردی انبار',stock_delta,'جدا از سود نقدی فروش','positive' if stock_delta>=0 else 'negative')}{metric('کل اقساط پرداخت‌شده',scalar(c,'SELECT COALESCE(SUM(amount),0) FROM loan_payments'),'اصل و سود؛ خروج وجه نقد')}{metric('مانده اصل وام‌ها',scalar(c,'SELECT COALESCE(SUM(remaining),0) FROM loans'),'مانده ثبت‌شده وام‌ها')}</div>
    <div class="twocol section"><div class="card"><h2>هشدار موجودی کم</h2>{table(['کالا','موجودی','حداقل'],[[esc(r['name']),f"{r['stock']:g} {esc(r['unit'])}",f"{r['min_stock']:g}"] for r in low])}</div><div class="card"><h2>وام‌ها و اقساط آینده</h2>{table(['وام','قسط','سررسید بعدی'],[[esc(r['title']),money(r['installment'])+' تومان',esc(show_date(r['next_date']) if r['next_date'] else 'ثبت نشده')] for r in due])}</div></div>
    <div class="notice section"><b>تفسیر درست:</b> سود خالص با تغییر ارزش انبار یکی نیست. خرید کالا به‌خودی‌خود هزینه کامل سودوزیان محسوب نمی‌شود؛ بهای کالا هنگام فروش در سود معامله منظور می‌شود. پرداخت اصل وام نیز هزینه سودوزیان نیست، اما از نقدینگی کم می‌کند. این نسخه «بودجه خرج امن» را به‌صورت قطعی تعیین نمی‌کند مگر اینکه موجودی نقد آغاز دوره، مطالبات، بدهی‌های سررسیدشده و ذخیره خرید مجدد را هم دقیق ثبت کنی.</div>'''
    return page('داشبورد',body,'')

def products(c):
    rows=[]
    for r in c.execute('SELECT * FROM products ORDER BY name'):
        status='<span class="pill" style="background:#fff0ee;color:#b42318">موجودی کم</span>' if r['stock']<=r['min_stock'] else '<span class="pill">عادی</span>'
        edit=f'<a class="btn secondary" href="/edit_product?id={r["id"]}">ویرایش</a>'
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
    <div class="card section"><h2>فهرست کالاها</h2><div class="field"><label>جست‌وجو</label><input id="productSearch" placeholder="نام، کد یا دسته‌بندی" oninput="filterProducts()"></div>
    {table(['کالا','دسته‌بندی','کد','موجودی','بهای پایه','قیمت روز پایه','ارزش موجودی','وضعیت','عملیات'],rows)}</div>
    <script>function filterProducts(){{const q=document.getElementById('productSearch').value.toLowerCase();document.querySelectorAll('table tbody tr').forEach(r=>r.style.display=r.innerText.toLowerCase().includes(q)?'':'none')}}</script>'''
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
def purchases(c):
    prods=options_products(c); opt=[(v,t) for v,t in prods]
    body=f'''<h1>ثبت خرید</h1><div class="card section"><form method="post" action="/add_purchase"><div class="formgrid">{field('تاریخ خرید','date','date',TODAY,True)}{selectfield('کالا','product_id',opt)}{field('مقدار خرید','qty','number','1',True,'0.001')}{field('قیمت خرید هر واحد (تومان)','unit_cost','number','0',True,'0.01')}{field('هزینه جانبی کل (حمل/تخلیه)','extra_cost','number','0',False,'0.01')}{field('مبلغ پرداخت‌شده','paid','number','0',True,'0.01')}{field('فروشنده','supplier')}{field('یادداشت','notes')}</div><div class="actions"><button>ثبت خرید و افزایش موجودی</button></div></form><p class="small">پس از ثبت خرید، موجودی و میانگین موزون بهای خرید به‌روزرسانی می‌شود. هزینه جانبی به بهای تمام‌شده خرید اضافه می‌شود.</p></div>'''
    rows=[[show_date(r['date']),esc(r['name']),f"{r['qty']:g}",money(r['unit_cost']),money(r['extra_cost']),money(r['qty']*r['unit_cost']+r['extra_cost']),esc(r['supplier']),money(r['paid'])] for r in c.execute('SELECT p.*,pr.name FROM purchases p JOIN products pr ON pr.id=p.product_id ORDER BY p.date DESC,p.id DESC LIMIT 100')]
    body+=f'<div class="card section"><h2>آخرین خریدها</h2>{table(["تاریخ","کالا","مقدار","قیمت واحد","هزینه جانبی","جمع بهای خرید","فروشنده","پرداخت‌شده"],rows)}</div>'
    return page('خرید',body,'purchases')
def sales(c):
    body=f'''<h1>ثبت فروش کالا</h1><div class="card section"><form method="post" action="/add_sale"><div class="formgrid">{field('تاریخ فروش','date','date',TODAY,True)}{selectfield('کالا','product_id',options_products(c))}{field('مقدار فروش','qty','number','1',True,'0.001')}{field('قیمت فروش هر واحد (تومان)','unit_price','number','0',True,'0.01')}{field('هزینه مستقیم فروش','extra_cost','number','0',False,'0.01')}{field('وجه دریافت‌شده','received','number','0',True,'0.01')}{field('مشتری','customer')}{field('یادداشت','notes')}</div><div class="actions"><button>ثبت فروش و کسر موجودی</button></div></form><p class="small">بهای تمام‌شده از میانگین بهای خرید ثبت‌شده در همان لحظه ذخیره می‌شود تا گزارش سود فروش تاریخی با خریدهای بعدی تغییر نکند.</p></div>'''
    rows=[[show_date(r['date']),esc(r['name']),f"{r['qty']:g}",money(r['unit_price']),money(r['cost_basis']),money(r['qty']*(r['unit_price']-r['cost_basis'])-r['extra_cost']),esc(r['customer']),money(r['received'])] for r in c.execute('SELECT s.*,p.name FROM sales s JOIN products p ON p.id=s.product_id ORDER BY s.date DESC,s.id DESC LIMIT 100')]
    body+=f'<div class="card section"><h2>آخرین فروش‌ها</h2>{table(["تاریخ","کالا","مقدار","قیمت فروش","بهای تمام‌شده","سود معامله پس از هزینه مستقیم","مشتری","دریافت‌شده"],rows)}</div>'
    return page('فروش',body,'sales')
def services(c):
    body=f'''<h1>درآمد خدماتی</h1><div class="card section"><form method="post" action="/add_service"><div class="formgrid">{field('تاریخ','date','date',TODAY,True)}{field('شرح خدمت','title',required=True)}{field('درآمد خدمت (تومان)','revenue','number','0',True,'0.01')}{field('هزینه اجرای خدمت','cost','number','0',True,'0.01')}{field('وجه دریافت‌شده','received','number','0',True,'0.01')}{field('مشتری','customer')}{field('یادداشت','notes')}</div><div class="actions"><button>ثبت خدمت</button></div></form></div>'''
    rows=[[show_date(r['date']),esc(r['title']),money(r['revenue']),money(r['cost']),money(r['revenue']-r['cost']),money(r['received']),esc(r['customer'])] for r in c.execute('SELECT * FROM services ORDER BY date DESC,id DESC LIMIT 100')]
    body+=f'<div class="card section"><h2>خدمات ثبت‌شده</h2>{table(["تاریخ","خدمت","درآمد","هزینه اجرا","سود خدمت","دریافتی","مشتری"],rows)}</div>'
    return page('خدمات',body,'services')
def expenses(c):
    body=f'''<h1>هزینه‌ها و برداشت‌های شخصی</h1><div class="card section"><form method="post" action="/add_expense"><div class="formgrid">{field('تاریخ','date','date',TODAY,True)}{field('شرح/دسته هزینه','category',required=True)}{field('مبلغ (تومان)','amount','number','0',True,'0.01')}{selectfield('نوع','business',[('1','هزینه کسب‌وکار'),('0','برداشت شخصی/خانوادگی')])}{selectfield('منبع پرداخت','source',[('سود/درآمد جاری','سود/درآمد جاری'),('سرمایه/پس‌انداز','سرمایه/پس‌انداز'),('نامشخص','نامشخص')])}{field('توضیحات','notes')}</div><div class="actions"><button>ثبت پرداخت</button></div></form><p class="small">هزینه کسب‌وکار در سودوزیان کسر می‌شود؛ برداشت شخصی سود عملیاتی را کم نمی‌کند، اما از نقدینگی و سرمایه قابل‌استفاده کم می‌کند. منبع پرداخت یک تخصیص مدیریتی است و باید با موجودی نقد تطبیق داده شود.</p></div>'''
    rows=[[show_date(r['date']),esc(r['category']),money(r['amount']), 'هزینه کسب‌وکار' if r['business'] else 'برداشت شخصی',esc(r['source']),esc(r['notes'])] for r in c.execute('SELECT * FROM expenses ORDER BY date DESC,id DESC LIMIT 150')]
    body+=f'<div class="card section"><h2>آخرین پرداخت‌ها</h2>{table(["تاریخ","شرح","مبلغ","نوع","منبع","توضیحات"],rows)}</div>'
    return page('هزینه‌ها',body,'expenses')
def loans(c):
    body=f'''<h1>وام‌ها و اقساط</h1><div class="twocol section"><div class="card"><h2>ثبت وام</h2><form method="post" action="/add_loan"><div class="formgrid">{field('نام وام','title',required=True)}{field('مبلغ اولیه وام','principal','number','0',True,'0.01')}{field('مانده اصل بدهی','remaining','number','0',True,'0.01')}{field('مبلغ قسط','installment','number','0',True,'0.01')}{field('سررسید بعدی','next_date','date',TODAY)}{field('توضیح نرخ/شرایط','rate_note')}{field('یادداشت','notes')}</div><div class="actions"><button>ثبت وام</button></div></form></div><div class="card"><h2>ثبت پرداخت قسط</h2><form method="post" action="/add_payment"><div class="formgrid">{selectfield('وام','loan_id',options_loans(c))}{field('تاریخ پرداخت','date','date',TODAY,True)}{field('کل مبلغ پرداخت','amount','number','0',True,'0.01')}{field('سهم اصل وام','principal_part','number','0',True,'0.01')}{field('سهم سود/کارمزد','interest_part','number','0',True,'0.01')}{selectfield('منبع پرداخت','source',[('سود/درآمد جاری','سود/درآمد جاری'),('سرمایه/پس‌انداز','سرمایه/پس‌انداز'),('نامشخص','نامشخص')])}{field('یادداشت','notes')}</div><div class="actions"><button>ثبت پرداخت قسط</button></div></form><p class="small">مبلغ قسط باید برابر مجموع سهم اصل و سهم سود/کارمزد باشد. فقط سود/کارمزد هزینه سودوزیان است؛ اصل قسط بدهی را کم می‌کند.</p></div></div>'''
    rows=[[r['title'],money(r['principal']),money(r['remaining']),money(r['installment']),esc(show_date(r['next_date']) if r['next_date'] else ''),esc(r['rate_note'])] for r in c.execute('SELECT * FROM loans ORDER BY next_date')]
    body+=f'<div class="card section"><h2>وضعیت وام‌ها</h2>{table(["وام","اصل اولیه","مانده اصل","مبلغ قسط","سررسید بعدی","شرایط"],rows)}</div>'
    payments=[[show_date(r['date']),esc(r['title']),money(r['amount']),money(r['principal_part']),money(r['interest_part']),esc(r['source'])] for r in c.execute('SELECT lp.*,l.title FROM loan_payments lp JOIN loans l ON l.id=lp.loan_id ORDER BY lp.date DESC LIMIT 100')]
    body+=f'<div class="card section"><h2>تاریخچه پرداخت اقساط</h2>{table(["تاریخ","وام","پرداخت کل","اصل","سود/کارمزد","منبع"],payments)}</div>'
    return page('وام‌ها',body,'loans')
def prices(c):
    body=f'''<h1>قیمت روز بازار</h1><div class="card section"><form method="post" action="/add_price"><div class="formgrid">{field('تاریخ قیمت','date','date',TODAY,True)}{selectfield('کالا','product_id',options_products(c))}{field('قیمت بازار هر واحد (تومان)','market_price','number','0',True,'0.01')}{field('منبع/یادداشت','notes')}</div><div class="actions"><button>ثبت قیمت روز و به‌روزرسانی کالا</button></div></form><p class="small">ثبت قیمت جدید، قیمت روز فعلی کالا را به‌روزرسانی می‌کند ولی سود تحقق‌یافته معاملات قبلی را تغییر نمی‌دهد.</p></div>'''
    rows=[[show_date(r['date']),esc(r['name']),money(r['market_price']),esc(r['notes'])] for r in c.execute('SELECT h.*,p.name FROM price_history h JOIN products p ON p.id=h.product_id ORDER BY h.date DESC,h.id DESC LIMIT 200')]
    body+=f'<div class="card section"><h2>تاریخچه قیمت‌ها</h2>{table(["تاریخ","کالا","قیمت روز","یادداشت"],rows)}</div>'
    return page('قیمت روز',body,'prices')
def reports(c):
    start=html.escape(jalali_month_start_iso()); end=TODAY
    # query date range submitted by GET
    rows=[]
    for label,s,e in [('امروز',TODAY,TODAY),('این هفته',(datetime.date.today()-datetime.timedelta(days=datetime.date.today().weekday())).isoformat(),TODAY),('این ماه',jalali_month_start_iso(),TODAY),('امسال',jalali_year_start_iso(),TODAY)]:
        x=calc(c,s,e); rows.append([label,money(x['sales_rev']),money(x['sales_rev']-x['sales_cost']-x['sales_extra']),money(x['service_rev']-x['service_cost']),money(x['exp']),money(x['interest']),money(x['net'])])
    body=f'''<h1>گزارش سود، زیان و جریان نقدی</h1><div class="card section"><h2>مقایسه دوره‌ها (تاریخ بر اساس تقویم سیستم)</h2>{table(["دوره","فروش کالا","سود فروش کالا پس از هزینه مستقیم","سود خدمات","هزینه کسب‌وکار","سود/کارمزد وام","سود خالص"],rows)}</div>
    <div class="card section"><h2>گزارش بازه دلخواه</h2><form method="get" action="/reports"><div class="formgrid">{field('از تاریخ','start','date',start,True)}{field('تا تاریخ','end','date',end,True)}</div><div class="actions"><button>محاسبه بازه</button><a class="btn secondary" href="/export.csv">خروجی CSV تراکنش‌ها</a></div></form></div>'''
    qs=parse_qs(urlparse('').query)
    # handler sets range via special global? handled in do_GET before call
    return page('گزارش‌ها',body,'reports')
def settings(c):
    capital=c.execute('SELECT * FROM opening_capital WHERE id=1').fetchone()
    body=f'''<h1>تنظیمات و سرمایه اولیه</h1><div class="card section"><h2>ثبت سرمایه و وجه نقد آغاز دوره</h2><form method="post" action="/save_capital"><div class="formgrid">{field('سرمایه/وجه نقد آغاز دوره (تومان)','amount','number',str(capital['amount']),True,'0.01')}{field('تاریخ آغاز دوره','date','date',capital['date'],True)}</div><div class="actions"><button>ذخیره تنظیمات</button></div></form><p class="small">این مقدار برای شروع ثبت سوابق استفاده می‌شود؛ سرمایه اولیه با سود سالانه یکی نیست. برای محاسبه دقیق «چقدر از سرمایه خرج شده»، موجودی نقد، مطالبات، بدهی‌ها و موجودی کالا نیز باید کامل و درست ثبت شوند.</p></div><div class="card section"><h2>پشتیبان‌گیری</h2><p>پشتیبان خودکار پیش از شروع برنامه ساخته می‌شود و ۷ نسخه آخر در پوشه <code>data/backups</code> می‌ماند. برای نگهداری خارج از دستگاه، فایل پشتیبان را نیز جداگانه کپی کن.</p><div class="actions"><a class="btn" href="/backup">دریافت نسخه پشتیبان پایگاه داده</a></div><p class="small">دیتابیس با حالت WAL اجرا می‌شود. بازیابی از فایل هنوز در این مرحله اضافه نشده است.</p></div>'''
    return page('تنظیمات',body,'settings')

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def send(self,content,typ='text/html; charset=utf-8',status=200):
        raw=content if isinstance(content,bytes) else content.encode('utf-8')
        self.send_response(status); self.send_header('Content-Type',typ); self.send_header('Content-Length',str(len(raw))); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(raw)
    def redirect(self,path,msg=''):
        from urllib.parse import quote
        self.send_response(303); self.send_header('Location',path+('&' if '?' in path else '?')+'msg='+quote(msg)); self.end_headers()
    def do_GET(self):
        u=urlparse(self.path); path=u.path.strip('/'); q=parse_qs(u.query); msg=q.get('msg',[''])[0]
        with LOCK, conn() as c:
            if path=='backup':
                try: data=DB.read_bytes(); self.send_response(200); self.send_header('Content-Type','application/octet-stream'); self.send_header('Content-Disposition','attachment; filename="business-backup.db"'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
                except Exception as e:self.send(str(e),status=500)
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
            pages={'':dash,'products':products,'purchases':purchases,'sales':sales,'services':services,'expenses':expenses,'loans':loans,'prices':prices,'reports':reports,'settings':settings}
            fn=pages.get(path)
            if not fn:self.send(page('یافت نشد','<h1>صفحه پیدا نشد</h1>'));return
            self.send(fn(c) if path=='' else fn(c))
    def do_POST(self):
        path=urlparse(self.path).path.strip('/'); n=int(self.headers.get('Content-Length','0')); raw=self.rfile.read(n).decode('utf-8'); d={k:v[-1] for k,v in parse_qs(raw,keep_blank_values=True).items()}
        def v(k,default=''):return d.get(k,default).strip()
        try:
            with LOCK, conn() as c:
                if path=='add_product':
                    pf=num(v('purchase_factor',1)); sf=num(v('sale_factor',1))
                    if not v('name') or pf<=0 or sf<=0: raise ValueError('نام کالا و ضرایب تبدیل معتبر الزامی هستند.')
                    c.execute('INSERT INTO products(name,code,unit,stock,avg_cost,market_price,min_stock,notes,category,purchase_unit,purchase_factor,sale_unit,sale_factor,roll_weight,sheet_area) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(v('name'),v('code'),v('unit','کیلوگرم'),num(v('stock')),num(v('avg_cost')),num(v('market_price')),num(v('min_stock')),v('notes'),v('category','سایر'),v('purchase_unit',v('unit','کیلوگرم')),pf,v('sale_unit',v('unit','کیلوگرم')),sf,num(v('roll_weight')),num(v('sheet_area')))); dest='/products'; msg='کالا ثبت شد.'
                elif path=='update_product':
                    pid=int(v('product_id')); p=c.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone()
                    if not p: raise ValueError('کالا پیدا نشد.')
                    if v('unit')!=p['unit'] and (scalar(c,'SELECT COUNT(*) FROM purchases WHERE product_id=?',(pid,)) or scalar(c,'SELECT COUNT(*) FROM sales WHERE product_id=?',(pid,))):
                        raise ValueError('این کالا سابقه تراکنش دارد؛ تغییر واحد پایه برای جلوگیری از خراب‌شدن سوابق مسدود شد.')
                    pf=num(v('purchase_factor')); sf=num(v('sale_factor'))
                    if not v('name') or pf<=0 or sf<=0: raise ValueError('نام و ضرایب تبدیل باید معتبر باشند.')
                    c.execute('UPDATE products SET name=?,code=?,unit=?,stock=?,avg_cost=?,market_price=?,min_stock=?,notes=?,category=?,purchase_unit=?,purchase_factor=?,sale_unit=?,sale_factor=?,roll_weight=?,sheet_area=? WHERE id=?',(v('name'),v('code'),v('unit'),num(v('stock')),num(v('avg_cost')),num(v('market_price')),num(v('min_stock')),v('notes'),v('category','سایر'),v('purchase_unit'),pf,v('sale_unit'),sf,num(v('roll_weight')),num(v('sheet_area')),pid))
                    dest='/products'; msg='مشخصات کالا به‌روزرسانی شد.'
                elif path=='add_purchase':
                    pid=int(v('product_id')); qty=num(v('qty')); cost=num(v('unit_cost')); extra=num(v('extra_cost')); paid=num(v('paid')); p=c.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone()
                    if not p or qty<=0 or cost<0: raise ValueError('کالا، مقدار یا قیمت خرید نامعتبر است.')
                    factor=num(p['purchase_factor'] if 'purchase_factor' in p.keys() else 1)
                    if factor<=0: raise ValueError('ضریب تبدیل واحد خرید باید بیشتر از صفر باشد.')
                    base_qty=qty*factor
                    newstock=p['stock']+base_qty; oldvalue=p['stock']*p['avg_cost']; newavg=(oldvalue+qty*cost+extra)/newstock if newstock else 0
                    c.execute('INSERT INTO purchases(date,product_id,qty,unit_cost,extra_cost,supplier,paid,notes) VALUES(?,?,?,?,?,?,?,?)',(to_iso_date(v('date',jalali_today())),pid,qty,cost,extra,v('supplier'),paid,v('notes')))
                    c.execute('UPDATE products SET stock=?,avg_cost=? WHERE id=?',(newstock,newavg,pid)); dest='/purchases';msg=f'خرید ثبت شد؛ {qty:g} {p["purchase_unit"]} معادل {base_qty:g} {p["unit"]} به موجودی اضافه شد.'
                elif path=='add_sale':
                    pid=int(v('product_id')); qty=num(v('qty')); price=num(v('unit_price')); extra=num(v('extra_cost')); received=num(v('received')); p=c.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone()
                    if not p or qty<=0 or price<0:raise ValueError('کالا، مقدار یا قیمت فروش نامعتبر است.')
                    base_qty=qty*num(p['sale_factor'] if 'sale_factor' in p.keys() else 1)
                    if base_qty>p['stock']:raise ValueError(f"موجودی کافی نیست؛ موجودی فعلی {p['stock']:g} {p['unit']} است.")
                    base_price=price/num(p['sale_factor'] if 'sale_factor' in p.keys() else 1)
                    c.execute('INSERT INTO sales(date,product_id,qty,unit_price,extra_cost,customer,received,notes,cost_basis) VALUES(?,?,?,?,?,?,?,?,?)',(to_iso_date(v('date',jalali_today())),pid,base_qty,base_price,extra,v('customer'),received,v('notes'),p['avg_cost']))
                    c.execute('UPDATE products SET stock=stock-? WHERE id=?',(base_qty,pid)); dest='/sales';msg=f'فروش ثبت شد؛ {qty:g} {p["sale_unit"]} معادل {base_qty:g} {p["unit"]} از موجودی کم شد.'
                elif path=='add_service':
                    c.execute('INSERT INTO services(date,title,revenue,cost,received,customer,notes) VALUES(?,?,?,?,?,?,?)',(to_iso_date(v('date',jalali_today())),v('title'),num(v('revenue')),num(v('cost')),num(v('received')),v('customer'),v('notes')));dest='/services';msg='درآمد خدمات ثبت شد.'
                elif path=='add_expense':
                    c.execute('INSERT INTO expenses(date,category,amount,source,business,notes) VALUES(?,?,?,?,?,?)',(to_iso_date(v('date',jalali_today())),v('category'),num(v('amount')),v('source','نامشخص'),int(v('business','1')),v('notes')));dest='/expenses';msg='پرداخت ثبت شد.'
                elif path=='add_loan':
                    c.execute('INSERT INTO loans(title,principal,remaining,installment,next_date,rate_note,notes) VALUES(?,?,?,?,?,?,?)',(v('title'),num(v('principal')),num(v('remaining')),num(v('installment')),to_iso_date(v('next_date')) if v('next_date') else '',v('rate_note'),v('notes')));dest='/loans';msg='وام ثبت شد.'
                elif path=='add_payment':
                    lid=int(v('loan_id')); amount=num(v('amount')); principal=num(v('principal_part')); interest=num(v('interest_part')); loan=c.execute('SELECT * FROM loans WHERE id=?',(lid,)).fetchone()
                    if not loan:raise ValueError('وام انتخاب‌شده پیدا نشد.')
                    if abs(amount-principal-interest)>1:raise ValueError('مبلغ قسط باید با مجموع اصل و سود/کارمزد برابر باشد.')
                    if principal>loan['remaining']+0.01:raise ValueError('سهم اصل قسط از مانده اصل وام بیشتر است.')
                    c.execute('INSERT INTO loan_payments(loan_id,date,amount,principal_part,interest_part,source,notes) VALUES(?,?,?,?,?,?,?)',(lid,to_iso_date(v('date',jalali_today())),amount,principal,interest,v('source','نامشخص'),v('notes')))
                    nextdate=v('next_date')
                    c.execute('UPDATE loans SET remaining=MAX(0,remaining-?),next_date=CASE WHEN next_date<>"" THEN date(next_date,"+1 month") ELSE next_date END WHERE id=?',(principal,lid));dest='/loans';msg='پرداخت قسط ثبت شد و مانده اصل وام کاهش یافت.'
                elif path=='add_price':
                    pid=int(v('product_id')); price=num(v('market_price')); p=c.execute('SELECT id FROM products WHERE id=?',(pid,)).fetchone()
                    if not p:raise ValueError('کالا پیدا نشد.')
                    c.execute('INSERT INTO price_history(date,product_id,market_price,notes) VALUES(?,?,?,?)',(to_iso_date(v('date',jalali_today())),pid,price,v('notes')));c.execute('UPDATE products SET market_price=? WHERE id=?',(price,pid));dest='/prices';msg='قیمت روز ثبت شد.'
                elif path=='save_capital':
                    c.execute('UPDATE opening_capital SET amount=?,date=? WHERE id=1',(num(v('amount')),to_iso_date(v('date',jalali_today()))));dest='/settings';msg='تنظیمات سرمایه اولیه ذخیره شد.'
                else:raise ValueError('درخواست نامعتبر است.')
                c.execute('INSERT INTO audit_log(action,details) VALUES(?,?)',(path, json.dumps(d, ensure_ascii=False)))
            self.redirect(dest,msg)
        except Exception as e:
            self.redirect('/'+({'add_product':'products','update_product':'products','add_purchase':'purchases','add_sale':'sales','add_service':'services','add_expense':'expenses','add_loan':'loans','add_payment':'loans','add_price':'prices','save_capital':'settings'}.get(path,'')),str(e))

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
