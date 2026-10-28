// Behavioral tests for the inline Jalali calendar conversion logic.
const fs = require("fs");
const vm = require("vm");
const assert = require("assert");

const source = fs.readFileSync("static/app.js", "utf8");
function extractFunction(name) {
  const start = source.indexOf("function " + name + "(");
  assert(start >= 0, "missing function " + name);
  const next = source.indexOf("\n function ", start + 1);
  assert(next >= 0, "cannot find end boundary for " + name);
  return source.slice(start, next).trim();
}

const j2gSource = extractFunction("j2g");
const jalaliDaysSource = extractFunction("jalaliDays");
const parseSource = extractFunction("parseJalali");
const context = {
  Date, Math,
  toLatin: value => String(value).replace(/[۰-۹٠-٩]/g, ch => {
    const fa = "۰۱۲۳۴۵۶۷۸۹", ar = "٠١٢٣٤٥٦٧٨٩";
    const idx = fa.indexOf(ch);
    return idx >= 0 ? String(idx) : String(ar.indexOf(ch));
  })
};
const result = vm.runInNewContext(
  j2gSource + "\n" + jalaliDaysSource + "\n" + parseSource +
  "\n({j2g, jalaliDays, parseJalali})",
  context
);
const fmt = d => d.map((n, i) => String(n).padStart(i === 0 ? 4 : 2, "0")).join("-");

assert.strictEqual(fmt(result.j2g(1405, 1, 1)), "2026-03-21");
assert.strictEqual(fmt(result.j2g(1405, 8, 6)), "2026-10-28");
assert.strictEqual(fmt(result.j2g(1404, 1, 1)), "2025-03-21");
assert.strictEqual(fmt(result.j2g(1403, 12, 30)), "2025-03-20");
assert.strictEqual(result.jalaliDays(1405, 1), 31);
assert.strictEqual(result.jalaliDays(1405, 7), 30);
assert.strictEqual(result.jalaliDays(1405, 12), 29);
assert.deepStrictEqual(
  Array.from(result.parseJalali("۱۴۰۵/۰۸/۰۶", [1400, 1, 1])),
  [1405, 8, 6]
);
assert.deepStrictEqual(
  Array.from(result.parseJalali("invalid", [1405, 8, 6])),
  [1405, 8, 6]
);
console.log("JALALI PICKER CONVERSION TESTS PASSED");
