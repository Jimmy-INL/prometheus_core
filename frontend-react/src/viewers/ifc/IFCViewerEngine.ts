import * as OBC from "@thatopen/components";
import * as FRAGS from "@thatopen/fragments";
import * as THREE from "three";

export type LoadProgress = {
  stage: "downloading" | "parsing" | "rendering";
  progress: number;
  message: string;
};

export type ViewerOptions = {
  container: HTMLElement;
  wasmCdnPath?: string;
};

export type EquipmentItem = { key: string; label: string };
export type PipeItem      = { key: string; label: string };

// IFC entity types that count as "pipe" elements.
const PIPE_MEMBER_IFC_CLASSES = ["IfcPipeSegment", "IfcPipeFitting"];

// IFC entity types that represent a "piece of equipment" — concrete classes plus
// the abstract flow-element bases so we catch elements that weren't given a
// concrete subtype during authoring.
const EQUIPMENT_IFC_CLASSES = [
  "IfcPump", "IfcValve", "IfcTank", "IfcFan", "IfcChiller", "IfcCompressor",
  "IfcBoiler", "IfcCoolingTower", "IfcHeatExchanger", "IfcEvaporator",
  "IfcCondenser", "IfcFilter", "IfcMotor", "IfcTransformer",
  "IfcAirTerminal", "IfcAirTerminalBox", "IfcSanitaryTerminal", "IfcFlowMeter",
  "IfcUnitaryEquipment", "IfcDistributionChamberElement",
  "IfcFlowTerminal", "IfcFlowStorageDevice", "IfcFlowMovingDevice",
  "IfcFlowTreatmentDevice", "IfcEnergyConversionDevice",
];

// Categories matched by IFC entity type.
const CATEGORY_IFC_CLASSES: Record<string, string[]> = {
  walls:     ["IfcWall", "IfcWallStandardCase"],
  floors:    ["IfcSlab"],
  columns:   ["IfcColumn"],
  beams:     ["IfcBeam"],
  doors:     ["IfcDoor"],
  windows:   ["IfcWindow"],
  pipes:     ["IfcPipeSegment", "IfcPipeFitting"],
  equipment: ["IfcFlowTerminal", "IfcFlowStorageDevice", "IfcFlowMovingDevice"],
  // Catches IfcRoof entities (e.g. reactor containment domes) in addition to
  // the name-pattern path that handles IfcSlab "Roof Slab" elements below.
  roofs:     ["IfcRoof"],
};

// Categories matched by IFC Name attribute regex instead of entity type.
// value: regex tested against Name; categories: optional entity-type filter.
const CATEGORY_NAME_PATTERNS: Record<string, { pattern: RegExp; categories?: RegExp[] }> = {
  roofs: {
    pattern:    /^Roof Slab$/i,
    categories: [/^IfcSlab$/i],
  },
};

export default class IFCViewerEngine {
  private components: OBC.Components;
  private world: OBC.SimpleWorld<OBC.SimpleScene, OBC.SimpleCamera, OBC.SimpleRenderer>;
  private fragments: OBC.FragmentsManager;
  private hider: OBC.Hider;
  private disposed = false;
  private equipmentIdMaps = new Map<string, OBC.ModelIdMap>();
  private pipeRunIdMaps   = new Map<string, OBC.ModelIdMap>();

  constructor(private opts: ViewerOptions) {
    this.components = new OBC.Components();

    const worlds = this.components.get(OBC.Worlds);
    this.world = worlds.create<
      OBC.SimpleScene,
      OBC.SimpleCamera,
      OBC.SimpleRenderer
    >();

    this.world.scene = new OBC.SimpleScene(this.components);
    this.world.scene.setup();

    // Keep ambient low so the directional creates real surface definition
    this.world.scene.config.directionalLight.intensity = 2.5;
    this.world.scene.config.ambientLight.intensity = 0.6;

    // Fill light from the opposite side so back faces aren't pitch black
    const fill = new THREE.DirectionalLight(0xffffff, 1.2);
    fill.position.set(-5, 8, -3);
    this.world.scene.three.add(fill);

    this.world.renderer = new OBC.SimpleRenderer(this.components, opts.container);
    this.world.camera = new OBC.SimpleCamera(this.components);

    this.components.init();

    this.fragments = this.components.get(OBC.FragmentsManager);
    this.hider     = this.components.get(OBC.Hider);
  }

  // ── Init ────────────────────────────────────────────────────────────────

