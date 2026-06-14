#!/usr/bin/env node
/**
 * Headless shadeMap pre-compute.
 *
 * Ulaz (stdin, JSON):
 *   {
 *     "apiKey": "...",
 *     "samples": [{"km": 0.0, "lat": ..., "lon": ..., "deonica": "..."}, ...],
 *     "dates":   [{"key": "jun21", "label": "...", "start": "2026-06-21T05:00", "end": "2026-06-21T20:00"}, ...],
 *     "viewport": { "w": 1600, "h": 1000 }  // opciono
 *   }
 *
 * Izlaz (stdout, JSON):
 *   {
 *     "samples": [{"km": ..., "lat": ..., "lon": ..., "deonica": ..., "sun_hours": {"jun21": 8.4, ...}}, ...]
 *   }
 *
 * Browser console logovi idu na stderr — JSON na stdout ostaje čist.
 */
const puppeteer = require("puppeteer");
const fs = require("fs");

const HTML = `<!DOCTYPE html>
<html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<style>html,body,#map{margin:0;width:100%;height:100%;background:#000}</style>
</head><body>
<div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet-shadow-simulator/dist/leaflet-shadow-simulator.umd.min.js"></script>
</body></html>`;

async function readStdin() {
  return new Promise((resolve, reject) => {
    let buf = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (c) => (buf += c));
    process.stdin.on("end", () => resolve(buf));
    process.stdin.on("error", reject);
  });
}

async function main() {
  const raw = await readStdin();
  const input = JSON.parse(raw);
  const { apiKey, samples, dates } = input;
  const viewport = input.viewport || { w: 1600, h: 1000 };

  if (!apiKey) throw new Error("apiKey is required");
  if (!samples || !samples.length) throw new Error("samples is required");
  if (!dates || !dates.length) throw new Error("dates is required");

  const lats = samples.map((s) => s.lat);
  const lons = samples.map((s) => s.lon);
  const bounds = [
    [Math.min(...lats), Math.min(...lons)],
    [Math.max(...lats), Math.max(...lons)],
  ];

  const browser = await puppeteer.launch({
    headless: true,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      // shadeMap library zahteva WebGL; u headless Chromium-u nema GPU,
      // pa moramo eksplicitno dozvoliti software (SwiftShader) fallback.
      "--enable-unsafe-swiftshader",
      "--ignore-gpu-blocklist",
    ],
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: viewport.w, height: viewport.h });

    page.on("console", (msg) => process.stderr.write(`[browser] ${msg.text()}\n`));
    page.on("pageerror", (err) => process.stderr.write(`[pageerror] ${err.message}\n`));

    await page.setContent(HTML, { waitUntil: "networkidle0", timeout: 60000 });

    const result = await page.evaluate(
      async (apiKey, samples, dates, bounds) => {
        const map = L.map("map", {
          fadeAnimation: false,
          zoomAnimation: false,
          inertia: false,
          // attributionControl mora ostati — leaflet-shadow-simulator
          // direktno poziva map.attributionControl.addAttribution(...)
        });
        L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png").addTo(map);
        map.fitBounds(bounds, { padding: [40, 40] });

        await new Promise((r) => setTimeout(r, 2500));

        const terrainSource = {
          maxZoom: 15,
          tileSize: 256,
          getSourceUrl: ({ x, y, z }) =>
            `https://s3.amazonaws.com/elevation-tiles-prod/terrarium/${z}/${x}/${y}.png`,
          getElevation: ({ r, g, b }) => r * 256 + g + b / 256 - 32768,
        };

        const out = {
          samples: samples.map((s) => ({
            km: s.km,
            lat: s.lat,
            lon: s.lon,
            deonica: s.deonica,
            sun_hours: {},
          })),
        };

        const waitIdle = (shade) =>
          new Promise((resolve, reject) => {
            const timer = setTimeout(
              () => reject(new Error("idle timeout (60s)")),
              60000,
            );
            const handler = () => {
              clearTimeout(timer);
              resolve();
            };
            shade.once("idle", handler);
          });

        for (const cfg of dates) {
          console.log(`Computing ${cfg.key}...`);
          const shade = L.shadeMap({
            apiKey,
            color: "#000",
            opacity: 0,
            terrainSource,
            sunExposure: {
              enabled: true,
              startDate: new Date(cfg.start),
              endDate: new Date(cfg.end),
              iterations: 32,
            },
          }).addTo(map);

          await waitIdle(shade);

          for (let i = 0; i < samples.length; i++) {
            const s = samples[i];
            const pt = map.latLngToContainerPoint([s.lat, s.lon]);
            const hours = await shade.getHoursOfSun(pt.x, pt.y);
            out.samples[i].sun_hours[cfg.key] = hours;
          }

          map.removeLayer(shade);
        }
        return out;
      },
      apiKey,
      samples,
      dates,
      bounds,
    );

    process.stdout.write(JSON.stringify(result));
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  process.stderr.write(`ERROR: ${err.stack || err.message || err}\n`);
  process.exit(1);
});
