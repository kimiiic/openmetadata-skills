#!/usr/bin/env node
'use strict';

const { spawnSync, spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const PKG_ROOT = path.resolve(__dirname, '..');
const VENV_DIR = path.join(PKG_ROOT, '.venv');

function hasUv() {
  const result = spawnSync('uv', ['--version'], { stdio: 'ignore' });
  return result.status === 0;
}

function bootstrap() {
  if (fs.existsSync(VENV_DIR)) return;

  process.stderr.write('First run: installing Python dependencies with uv...\n');
  const result = spawnSync('uv', ['sync', '--directory', PKG_ROOT], {
    stdio: 'inherit',
    cwd: PKG_ROOT,
  });
  if (result.status !== 0) {
    process.stderr.write('uv sync failed. Check that uv is installed: https://docs.astral.sh/uv/\n');
    process.exit(result.status ?? 1);
  }
}

function main() {
  if (!hasUv()) {
    process.stderr.write(
      'uv is required but not found.\n' +
        'Install it: curl -LsSf https://astral.sh/uv/install.sh | sh\n' +
        'Then re-run your command.\n'
    );
    process.exit(1);
  }

  bootstrap();

  const args = process.argv.slice(2);
  const result = spawnSync('uv', ['run', '--directory', PKG_ROOT, 'discover-data', ...args], {
    stdio: 'inherit',
    cwd: PKG_ROOT,
  });
  process.exit(result.status ?? 0);
}

main();
