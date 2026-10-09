"""Server-side Exodus/STL → VTP conversion for the React MeshViewer.

Restores the mesh pipeline that lived in the old Chainlit frontend
(``frontend/components/exodus/*`` + ``mesh_view.py`` + ``stl_integration.py``),
deleted in the ``old-frontend-removal`` cutover. The React viewer
(``frontend/src/viewers/mesh/*``) was rebuilt and is already wired; it only needs
the ``.vtp`` timesteps + manifest this package produces.

Layout:
  - ``models`` / ``cache`` / ``exceptions`` — vtk-free leaf modules (safe to import
    anywhere; used by the app-facing service and tests).
  - ``vtk_pipeline`` / ``stl`` / ``converter`` — the VTK-dependent conversion library
    (``import vtk``). Imported lazily by :mod:`service` so the app (and the offline
    test suite) never pulls VTK just to mount the router.
  - ``service`` — the app-facing async enrichment (``enrich_mesh_artifacts``) plus the
    cache-root/URL helpers the artifacts router shares. It owns the spawn-based
    ``ProcessPoolExecutor`` that the VTK-dependent modules actually run in, so a crash
    in them costs one artifact rather than the web process.
"""
