/**
 * Combined Loader for Chainlit Custom Elements
 *
 * Loads viewer bundles from their respective subdirectories.
 * Build bundles with: make build-vtk && make build-ifc
 */

// Load VTK bundle
if (window.vtk) {
  console.log('[loader] vtk.js already loaded');
} else {
  console.log('[loader] Loading vtk.js bundle...');

  const vtkScript = document.createElement('script');
  vtkScript.src = '/public/js/vtk/bundle.js';
  vtkScript.async = false;

  vtkScript.onload = function() {
    if (window.vtk) {
      console.log('[loader] vtk.js bundle loaded successfully');
    } else {
      console.error('[loader] VTK bundle loaded but window.vtk not set');
    }
  };

  vtkScript.onerror = function(err) {
    console.error('[loader] Failed to load vtk.js bundle:', err);
    window.vtkLoadError = 'Failed to load vtk bundle';
    window.dispatchEvent(new CustomEvent('vtk-error', { detail: { error: 'Failed to load bundle' } }));
  };

  document.head.appendChild(vtkScript);
}

// Load IFC bundle
if (window.OBC) {
  console.log('[loader] ThatOpen components already loaded');
} else {
  console.log('[loader] Loading ThatOpen IFC bundle...');

  const ifcScript = document.createElement('script');
  ifcScript.src = '/public/js/ifc/bundle.js';
  ifcScript.async = false;

  ifcScript.onload = function() {
    if (window.OBC) {
      console.log('[loader] ThatOpen IFC bundle loaded successfully');
    } else {
      console.error('[loader] IFC bundle loaded but window.OBC not set');
    }
  };

  ifcScript.onerror = function(err) {
    console.error('[loader] Failed to load ThatOpen IFC bundle:', err);
    window.ifcLoadError = 'Failed to load ifc bundle';
    window.dispatchEvent(new CustomEvent('ifc-error', { detail: { error: 'Failed to load bundle' } }));
  };

  document.head.appendChild(ifcScript);
}
