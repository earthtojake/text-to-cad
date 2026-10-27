// Render the published GLB and its baked clip through the same native paths as the docs hero.
import * as THREE from "three";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { LineSegments2 } from "three/examples/jsm/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/examples/jsm/lines/LineSegmentsGeometry.js";
import { renderModel } from "@text-to-cad/core/common/renderModel.js";
import { cloneThemePresetSettings } from "@text-to-cad/core/common/themeSettings.js";
import {
  createGlbAnimationRuntime,
  disposeGlbAnimationRuntime,
  setGlbAnimationTime,
} from "@text-to-cad/core/lib/render/glbAnimationRuntime.js";
import { buildGlbDocumentFromBuffer, disposeGlbDocument } from "@text-to-cad/core/lib/render/glbMeshData.js";
import { VIEWER_SCENE_SCALE } from "@text-to-cad/core/lib/viewer/sceneScale.js";

const EDGE_CREASE_DEG = 35;
const EDGE_OPACITY = 0.84;
// The outline around each part: its back faces pushed out along their normals by this share of
// the model's radius, in the edge colour, behind the part.
const SILHOUETTE_SCALE = 0.004;
const SILHOUETTE_OPACITY = 0.9;

type PreviewScheme = "dark" | "light";
type HeroGlbDocument = Awaited<ReturnType<typeof buildGlbDocumentFromBuffer>>;

const GLB_PREVIEW_PALETTES = {
  dark: {
    background: "#292929",
    border: "#414141",
    edge: "#202b38",
    headerBackground: "#303030",
    headerText: "#d4d4d4",
    keyLight: "#f6f8fb",
    keyLightIntensity: 2.5,
    fillLight: "#7f95ad",
    fillLightIntensity: 0.8,
    ambientLight: "#eef4fa",
    ambientLightIntensity: 1.85,
  },
  light: {
    background: "#fafafa",
    border: "#e5e5e5",
    edge: "#2f3a4b",
    headerBackground: "#ffffff",
    headerText: "#737373",
    keyLight: "#ffffff",
    keyLightIntensity: 2.6,
    fillLight: "#cfd8e3",
    fillLightIntensity: 0.9,
    ambientLight: "#ffffff",
    ambientLightIntensity: 2.2,
  },
} as const;

// The viewport's lighting and backdrop: the workbench theme, lit for this page.
function buildWorkbenchTheme(scheme: PreviewScheme) {
  const palette = GLB_PREVIEW_PALETTES[scheme];
  const theme = cloneThemePresetSettings("workbench-light");

  return {
    ...theme,
    background: {
      type: "solid",
      solidColor: palette.background,
    },
    lighting: {
      ambient: {
        color: palette.ambientLight,
        enabled: true,
        intensity: palette.ambientLightIntensity,
      },
      directionalLights: [
        {
          color: palette.keyLight,
          enabled: true,
          intensity: palette.keyLightIntensity,
          position: { x: -120, y: 180, z: 240 },
        },
        {
          color: palette.fillLight,
          enabled: true,
          intensity: palette.fillLightIntensity,
          position: { x: 180, y: -120, z: 120 },
        },
      ],
      hemisphere: {
        enabled: false,
      },
    },
  };
}

// An outline material: back faces pushed out along their normals, drawn flat behind the part.
function silhouetteMaterial(color: string, offset: number) {
  return new THREE.ShaderMaterial({
    uniforms: {
      color: { value: new THREE.Color(color) },
      opacity: { value: SILHOUETTE_OPACITY },
      offset: { value: offset },
    },
    vertexShader: `
      uniform float offset;
      void main() {
        vec3 displaced = position + normal * offset;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(displaced, 1.0);
      }
    `,
    fragmentShader: `
      uniform vec3 color;
      uniform float opacity;
      void main() {
        gl_FragColor = vec4(color, opacity);
      }
    `,
    side: THREE.BackSide,
    transparent: true,
    depthTest: true,
    depthWrite: false,
  });
}

