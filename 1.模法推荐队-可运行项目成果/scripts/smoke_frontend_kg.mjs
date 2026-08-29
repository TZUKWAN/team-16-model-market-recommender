#!/usr/bin/env node
/**
 * F4 知识图谱前端视觉 smoke 验证脚本。
 *
 * 流程：
 * 1. 启动后端 uvicorn（端口 8000）
 * 2. 启动前端 vite dev server（端口 5173，代理 /api 到 8000）
 * 3. 用 Playwright 访问首页
 * 4. 输入示例业务需求并解析
 * 5. 生成模型推荐
 * 6. 点击第一个推荐结果的「查看图谱」按钮
 * 7. 等待 ForceGraph2D 渲染稳定后截图
 * 8. 关闭前后端进程
 *
 * 使用：
 *   node scripts/smoke_frontend_kg.mjs
 *
 * 输出：
 *   reports/smoke/frontend_kg_smoke_01_main.png
 *   reports/smoke/frontend_kg_smoke_02_parsed.png
 *   reports/smoke/frontend_kg_smoke_03_recommended.png
 *   reports/smoke/frontend_kg_smoke_04_kg_graph.png
 *   reports/smoke/frontend_kg_smoke_05_fullpage.png
 */

import { spawn } from 'node:child_process';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const FRONTEND = path.join(ROOT, 'frontend');
const OUTPUT_DIR = path.join(ROOT, 'reports', 'smoke');

let chromium;
try {
  ({ chromium } = await import('playwright'));
} catch {
  try {
    ({ chromium } = await import(path.join(FRONTEND, 'node_modules', 'playwright', 'index.mjs')));
  } catch {
    console.error(
      '[kg-smoke] Playwright not found. Please install it temporarily:\n' +
      '  cd frontend && npm install -D playwright && npx playwright install chromium\n' +
      'Then run this script again.'
    );
    process.exit(1);
  }
}

fs.mkdirSync(OUTPUT_DIR, { recursive: true });

const SCREENSHOTS = {
  main: path.join(OUTPUT_DIR, 'frontend_kg_smoke_01_main.png'),
  parsed: path.join(OUTPUT_DIR, 'frontend_kg_smoke_02_parsed.png'),
  recommended: path.join(OUTPUT_DIR, 'frontend_kg_smoke_03_recommended.png'),
  kgGraph: path.join(OUTPUT_DIR, 'frontend_kg_smoke_04_kg_graph.png'),
  fullPage: path.join(OUTPUT_DIR, 'frontend_kg_smoke_05_fullpage.png'),
};

const QUERY = '帮我筛一批县域新客做首贷营销，最好能给出转化概率高的名单。';
const FRONTEND_URL = 'http://localhost:5173';
const HEALTH_URL = 'http://localhost:8000/api/v1/health';

