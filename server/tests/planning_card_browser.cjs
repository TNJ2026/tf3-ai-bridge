// Run with Playwright installed (NODE_PATH may point to bundled dependencies).
const { chromium } = require('playwright');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1000, height: 900 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const html = readFileSync(path.join(__dirname, '../src/tf3_mcp/planning_card.html'), 'utf8');
    await page.setContent('<style>body{margin:0}iframe{border:0;width:100%;height:150px}</style><iframe></iframe>');
    await page.evaluate(html => {
      window.messages = [];
      window.addEventListener('message', e => {
        const m = e.data;
        window.messages.push(m);
        if (m.method === 'ui/initialize') e.source.postMessage({ jsonrpc: '2.0', id: m.id, result: { hostContext: { containerDimensions: { maxHeight: 760 } } } }, '*');
        if (m.method === 'ui/notifications/size-changed') document.querySelector('iframe').style.height = m.params.height + 'px';
        if (m.method === 'ui/open-link') e.source.postMessage({ jsonrpc: '2.0', id: m.id, result: {} }, '*');
      });
      document.querySelector('iframe').srcdoc = html;
    }, html);
    const frame = page.frames().find(f => f.parentFrame());
    await frame.waitForFunction(() => document.documentElement.clientHeight === 760);
    const image = await page.evaluate(() => {
      const canvas = document.createElement('canvas'); canvas.width = 1600; canvas.height = 1100;
      const ctx = canvas.getContext('2d'); ctx.fillStyle = '#306080'; ctx.fillRect(0, 0, 1600, 1100);
      return canvas.toDataURL('image/png');
    });
    await page.evaluate(image => document.querySelector('iframe').contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: { _meta: { planningCard: { title: '贵州规划', scope: 'global', image, htmlUrl: 'http://127.0.0.1:12345/report.html' } } } }, '*'), image);
    await frame.waitForFunction(() => !document.querySelector('#image').hidden);
    const measure = () => frame.evaluate(() => {
      const v = document.querySelector('#viewport'), i = document.querySelector('#image');
      const r = i.getBoundingClientRect(), vr = v.getBoundingClientRect();
      return { width: r.width, height: r.height, x: r.x, y: r.y, viewportWidth: vr.width, viewportHeight: vr.height,
        documentHeight: document.documentElement.scrollHeight, documentWidth: document.documentElement.scrollWidth,
        titleX: document.querySelector('#title').getBoundingClientRect().x, viewportX: vr.x,
        zoom: document.querySelector('#zoom').textContent, minDisabled: document.querySelector('#minus').disabled, maxDisabled: document.querySelector('#plus').disabled };
    });
    const fit = await measure();
    assert.ok(fit.viewportHeight < 760 && fit.viewportHeight > 650);
    assert.equal(fit.documentHeight, 760);
    assert.equal(fit.x, fit.viewportX); assert.equal(fit.y, await frame.locator("#viewport").evaluate(v => v.getBoundingClientRect().y));
    assert.equal(await frame.locator("#scope").count(), 0);
    assert.equal(await frame.locator("#status").isVisible(), false);
    assert.ok(fit.width >= fit.viewportWidth-0.01 && fit.height >= fit.viewportHeight-0.01);
    assert.ok(Math.abs(fit.width / fit.height - 1600 / 1100) < 1e-4);
    assert.equal(fit.zoom, '100%');
    assert.equal(await frame.locator('body').evaluate(e=>getComputedStyle(e).backgroundColor), 'rgba(0, 0, 0, 0)');
    assert.equal(await frame.locator('#viewport').evaluate(e=>getComputedStyle(e).backgroundColor), 'rgba(0, 0, 0, 0)');
    await page.mouse.move(400,300); await page.mouse.down(); await page.mouse.move(250,300); await page.mouse.up();
    assert.ok((await measure()).x < fit.x, 'default cover image must be draggable');
    assert.equal(await frame.locator('#fit').count(), 0);
    assert.equal(await frame.locator('nav').evaluate(n => getComputedStyle(n).position), 'absolute');
    for (let i = 0; i < 20; i++) await frame.locator('#plus').click({ force: true });
    const maximum = await measure();
    assert.equal(maximum.zoom, '500%'); assert.equal(maximum.maxDisabled, true);
    assert.ok(Math.abs(maximum.width - fit.width * 5) < 0.1);
    assert.equal(maximum.documentHeight, 760);
    assert.equal(maximum.documentWidth, 1000);
    await page.mouse.move(400, 300); await page.mouse.down(); await page.mouse.move(250, 200); await page.mouse.up();
    assert.ok((await measure()).x < maximum.x);
    await frame.locator('#viewport').focus(); await page.keyboard.press('ArrowRight');
    await frame.locator('#html').click();
    assert.equal(await page.evaluate(() => window.messages.filter(m => m.method === 'ui/open-link').length), 1);
    await page.evaluate(() => { document.querySelector('iframe').style.width = '320px'; document.querySelector('iframe').contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/host-context-changed', params: { containerDimensions: { height: 420 } } }, '*'); });
    await frame.waitForFunction(() => document.documentElement.clientHeight === 420);
    for (let i = 0; i < 20; i++) await frame.locator('#minus').click({ force: true });
    const small = await measure();
    assert.ok(parseInt(small.zoom) < 100); assert.equal(small.minDisabled, true);
    assert.ok(small.width <= 320 && small.height <= 420);
    assert.equal(small.documentWidth, 320); assert.equal(small.documentHeight, 420);
    assert.deepEqual(errors, []);
    console.log('PASS: transparent card, default cover, default drag, full-image minimum, 5x limit, resize and HTML link');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