  async init(): Promise<void> {
    const workerUrl = await OBC.FragmentsManager.getWorker();
    this.fragments.init(workerUrl);

    // Keep culling/LOD up to date with camera movement
    this.world.camera.controls.addEventListener("update", () => {
      this.fragments.core.update();
    });

    // Fix z-fighting on newly added materials
    this.fragments.core.models.materials.list.onItemSet.add(({ value: material }: { value: THREE.Material }) => {
      if (!("isLodMaterial" in material && material.isLodMaterial)) {
        material.polygonOffset = true;
        material.polygonOffsetUnits = 1;
        material.polygonOffsetFactor = Math.random();
      }
    });

    // Wire camera and add to scene when a model loads
    this.fragments.list.onItemSet.add(({ value: model }: { value: FRAGS.FragmentsModel }) => {
      model.useCamera(this.world.camera.three);
      this.world.scene.three.add(model.object);
      this.fragments.core.update(true);
    });
  }

  // ── Load ────────────────────────────────────────────────────────────────

  async loadIfcFromUrl(
    url: string,
    onProgress?: (p: LoadProgress) => void,
  ): Promise<void> {
    const ifcLoader = this.components.get(OBC.IfcLoader);

    await ifcLoader.setup({
      autoSetWasm: false,
      wasm: {
        path: this.opts.wasmCdnPath ?? "https://unpkg.com/web-ifc@0.0.77/",
        absolute: true,
      },
    });

    onProgress?.({ stage: "downloading", progress: 0, message: "Downloading IFC file…" });

    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`IFC fetch failed: ${resp.status}`);
    const buffer = new Uint8Array(await resp.arrayBuffer());

    onProgress?.({ stage: "parsing", progress: 0, message: "Processing geometry…" });

    await ifcLoader.load(buffer, false, "model", {
      processData: {
        progressCallback: (progress: number) => {
          onProgress?.({
            stage: "parsing",
            progress: Math.round(progress * 100),
            message: `Processing geometry… ${Math.round(progress * 100)}%`,
          });
        },
      },
    });

    onProgress?.({ stage: "rendering", progress: 100, message: "Complete!" });

