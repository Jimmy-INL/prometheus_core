#!/usr/bin/env node
/**
 * Build script for ThatOpen IFC bundle
 *
 * Run with: node build.mjs
 * Requires: npm install
 */

import * as esbuild from 'esbuild';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));

// Entry point that exports what we need
const entryContent = `
// Import ThatOpen components
import * as OBC from '@thatopen/components';
import * as OBCF from '@thatopen/components-front';
import * as THREE from 'three';

// Expose on window
window.OBC = OBC;
window.OBCF = OBCF;
window.THREE = THREE;

console.log('[ifc-bundle] ThatOpen components loaded');
window.dispatchEvent(new CustomEvent('ifc-ready', { detail: { version: 'bundled' } }));
`;

async function build() {
  console.log('Building ThatOpen IFC bundle...');

  try {
    await esbuild.build({
      stdin: {
        contents: entryContent,
        resolveDir: __dirname,
        loader: 'js',
      },
      bundle: true,
      outfile: join(__dirname, 'bundle.js'),
      format: 'iife',
      platform: 'browser',
      target: ['es2020'],
      minify: true,
      sourcemap: true,
      logLevel: 'info',
      define: {
        'global': 'window',
      },
    });

    console.log('ThatOpen IFC bundle created at public/js/ifc/bundle.js');
  } catch (err) {
    console.error('Build failed:', err);
    process.exit(1);
  }
}

build();
