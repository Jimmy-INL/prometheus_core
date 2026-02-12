#!/usr/bin/env node
/**
 * Build script for vtk.js bundle
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
// Import rendering profile to register WebGL backends
import '@kitware/vtk.js/Rendering/Profiles/Geometry';

// Import the modules we need
import vtkFullScreenRenderWindow from '@kitware/vtk.js/Rendering/Misc/FullScreenRenderWindow';
import vtkActor from '@kitware/vtk.js/Rendering/Core/Actor';
import vtkMapper from '@kitware/vtk.js/Rendering/Core/Mapper';
import vtkXMLPolyDataReader from '@kitware/vtk.js/IO/XML/XMLPolyDataReader';
import vtkColorTransferFunction from '@kitware/vtk.js/Rendering/Core/ColorTransferFunction';
import vtkCellPicker from '@kitware/vtk.js/Rendering/Core/CellPicker';

// Expose on window
window.vtk = {
  Rendering: {
    Misc: { vtkFullScreenRenderWindow },
    Core: { vtkActor, vtkMapper, vtkColorTransferFunction, vtkCellPicker },
  },
  IO: {
    XML: { vtkXMLPolyDataReader },
  },
};

console.log('[vtk-bundle] vtk.js loaded');
window.dispatchEvent(new CustomEvent('vtk-ready', { detail: { version: 'bundled' } }));
`;

async function build() {
  console.log('Building vtk.js bundle...');

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
    });

    console.log('vtk.js bundle created at public/js/vtk/bundle.js');
  } catch (err) {
    console.error('Build failed:', err);
    process.exit(1);
  }
}

build();