    // Fit camera once the model is in the scene
    this.fitToFrame();
  }

  // ── Visibility ────────────────────────────────────────────────────────────

  async setCategoryVisible(category: string, visible: boolean): Promise<void> {
    // Name-based categories (e.g. roofs → IfcSlab elements named "Roof *").
    // After running the name-pattern path, fall through to the entity-type path
    // when the category also has an entry in CATEGORY_IFC_CLASSES (e.g. "roofs"
    // needs to catch both IfcSlab "Roof Slab" elements AND IfcRoof entities like
    // a reactor containment dome).
    if (category in CATEGORY_NAME_PATTERNS) {
      const { pattern, categories } = CATEGORY_NAME_PATTERNS[category];
      await this.setCategoryVisibleByName(pattern, visible, categories);
      if (!(category in CATEGORY_IFC_CLASSES)) return;
    }

    // Entity-type-based categories
    const classes = CATEGORY_IFC_CLASSES[category];
    if (!classes) {
      console.warn(`[IFCViewerEngine] Unknown category: "${category}"`);
      return;
    }

    const regexes = classes.map((c) => new RegExp(`^${c}$`, "i"));
    const modelIdMap: OBC.ModelIdMap = {};

    for (const [, model] of this.fragments.list) {
      try {
        const items = await model.getItemsOfCategories(regexes);
        const localIds = Object.values(items).flat();
        if (localIds.length > 0) {
          modelIdMap[model.modelId] = new Set(localIds as number[]);
        }
      } catch (err) {
        console.warn(`[IFCViewerEngine] getItemsOfCategories failed for "${category}":`, err);
      }
    }

    if (Object.keys(modelIdMap).length === 0) return;
    await this.hider.set(visible, modelIdMap);
  }

  // Match elements whose IFC Name attribute satisfies namePattern,
  // regardless of entity type.
  private async setCategoryVisibleByName(
    namePattern: RegExp,
    visible: boolean,
    categories?: RegExp[],
  ): Promise<void> {
    const finder = this.components.get(OBC.ItemsFinder);
    const queryKey = `__name_${namePattern.source}_${categories?.map(r => r.source).join("_") ?? ""}`;

    if (!finder.list.has(queryKey)) {
      const query: Record<string, unknown> = {
        attributes: { queries: [{ name: /^Name$/, value: namePattern }] },
      };
      if (categories) query.categories = categories;
      finder.create(queryKey, [query]);
    }

    const query = finder.list.get(queryKey);
    if (!query) return;

    let modelIdMap: OBC.ModelIdMap;
    try {
      modelIdMap = await query.test();
    } catch (err) {
      console.warn(`[IFCViewerEngine] ItemsFinder query failed for pattern "${namePattern}":`, err);
      return;
    }

    if (Object.keys(modelIdMap).length === 0) return;
    await this.hider.set(visible, modelIdMap);
  }

  async resetVisibility(): Promise<void> {
    await this.hider.set(true);
  }

  // ── Category presence ───────────────────────────────────────────────────
  // An IFC can contain anything, so the UI only shows toggles for categories
  // the loaded model actually has. Returns the subset of `categories` present.

  async enumerateCategories(categories: string[]): Promise<string[]> {
    const present: string[] = [];
    for (const category of categories) {
      if (await this.categoryHasItems(category)) present.push(category);
    }
    return present;
  }

  private async categoryHasItems(category: string): Promise<boolean> {
    // Name-pattern path (e.g. IfcSlab named "Roof Slab")
    if (category in CATEGORY_NAME_PATTERNS) {
      const { pattern, categories } = CATEGORY_NAME_PATTERNS[category];
      if (await this.nameQueryHasItems(pattern, categories)) return true;
      // fall through to the entity-type path when the category has both
    }

    const classes = CATEGORY_IFC_CLASSES[category];
    if (!classes) return false;

    const regexes = classes.map((c) => new RegExp(`^${c}$`, "i"));
    for (const [, model] of this.fragments.list) {
      try {
        const items = await model.getItemsOfCategories(regexes);
        if (Object.values(items).flat().length > 0) return true;
      } catch (err) {
        console.warn(`[IFCViewerEngine] getItemsOfCategories failed for "${category}":`, err);
      }
    }
    return false;
  }

  private async nameQueryHasItems(namePattern: RegExp, categories?: RegExp[]): Promise<boolean> {
    const finder = this.components.get(OBC.ItemsFinder);
    const queryKey = `__name_${namePattern.source}_${categories?.map(r => r.source).join("_") ?? ""}`;

    if (!finder.list.has(queryKey)) {
      const query: Record<string, unknown> = {
        attributes: { queries: [{ name: /^Name$/, value: namePattern }] },
      };
      if (categories) query.categories = categories;
      finder.create(queryKey, [query]);
    }

    const query = finder.list.get(queryKey);
    if (!query) return false;

    try {
      const modelIdMap = await query.test();
      // test() can return model keys with empty id sets when nothing matches —
      // count actual ids, not keys, or every name query reads as "present".
      return Object.values(modelIdMap).some((ids) => (ids as Set<number>).size > 0);
    } catch (err) {
      console.warn(`[IFCViewerEngine] ItemsFinder query failed for pattern "${namePattern}":`, err);
      return false;
    }
  }

  // ── Equipment enumeration / toggling ────────────────────────────────────

  async enumerateEquipment(): Promise<EquipmentItem[]> {
    this.equipmentIdMaps.clear();
    const regexes = EQUIPMENT_IFC_CLASSES.map((c) => new RegExp(`^${c}$`, "i"));
    const items: EquipmentItem[] = [];

    for (const [, model] of this.fragments.list) {
      let byCategory: { [category: string]: number[] };
      try {
        byCategory = await model.getItemsOfCategories(regexes);
      } catch (err) {
        console.warn(`[IFCViewerEngine] getItemsOfCategories failed:`, err);
        continue;
      }

      const localIds = Object.values(byCategory).flat();
      if (localIds.length === 0) continue;

      let dataList: FRAGS.ItemData[] = [];
      try {
        dataList = await model.getItemsData(localIds, {
          attributes: ["Name"],
          attributesDefault: false,
          relationsDefault: { attributes: false, relations: false },
        });
      } catch (err) {
        console.warn(`[IFCViewerEngine] getItemsData failed:`, err);
      }

      for (let i = 0; i < localIds.length; i++) {
        const localId = localIds[i];
        const nameAttr = dataList[i]?.Name as { value?: unknown } | undefined;
        const rawName = nameAttr && typeof nameAttr === "object" && "value" in nameAttr
          ? nameAttr.value
          : undefined;
        const label = (typeof rawName === "string" && rawName.length > 0)
          ? rawName
          : `#${localId}`;
        const key = `${model.modelId}:${localId}`;
        this.equipmentIdMaps.set(key, { [model.modelId]: new Set([localId]) });
        items.push({ key, label });
      }
    }

    items.sort((a, b) => a.label.localeCompare(b.label, undefined, { numeric: true }));
    return items;
  }

  async setEquipmentVisible(key: string, visible: boolean): Promise<void> {
    const idMap = this.equipmentIdMaps.get(key);
    if (!idMap) return;
    await this.hider.set(visible, idMap);
  }

  // ── Pipe enumeration / toggling ─────────────────────────────────────────
  // The backend doesn't currently author IfcDistributionSystem groupings, so
  // we list each segment / fitting individually rather than per logical run.

  async enumeratePipes(): Promise<PipeItem[]> {
    this.pipeRunIdMaps.clear();
    const regexes = PIPE_MEMBER_IFC_CLASSES.map((c) => new RegExp(`^${c}$`, "i"));
    const items: PipeItem[] = [];

    for (const [, model] of this.fragments.list) {
      let byCategory: { [category: string]: number[] };
      try {
        byCategory = await model.getItemsOfCategories(regexes);
      } catch (err) {
        console.warn(`[IFCViewerEngine] getItemsOfCategories(pipes) failed:`, err);
        continue;
      }

      const localIds = Object.values(byCategory).flat();
      if (localIds.length === 0) continue;

      let dataList: FRAGS.ItemData[] = [];
      try {
        dataList = await model.getItemsData(localIds, {
          attributes: ["Name"],
          attributesDefault: false,
          relationsDefault: { attributes: false, relations: false },
        });
      } catch (err) {
        console.warn(`[IFCViewerEngine] getItemsData(pipes) failed:`, err);
      }

      for (let i = 0; i < localIds.length; i++) {
        const localId = localIds[i];
        const nameAttr = dataList[i]?.Name as { value?: unknown } | undefined;
        const rawName = nameAttr && "value" in nameAttr ? nameAttr.value : undefined;
        const label = (typeof rawName === "string" && rawName.length > 0)
          ? rawName
          : `#${localId}`;
        const key = `${model.modelId}:${localId}`;
        this.pipeRunIdMaps.set(key, { [model.modelId]: new Set([localId]) });
        items.push({ key, label });
      }
    }

    items.sort((a, b) => a.label.localeCompare(b.label, undefined, { numeric: true }));
    return items;
  }

  async setPipeVisible(key: string, visible: boolean): Promise<void> {
    const idMap = this.pipeRunIdMaps.get(key);
    if (!idMap) return;
    await this.hider.set(visible, idMap);
  }

  // ── Camera ──────────────────────────────────────────────────────────────

  fitToFrame(): void {
    const bbox = new THREE.Box3();
    this.fragments.list.forEach((model: FRAGS.FragmentsModel) => {
      if (model.box) bbox.union(model.box);
    });
    if (bbox.isEmpty()) return;

    const center = bbox.getCenter(new THREE.Vector3());
    const size   = bbox.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);
    const cam    = this.world.camera.three as THREE.PerspectiveCamera;
    const fov    = cam.fov * (Math.PI / 180);
    const dist   = (maxDim / (2 * Math.tan(fov / 2))) * 1.5;

    this.world.camera.controls.setLookAt(
      center.x + dist, center.y + dist, center.z + dist,
      center.x, center.y, center.z,
    );
  }

  resetCamera(): void { this.fitToFrame(); }

  setTopView(): void {
    const controls = this.world.camera.controls;
    const target   = controls.getTarget(new THREE.Vector3());
    const dist     = controls.distance;
    controls.setLookAt(target.x, target.y + dist, target.z, target.x, target.y, target.z, true);
  }

  setFrontView(): void {
    const controls = this.world.camera.controls;
    const target   = controls.getTarget(new THREE.Vector3());
    const dist     = controls.distance;
    controls.setLookAt(target.x, target.y, target.z + dist, target.x, target.y, target.z, true);
  }

  setSideView(): void {
    const controls = this.world.camera.controls;
    const target   = controls.getTarget(new THREE.Vector3());
    const dist     = controls.distance;
    controls.setLookAt(target.x + dist, target.y, target.z, target.x, target.y, target.z, true);
  }

  setIsometricView(): void {
    const controls = this.world.camera.controls;
    const target   = controls.getTarget(new THREE.Vector3());
    const dist     = controls.distance;
    const off      = dist / Math.sqrt(3);
    controls.setLookAt(
      target.x + off, target.y + off, target.z + off,
      target.x, target.y, target.z,
      true,
    );
  }

  // ── Lifecycle ─────────────────────────────────────────────────────────────

  resize(): void {
    const el = this.opts.container;
    const w  = el.clientWidth;
    const h  = el.clientHeight;
    if (!w || !h) return;

    this.world.renderer?.resize(new THREE.Vector2(w, h));
    const cam = this.world.camera.three as THREE.PerspectiveCamera;
    cam.aspect = w / h;
    cam.updateProjectionMatrix();
    this.world.update();
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    try {
      this.components.dispose();
    } catch (e) {
      console.error("[IFCViewerEngine] Dispose error:", e);
    }
  }
}
