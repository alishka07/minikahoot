/**
 * Собирает frontend/public/quizo-demo.html из авторского бандла
 * video/Quizo Quiz Loop.html (экспорт Claude Design).
 *
 * Бандл рассчитан на просмотр как отдельная страница-«видео»: он рисует
 * панель воспроизведения со скраббером, плавающую кнопку Tweaks и бейдж
 * «Unpacking...». На лендинге всё это лишнее, поэтому мы дописываем свой
 * <style> в шаблон, который бандлер разворачивает в документ.
 *
 * Запуск: node scripts/build-demo-embed.mjs
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(here, '../../video/Quizo Quiz Loop.html');
const OUT = resolve(here, '../public/quizo-demo.html');

// Стиль уезжает в шаблон, а не в исходный <head>: бандлер заменяет документ
// целиком, поэтому всё, что лежит в первоначальной разметке, пропадает.
const EMBED_STYLE = `
<style>
  /* Авторская обвязка Claude Design: панель проигрывателя и Tweaks. */
  [data-omelette-chrome] { display: none !important; }
  html, body { height: 100%; margin: 0; background: #06060f; overflow: hidden; }
  /* Сцена рисуется как position:absolute; inset:0 — ей нужен растянутый предок. */
  x-dc, x-import { position: absolute; inset: 0; display: block; }
</style>
`.trim();

const html = readFileSync(SRC, 'utf8');
const lines = html.split('\n');

// 1. Бейдж «Unpacking...» виден до подмены документа — гасим его на месте.
const headStyle = lines.findIndex((l) => l.includes('#__bundler_loading { position: fixed'));
if (headStyle === -1) throw new Error('не нашёл стиль #__bundler_loading');
lines[headStyle] = lines[headStyle].replace(
  '#__bundler_loading { position: fixed',
  '#__bundler_loading { display: none !important; position: fixed',
);

// 2. Свой стиль — в конец <helmet> шаблона, последним в каскаде.
const tpl = lines.findIndex((l) => l.includes('<script type="__bundler/template">'));
if (tpl === -1) throw new Error('не нашёл шаблон бандлера');
const body = tpl + 1;
const template = JSON.parse(lines[body]);
if (!template.includes('<\/helmet>')) throw new Error('не нашёл <\/helmet> в шаблоне');
const patched = template.replace('<\/helmet>', `${EMBED_STYLE}\n<\/helmet>`);

// Закрывающие теги экранируем как в оригинале: строка живёт внутри <script>,
// и голый </script> в ней оборвал бы элемент.
lines[body] = JSON.stringify(patched).replace(/<\//g, '<\u002F');

writeFileSync(OUT, lines.join('\n'));
console.log(`quizo-demo.html: ${(lines.join('\n').length / 1024 / 1024).toFixed(2)} MB`);