function log(msg) {
  console.log(`[kg-smoke] ${msg}`);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForBackend(maxMs = 30000) {
  const start = Date.now();
  while (Date.now() - start < maxMs) {
    try {
      const res = await fetch(HEALTH_URL);
      if (res.ok) {
        log('backend health check passed');
        return;
      }
    } catch {
      // not ready yet
    }
    await sleep(1000);
  }
  throw new Error('backend health check failed');
}

function startBackend() {
  log('starting backend uvicorn on port 8000...');
  const proc = spawn(
    'python',
    ['-X', 'utf8', '-m', 'uvicorn', 'app.main:app', '--app-dir', 'backend', '--host', '127.0.0.1', '--port', '8000'],
    {
      cwd: ROOT,
      env: { ...process.env, PYTHONUTF8: '1' },
      stdio: 'pipe',
      windowsHide: true,
    }
  );
  proc.stdout.on('data', (d) => process.stdout.write(`[backend] ${d}`));
  proc.stderr.on('data', (d) => process.stderr.write(`[backend] ${d}`));
  return proc;
}

function startFrontend() {
  log('starting frontend vite dev server on port 5173...');
  const proc = spawn('npm.cmd', ['run', 'dev'], {
    cwd: FRONTEND,
    env: { ...process.env, VITE_API_BASE_URL: 'http://localhost:8000' },
    stdio: 'pipe',
    windowsHide: true,
  });
  proc.stdout.on('data', (d) => process.stdout.write(`[frontend] ${d}`));
  proc.stderr.on('data', (d) => process.stderr.write(`[frontend] ${d}`));
  return proc;
}

async function waitForFrontend(maxMs = 30000) {
  const start = Date.now();
  while (Date.now() - start < maxMs) {
    try {
      const res = await fetch(FRONTEND_URL);
      if (res.ok) {
        log('frontend dev server ready');
        return;
      }
    } catch {
      // not ready yet
    }
    await sleep(1000);
  }
  throw new Error('frontend dev server failed to start');
}

function killProcess(proc, label) {
  return new Promise((resolve) => {
    if (!proc) return resolve();
    log(`stopping ${label} (pid ${proc.pid})...`);
    try {
      // On Windows, spawn with kill tree
      if (process.platform === 'win32') {
        spawn('taskkill', ['/pid', String(proc.pid), '/T', '/F'], { windowsHide: true });
      } else {
        proc.kill('SIGTERM');
      }
    } catch (err) {
      log(`failed to kill ${label}: ${err.message}`);
    }
    setTimeout(resolve, 1500);
  });
}

async function runSmoke() {
  let backendProc = null;
  let frontendProc = null;
  let browser = null;

  try {
    backendProc = startBackend();
    await waitForBackend();

    frontendProc = startFrontend();
    await waitForFrontend();

    log('launching headless chromium...');
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await context.newPage();

    // 1. Main page
    log('opening frontend...');
    await page.goto(FRONTEND_URL, { waitUntil: 'networkidle' });
    await sleep(1000);
    await page.screenshot({ path: SCREENSHOTS.main });
    log(`saved ${SCREENSHOTS.main}`);

    // 2. Parse demand
    log('filling demand and parsing...');
    const inputSelector = 'textarea[placeholder*="业务需求"], textarea';
    await page.waitForSelector(inputSelector, { timeout: 10000 });
    await page.fill(inputSelector, QUERY);
    await page.click('button:has-text("解析需求")');
    await page.waitForSelector('.system-understanding, [class*="system-understanding"]', { timeout: 20000 });
    await sleep(1000);
    await page.screenshot({ path: SCREENSHOTS.parsed });
    log(`saved ${SCREENSHOTS.parsed}`);

    // 3. Recommend models
    log('requesting model recommendations...');
    await page.click('button:has-text("生成模型推荐")');
    await page.waitForSelector('.recommendation-panel, [class*="recommendation"]', { timeout: 20000 });
    await sleep(1500);
    await page.screenshot({ path: SCREENSHOTS.recommended });
    log(`saved ${SCREENSHOTS.recommended}`);

    // 4. Open knowledge graph
    log('opening knowledge graph view...');
    const kgButton = await page.locator('button:has-text("查看图谱")').first();
    if (await kgButton.count() === 0) {
      throw new Error('"查看图谱" button not found in recommendation panel');
    }
    await kgButton.click();

    // Wait for KnowledgeGraphView component to render and force graph to settle
    await page.waitForSelector('.knowledge-graph-view, .force-graph-container', { timeout: 20000 });
    await page.waitForSelector('.force-graph-container canvas', { timeout: 20000 });
    log('force graph canvas found, waiting for layout to settle...');
    await sleep(5000);

    // Screenshot the graph card specifically
    const graphCard = await page.locator('.knowledge-graph-view').first();
    if (await graphCard.count() > 0) {
      await graphCard.screenshot({ path: SCREENSHOTS.kgGraph });
    } else {
      await page.screenshot({ path: SCREENSHOTS.kgGraph });
    }
    log(`saved ${SCREENSHOTS.kgGraph}`);

    // 5. Full page screenshot
    await page.screenshot({ path: SCREENSHOTS.fullPage, fullPage: true });
    log(`saved ${SCREENSHOTS.fullPage}`);

    log('F4 knowledge graph smoke test completed successfully');
  } finally {
    if (browser) await browser.close();
    await killProcess(frontendProc, 'frontend');
    await killProcess(backendProc, 'backend');
  }
}

runSmoke().catch((err) => {
  console.error('[kg-smoke] FAILED:', err);
  process.exit(1);
});