// The GLB's scene as a model `renderModel` frames and draws: placed in CAD space (millimetres, Z
// up) by the document's own matrix, each part's colour kept on the matte workbench finish, and each
// part's folds and outline drawn in the edge colour, riding with it as the clip moves it.
function buildHeroModel(glb: HeroGlbDocument, scheme: PreviewScheme) {
  const placed = new THREE.Group();
  placed.matrix.fromArray(glb.cadRootMatrix);
  placed.matrixAutoUpdate = false;
  placed.add(glb.scene);
  const root = new THREE.Group();
  root.add(placed);

  const bounds = glb.animatedBounds ?? glb.restBounds ?? { min: [0, 0, 0], max: [1, 1, 1] };
  const radius = new THREE.Vector3(...bounds.max).sub(new THREE.Vector3(...bounds.min)).length() / 2;
  const edgeColor = GLB_PREVIEW_PALETTES[scheme].edge;
  const edgeMaterial = new LineMaterial({
    color: edgeColor,
    linewidth: 1,
    transparent: true,
    opacity: EDGE_OPACITY,
  });
  const outlineMaterial = silhouetteMaterial(edgeColor, radius * SILHOUETTE_SCALE);
  const edgeGeometries: LineSegmentsGeometry[] = [];
  const meshes: THREE.Mesh[] = [];
  glb.scene.traverse((object: THREE.Object3D) => {
    if ((object as THREE.Mesh).isMesh) {
      meshes.push(object as THREE.Mesh);
    }
  });
  for (const mesh of meshes) {
    for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
      if (material instanceof THREE.MeshStandardMaterial) {
        material.roughness = 0.92;
        material.metalness = 0;
        material.envMapIntensity = 0;
      }
    }
    const folds = new THREE.EdgesGeometry(mesh.geometry, EDGE_CREASE_DEG);
    const lines = new LineSegmentsGeometry().fromEdgesGeometry(folds);
    folds.dispose();
    edgeGeometries.push(lines);
    mesh.add(new LineSegments2(lines, edgeMaterial));
    const outline = new THREE.Mesh(mesh.geometry, outlineMaterial);
    outline.renderOrder = -1;
    mesh.add(outline);
  }

  return {
    root,
    bounds,
    runtime: {
      // Device pixels, as `renderModel` gives them on every resize.
      syncScreenSpaceLineMaterials(width: number, height: number) {
        edgeMaterial.resolution.set(width, height);
      },
    },
    dispose() {
      for (const geometry of edgeGeometries) {
        geometry.dispose();
      }
      edgeMaterial.dispose();
      outlineMaterial.dispose();
      disposeGlbDocument(glb);
    },
  };
}


const response=await fetch('/hero/planetary.glb');
if(!response.ok)throw new Error(`Planetary GLB: HTTP ${response.status}`);
const glb=await buildGlbDocumentFromBuffer(await response.arrayBuffer(),{});
const clip=glb.clips.find((candidate: THREE.AnimationClip)=>candidate.name==='meshCycle');
if(!clip)throw new Error('Planetary GLB is missing meshCycle');
const animation=createGlbAnimationRuntime(THREE,glb.scene,clip);
const theme=buildWorkbenchTheme('dark');
const model=buildHeroModel(glb,'dark');
model.root.rotation.x=0.12;model.root.rotation.z=-0.18;
const viewport=renderModel(THREE,model,{canvas:document.querySelector('canvas'),hostElement:document.querySelector('#model'),direction:[1,-1,1.05],padding:0.03,lockedHalfHeightScale:0.8,scale:VIEWER_SCENE_SCALE.CAD,theme,autoStart:false});
const svg=document.querySelector('#wordmark svg') as SVGSVGElement;
svg.pauseAnimations();
// Reveal whole typeset lines through a continuous mask, preserving kerning.
const rows = [
 {id:'byline',text:'Design physical',start:2.35,duration:0.42},
 {id:'byline',text:'products with AI.',start:2.85,duration:0.50},
 {id:'subtitle',text:'100% open source',start:3.55,duration:0.47},
 {id:'subtitle',text:'and free.',start:4.10,duration:0.32},
 {id:'site-url',text:'[[ texttocad.dev ]]',start:4.62,duration:0.60},
].map(row=>{
 const element=document.createElement('span');
 element.className='type-row';element.textContent=row.text;
 document.getElementById(row.id)!.append(element);
 return {...row,element};
});
const clamp=(v:number)=>Math.max(0,Math.min(1,v));
const ease=(v:number)=>v<0.5?2*v*v:1-Math.pow(-2*v+2,2)/2;
(window as any).renderAt=(t:number)=>{
 const caret=document.getElementById('caret')!;
 caret.style.opacity='0';
 for(const row of rows){
   const p=clamp((t-row.start)/row.duration);
   const reveal=ease(p);
   row.element.style.clipPath=`inset(0 ${(1-reveal)*100}% 0 0)`;
   if(t>=row.start && t<row.start+row.duration+0.07){
     const rect=row.element.getBoundingClientRect();
     caret.style.left=`${rect.left+rect.width*reveal+2}px`;
     const style=getComputedStyle(row.element);
     const size=parseFloat(style.fontSize);
     caret.style.top=`${rect.top+size*0.1}px`;
     caret.style.height=`${size*0.94}px`;
     caret.style.background=style.color;
     caret.style.opacity=String(Math.min(clamp((t-row.start)/0.04),clamp((row.start+row.duration+0.07-t)/0.07)));
   }
 }
 const entrance=Math.max(0,Math.min(1,(t-2.35)/0.65));
 const eased=1-Math.pow(1-entrance,3);
 const host=document.getElementById('model')!;
 host.style.opacity=String(eased);
 host.style.transform=`translateY(${(1-eased)*18}px) scale(${0.94+0.06*eased})`;
 svg.setCurrentTime(t);setGlbAnimationTime(animation,t*0.5);viewport.render();};
(window as any).renderAt(0);
(window as any).ready=true;
