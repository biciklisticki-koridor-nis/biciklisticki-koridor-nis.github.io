/* obrazac.html -> obrazac.pdf, za štampu i nošenje na teren.
 *
 * Zašto preko pregledača a ne bibliotekom za PDF: obrazac ima ćirilične i
 * latinične dijakritike (č, ć, š, ž, đ), a većina lakih PDF biblioteka za njih
 * traži da se font ručno ugradi. Pregledač to već ume, a puppeteer je ionako
 * u projektu zbog provere stranica. Prednost je i što se isti obrazac može
 * otvoriti u pregledaču i odštampati direktno, bez ovog koraka.
 *
 * Pokretanje iz korena repo-a:  node docs/9.2-kalibracija-buke/napravi_pdf.js
 */
"use strict";

const path = require("path");
const puppeteer = require("puppeteer");

const HERE = __dirname;
const SRC = path.join(HERE, "obrazac.html");
const OUT = path.join(HERE, "obrazac.pdf");

(async () => {
  const browser = await puppeteer.launch({ args: ["--no-sandbox"] });
  const page = await browser.newPage();
  await page.goto("file://" + SRC, { waitUntil: "load" });
  await page.pdf({
    path: OUT,
    format: "A4",
    landscape: true,
    printBackground: true,      // bez ovoga nestaju zaglavlja tabele i okviri
    preferCSSPageSize: true,    // @page u obrascu nosi margine
  });
  await browser.close();
  console.log("-> " + path.relative(process.cwd(), OUT));
})().catch(err => {
  console.error("PDF nije napravljen:", err.message);
  process.exit(1);
});
