"use client";

import { Canvas, useFrame, useLoader, useThree } from "@react-three/fiber";
import { Float, OrbitControls, PerspectiveCamera, Sparkles, useGLTF } from "@react-three/drei";
import { Component, Suspense, useEffect, useMemo, useRef, useState, type CSSProperties, type ErrorInfo, type ReactNode } from "react";
import * as THREE from "three";
import { MTLLoader } from "three/examples/jsm/loaders/MTLLoader.js";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";
import gsap from "gsap";
import type { FlyPlayer } from "@/lib/types";
import type { CameraMode } from "@/lib/store";

export default function CasinoScene({ players, currentActor, lastEvent, street, board = [], pot = 0, cameraMode = "broadcast", inspectionMode = false, reducedMotion }: { players: FlyPlayer[]; currentActor: string | null; lastEvent?: string; street?: string; board?: string[]; pot?: number; cameraMode?: CameraMode; inspectionMode?: boolean; reducedMotion: boolean }) {
  const [canvasReady, setCanvasReady] = useState(false);
  const enableWebgl = process.env.NEXT_PUBLIC_ENABLE_WEBGL_SCENE !== "false";
  if (!enableWebgl) return <StaticCasinoScene players={players} currentActor={currentActor} board={board} pot={pot} />;
  return <Canvas fallback={canvasReady ? null : <StaticCasinoScene players={players} currentActor={currentActor} board={board} pot={pot} />} dpr={[1, 1.35]} gl={{ antialias: false, alpha: false }} onCreated={({ gl, scene }) => {
    setCanvasReady(true);
    gl.setClearColor("#0b0e0c", 1);
    scene.background = new THREE.Color("#0b0e0c");
    // Keep the React scene mounted across a transient driver/context reset.
    // WebGL will normally restore the context; replacing the Canvas here made
    // a momentary reset permanently downgrade the live table to CSS.
    gl.domElement.addEventListener("webglcontextlost", (event) => {
      event.preventDefault();
    });
  }} onError={(error) => console.error("Fly Poker WebGL scene error", error)}>
    <ResponsiveCamera />
    <color attach="background" args={["#0b0e0c"]} />
    <SceneBackground />
    <ambientLight intensity={1.3} color="#b7d4bd" />
    <spotLight position={[0, 8, 3]} angle={0.5} penumbra={1} intensity={120} color="#f2c56b" />
    <pointLight position={[-5, 3, 1]} intensity={30} color="#319b83" />
    <pointLight position={[5, 2, -1]} intensity={25} color="#b75546" />
    <Sparkles count={90} scale={[11, 5, 8]} size={1.2} speed={0.18} opacity={0.18} color="#d4c29c" />
    <CameraRig players={players} currentActor={currentActor} lastEvent={lastEvent} street={street} cameraMode={cameraMode} inspectionMode={inspectionMode} reducedMotion={reducedMotion} />
    <SceneErrorBoundary fallback={<ProceduralTable board={board} pot={pot} />}><Suspense fallback={<group />}><Table board={board} pot={pot} /></Suspense></SceneErrorBoundary>
    {players.map((player) => <SceneErrorBoundary key={player.id} fallback={<ProceduralFlyAvatar player={player} active={currentActor === player.id} reducedMotion={reducedMotion} />}><FlyAvatar player={player} active={currentActor === player.id} reducedMotion={reducedMotion} /></SceneErrorBoundary>)}
    <OrbitControls enablePan={false} enableZoom={false} minPolarAngle={1.03} maxPolarAngle={1.3} target={[0, 0, 0]} />
  </Canvas>;
}

function StaticCasinoScene({ players, currentActor, board, pot }: { players: FlyPlayer[]; currentActor: string | null; board: string[]; pot: number }) {
  return <div className="scene-fallback" aria-label="Static cinematic poker table fallback">
    <div className="fallback-table">
      <div className="fallback-board">{board.map((card) => <span key={card} className={card.includes("♥") || card.includes("♦") ? "red-card" : ""}>{card}</span>)}</div>
      <div className="fallback-pot">{pot.toLocaleString()} <small>CHIPS</small></div>
      {players.map((player) => <div key={player.id} className={`fallback-fly seat-${player.seat} ${currentActor === player.id ? "active" : ""}`} style={{ "--accent": player.accent } as CSSProperties}><i />{player.name}</div>)}
    </div>
  </div>;
}

function SceneBackground() {
  const { gl } = useThree();
  useFrame(() => {
    gl.setClearColor("#0b0e0c", 1);
  }, -1000);
  return null;
}

function CameraRig({ players, currentActor, lastEvent, street, cameraMode, inspectionMode, reducedMotion }: { players: FlyPlayer[]; currentActor: string | null; lastEvent?: string; street?: string; cameraMode: CameraMode; inspectionMode: boolean; reducedMotion: boolean }) {
  const { camera } = useThree();
  const focus = players.find((player) => player.id === currentActor);
  const tween = useRef<gsap.core.Tween | null>(null);

  useEffect(() => {
    if (reducedMotion || inspectionMode || cameraMode === "broadcast" && !focus && !lastEvent) return;
    const [x, , z] = focus ? seatPosition(focus.seat) : [0, 0, 0, 0];
    const event = lastEvent?.toLowerCase() ?? "";
    const dramatic = street === "showdown" || event.includes("takes the pot") || event.includes("all-in") || event.includes("claims the table") || event.includes("leaves the felt") || event.includes("raise");
    const reveal = event.includes("arrives") || event.includes("reveal");
    let destination: THREE.Vector3;
    let lookAt = new THREE.Vector3(0, 0, 0);
    if (cameraMode === "table") {
      destination = new THREE.Vector3(0, 10.4, 5.8);
    } else if (cameraMode === "macro" && focus) {
      destination = new THREE.Vector3(x * 0.42, 4.0, z + 3.65);
      lookAt = new THREE.Vector3(x, 0.35, z);
    } else {
      destination = new THREE.Vector3(dramatic ? 0 : x * (reveal ? 0.35 : 0.55), dramatic ? 7.4 : reveal ? 7.0 : 6.6, dramatic ? 9.8 : reveal ? 9.15 : 8.4 + z * 0.18);
    }
    tween.current?.kill();
    tween.current = gsap.to(camera.position, {
      x: destination.x,
      y: destination.y,
      z: destination.z,
      duration: reducedMotion ? 0 : dramatic ? 1.05 : 0.8,
      ease: dramatic ? "power3.inOut" : "power2.out",
      overwrite: true,
      onUpdate: () => camera.lookAt(lookAt),
    });
    return () => {
      tween.current?.kill();
    };
  }, [camera, cameraMode, currentActor, focus, inspectionMode, lastEvent, reducedMotion, street]);

  useEffect(() => () => {
    tween.current?.kill();
  }, []);

  useFrame(({ clock }) => {
    // Inspection mode is intentionally steady: the spectator can study one
    // fly without an event-driven cut moving the camera underneath them.
    if (reducedMotion || inspectionMode) return;
    const event = lastEvent?.toLowerCase() ?? "";
    if (cameraMode === "table" || cameraMode === "macro") return;
    if (event.includes("claims the table")) {
      const angle = clock.elapsedTime * 0.16;
      const orbit = new THREE.Vector3(Math.sin(angle) * 9.2, 7.4, Math.cos(angle) * 9.2);
      camera.position.lerp(orbit, 0.035);
      camera.lookAt(0, 0, 0);
      return;
    }
  });
  return null;
}

function Table({ board, pot }: { board: string[]; pot: number }) {
  const materials = useLoader(MTLLoader, "/models/table.mtl");
  materials.preload();
  const table = useLoader(OBJLoader, "/models/table.obj", (loader) => loader.setMaterials(materials));
  const cardMaterials = useLoader(MTLLoader, "/models/card.mtl");
  cardMaterials.preload();
  const cardObject = useLoader(OBJLoader, "/models/card.obj", (loader) => loader.setMaterials(cardMaterials));
  const chipMaterials = useLoader(MTLLoader, "/models/chip_25.mtl");
  chipMaterials.preload();
  const chipObject = useLoader(OBJLoader, "/models/chip_25.obj", (loader) => loader.setMaterials(chipMaterials));
  const tableModel = useMemo(() => {
    const clone = table.clone();
    clone.traverse((child) => {
      if (!(child instanceof THREE.Mesh)) return;
      child.castShadow = true;
      child.receiveShadow = true;
      const material = child.material;
      if (material instanceof THREE.MeshStandardMaterial) {
        material.roughness = 0.76;
        material.metalness = 0.08;
      } else if (material instanceof THREE.MeshPhongMaterial) {
        material.shininess = 18;
      }
      if (material instanceof THREE.MeshPhongMaterial || material instanceof THREE.MeshStandardMaterial) {
        const materialName = `${child.name} ${(material as THREE.Material).name}`.toLowerCase();
        if (materialName.includes("cloth")) material.color.set("#174633");
        if (materialName.includes("cushion")) material.color.set("#2a1717");
        if (materialName.includes("wood")) material.color.set("#211710");
      }
    });
    return clone;
  }, [table]);
  return <group rotation={[-0.02, 0, 0]}>
    <primitive object={tableModel} position={[0, -0.52, 0]} scale={[5.4, 2.3, 3.02]} />
    <mesh receiveShadow position={[0, -0.55, 0]} rotation={[0, 0, 0]}>
      <cylinderGeometry args={[4.6, 4.8, 0.8, 64]} /><meshStandardMaterial color="#211710" roughness={0.72} metalness={0.12} />
    </mesh>
    <mesh receiveShadow position={[0, -0.05, 0]} scale={[1, 1, 0.62]}>
      <cylinderGeometry args={[4.35, 4.35, 0.12, 64]} /><meshStandardMaterial color="#174633" roughness={0.92} metalness={0.02} />
    </mesh>
    <mesh position={[0, 0.02, 0]} scale={[1, 1, 0.62]}>
      <torusGeometry args={[4.17, 0.07, 12, 64]} /><meshStandardMaterial color="#c39444" roughness={0.4} metalness={0.82} emissive="#2f1d07" />
    </mesh>
    <mesh position={[0, 0.035, 0]} scale={[1, 1, 0.62]}>
      <torusGeometry args={[2.25, 0.015, 8, 64]} /><meshStandardMaterial color="#3b7057" roughness={0.9} />
    </mesh>
    <mesh position={[0, 0.05, 0]} rotation={[0, 0, 0]}>
      <boxGeometry args={[0.9, 0.015, 0.47]} /><meshStandardMaterial color="#d5b25e" roughness={0.55} metalness={0.7} />
    </mesh>
    <mesh position={[0, 0.055, 0]}>
      <boxGeometry args={[0.05, 0.02, 0.7]} /><meshStandardMaterial color="#1b251d" />
    </mesh>
    <group position={[0, 0.12, -0.12]}>
      {board.map((card, index) => <group key={`${card}-${index}`} position={[(index - (board.length - 1) / 2) * 0.56, 0, 0]} rotation={[0, 0, (index % 2 ? -1 : 1) * 0.035]}>
        <RealCard object={cardObject} />
      </group>)}
    </group>
    <group position={[1.02, 0.13, 0.05]}>
      {Array.from({ length: Math.min(5, Math.max(1, Math.ceil(pot / 250))) }, (_, index) => <RealChip key={index} object={chipObject} position={[0, index * 0.06, 0]} />)}
    </group>
  </group>;
}

class SceneErrorBoundary extends Component<{ children: ReactNode; fallback: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error("Fly Poker scene asset failed", error, info.componentStack); }
  render() { return this.state.failed ? this.props.fallback : this.props.children; }
}

function ProceduralTable({ board, pot }: { board: string[]; pot: number }) {
  return <group>
    <mesh receiveShadow position={[0, -0.48, 0]} scale={[1, 1, 0.62]}><cylinderGeometry args={[4.55, 4.8, 0.82, 64]} /><meshStandardMaterial color="#211710" roughness={0.74} metalness={0.12} /></mesh>
    <mesh receiveShadow position={[0, -0.04, 0]} scale={[1, 1, 0.62]}><cylinderGeometry args={[4.35, 4.35, 0.12, 64]} /><meshStandardMaterial color="#174633" roughness={0.92} /></mesh>
    <mesh position={[0, 0.02, 0]} scale={[1, 1, 0.62]}><torusGeometry args={[4.17, 0.07, 12, 64]} /><meshStandardMaterial color="#c39444" roughness={0.4} metalness={0.82} /></mesh>
    <group position={[0, 0.12, -0.12]}>{board.map((card, index) => <RealCardFallback key={`${card}-${index}`} card={card} position={[(index - (board.length - 1) / 2) * 0.56, 0, 0]} />)}</group>
    <group position={[1.02, 0.13, 0.05]}>{Array.from({ length: Math.min(5, Math.max(1, Math.ceil(pot / 250))) }, (_, index) => <mesh key={index} position={[0, index * 0.06, 0]} rotation={[Math.PI / 2, 0, 0]}><cylinderGeometry args={[0.12, 0.12, 0.035, 24]} /><meshStandardMaterial color={index % 2 ? "#e9e2d1" : "#c94e45"} roughness={0.45} metalness={0.3} /></mesh>)}</group>
  </group>;
}

function RealCardFallback({ card, position }: { card: string; position: [number, number, number] }) {
  return <group position={position}><mesh rotation={[0.03, 0.16, 0.08]}><boxGeometry args={[0.42, 0.04, 0.62]} /><meshStandardMaterial color="#e9e2d1" roughness={0.72} /></mesh><mesh position={[0, 0.025, 0]} rotation={[-Math.PI / 2, 0, 0]}><planeGeometry args={[0.22, 0.22]} /><meshBasicMaterial color={card.includes("♥") || card.includes("♦") ? "#a8443c" : "#17231b"} /></mesh></group>;
}

function ResponsiveCamera() {
  const { size } = useThree();
  return <PerspectiveCamera makeDefault position={[0, 8.4, 10.5]} fov={size.width < 600 ? 58 : 33} />;
}

function RealCard({ object }: { object: THREE.Group }) {
  const instance = useMemo(() => object.clone(), [object]);
  return <primitive object={instance} scale={[0.098, 0.014, 0.071]} rotation={[0, 0, 0.09]} position={[0, 0.018, 0]} />;
}

function RealChip({ object, position }: { object: THREE.Group; position: [number, number, number] }) {
  const instance = useMemo(() => object.clone(), [object]);
  return <primitive object={instance} position={position} scale={[0.064, 0.07, 0.064]} rotation={[Math.PI / 2, 0, 0]} />;
}

function FlyAvatar({ player, active, reducedMotion }: { player: FlyPlayer; active: boolean; reducedMotion: boolean }) {
  const gltfUrl = process.env.NEXT_PUBLIC_FLY_GLTF_URL || "/models/spyfly.glb";
  if (gltfUrl) return <GltfFlyAvatar url={gltfUrl} player={player} active={active} reducedMotion={reducedMotion} />;
  return <ProceduralFlyAvatar player={player} active={active} reducedMotion={reducedMotion} />;
}

function GltfFlyAvatar({ url, player, active, reducedMotion }: { url: string; player: FlyPlayer; active: boolean; reducedMotion: boolean }) {
  const { scene } = useGLTF(url, true);
  const instance = useMemo(() => {
    const clone = scene.clone();
    clone.traverse((child) => {
      if (!(child instanceof THREE.Mesh)) return;
      const sourceMaterials = Array.isArray(child.material) ? child.material : [child.material];
      child.material = sourceMaterials.map((source) => {
        const material = source.clone();
        if (material instanceof THREE.MeshStandardMaterial || material instanceof THREE.MeshPhongMaterial) {
          material.color.set("#3b352c");
          material.emissive.set(player.accent);
          material.emissiveIntensity = 0.08;
          if (material instanceof THREE.MeshStandardMaterial) {
            material.roughness = 0.62;
            material.metalness = 0.12;
          } else {
            material.shininess = 26;
          }
        }
        return material;
      });
      child.castShadow = true;
      child.receiveShadow = true;
    });
    return clone;
  }, [player.accent, scene]);
  const fit = useMemo(() => {
    const bounds = new THREE.Box3().setFromObject(scene);
    const size = bounds.getSize(new THREE.Vector3());
    const center = bounds.getCenter(new THREE.Vector3());
    // The source fly is authored in millimetres and reads too small at the
    // table's establishing-shot scale. Normalize it to a clearly visible
    // insect silhouette while preserving its original proportions.
    const targetWidth = 2.1;
    const scale = targetWidth / Math.max(0.001, size.x, size.z);
    return { scale, offset: new THREE.Vector3(-center.x, -bounds.min.y, -center.z) };
  }, [scene]);
  const group = useRef<THREE.Group>(null);
  const seat = seatPosition(player.seat);
  useFrame(({ clock }) => {
    if (!group.current || reducedMotion) return;
    const pulse = active ? Math.sin(clock.elapsedTime * 5.6) * 0.045 : Math.sin(clock.elapsedTime * 1.6 + player.seat) * 0.012;
    group.current.position.y = seat[1] + pulse;
    group.current.rotation.y = seat[3] + Math.sin(clock.elapsedTime * 0.4 + player.seat) * 0.04;
  });
  return <group ref={group} position={[seat[0], seat[1], seat[2]]} rotation={[0, seat[3], 0]} scale={fit.scale * (active ? 1.08 : 1)}>
    <primitive object={instance} position={[fit.offset.x, fit.offset.y, fit.offset.z]} />
    <InsectCardHands player={player} active={active} reducedMotion={reducedMotion} />
    <pointLight position={[0.5, 0.45, 0]} color={player.accent} intensity={active ? 0.8 : 0.18 + player.activity * 0.5} distance={1.4} />
  </group>;
}

function ProceduralFlyAvatar({ player, active, reducedMotion }: { player: FlyPlayer; active: boolean; reducedMotion: boolean }) {
  const group = useRef<THREE.Group>(null);
  const seat = seatPosition(player.seat);
  const [seatX, seatY, seatZ, seatRotation] = seat;
  useFrame(({ clock }) => {
    if (!group.current || reducedMotion) return;
    const pulse = active ? Math.sin(clock.elapsedTime * 5.6) * 0.045 : Math.sin(clock.elapsedTime * 1.6 + player.seat) * 0.012;
    group.current.position.y = seatY + pulse;
    group.current.rotation.y = Math.sin(clock.elapsedTime * 0.4 + player.seat) * 0.04;
    // Small insect-scale tells keep the characters readable without adding
    // humanoid gestures or costume-like animation.
    const phase = clock.elapsedTime;
    if (player.id === "vesper") group.current.rotation.z = Math.sin(phase * 1.8) * 0.035;
    if (player.id === "sugar") group.current.rotation.z = Math.sin(phase * 12) * 0.018;
    if (player.id === "knuckles") group.current.position.x = seatX + Math.sin(phase * 5.4) * 0.012;
    if (player.id === "velvet") group.current.rotation.x = Math.sin(phase * 0.75) * 0.022;
    if (player.id === "static") group.current.rotation.z = Math.sin(phase * 18) * 0.012;
    if (player.id === "hex") group.current.rotation.z = 0;
  });
  return <group ref={group} position={[seatX, seatY, seatZ]} rotation={[0, seatRotation, 0]}>
    <Float speed={active ? 2.1 : 0.8} rotationIntensity={active ? 0.16 : 0.025} floatIntensity={active ? 0.16 : 0.04} enabled={!reducedMotion}>
      <group scale={active ? 1.08 : 1}>
        <mesh castShadow position={[0, 0.36, 0]} scale={[0.5, 0.25, 0.24]}><sphereGeometry args={[1, 24, 16]} /><meshStandardMaterial color="#191d19" roughness={0.46} metalness={0.46} /></mesh>
        <mesh castShadow position={[0.36, 0.39, 0]} scale={[0.28, 0.2, 0.19]}><sphereGeometry args={[1, 22, 14]} /><meshStandardMaterial color="#252923" roughness={0.42} metalness={0.42} /></mesh>
        <mesh castShadow position={[-0.45, 0.3, 0]} scale={[0.34, 0.16, 0.17]}><sphereGeometry args={[1, 20, 14]} /><meshStandardMaterial color="#111511" roughness={0.5} metalness={0.35} /></mesh>
        <mesh position={[-0.4, 0.33, 0.16]} rotation={[0, 0.2, 0]}><torusGeometry args={[0.12, 0.018, 8, 20, Math.PI * (0.55 + (player.seat % 3) * 0.12)]} /><meshStandardMaterial color={player.accent} roughness={0.52} metalness={0.3} /></mesh>
        <IdentifierMark id={player.id} accent={player.accent} />
        <InsectLegs accent={player.accent} />
        <InsectCardHands player={player} active={active} reducedMotion={reducedMotion} />
        <mesh position={[0.43, 0.43, 0.16]}><sphereGeometry args={[0.045, 12, 8]} /><meshBasicMaterial color={player.accent} /></mesh>
        <mesh position={[0.43, 0.43, -0.16]}><sphereGeometry args={[0.045, 12, 8]} /><meshBasicMaterial color={player.accent} /></mesh>
        <mesh position={[-0.07, 0.5, 0.2]} rotation={[0.1, 0.15, 0.15]}><planeGeometry args={[0.72, 0.27]} /><meshPhysicalMaterial color="#9ee8d3" transparent opacity={0.19} roughness={0.25} transmission={0.1} side={THREE.DoubleSide} /></mesh>
        <mesh position={[-0.07, 0.5, -0.2]} rotation={[-0.1, 0.15, -0.15]}><planeGeometry args={[0.72, 0.27]} /><meshPhysicalMaterial color="#9ee8d3" transparent opacity={0.15} roughness={0.25} transmission={0.1} side={THREE.DoubleSide} /></mesh>
        <mesh position={[0.56, 0.51, 0.12]} rotation={[0, 0, -0.46]}><cylinderGeometry args={[0.012, 0.012, 0.3, 8]} /><meshStandardMaterial color={player.accent} /></mesh>
        <mesh position={[0.56, 0.51, -0.12]} rotation={[0, 0, -0.46]}><cylinderGeometry args={[0.012, 0.012, 0.3, 8]} /><meshStandardMaterial color={player.accent} /></mesh>
        <pointLight position={[0.5, 0.45, 0]} color={player.accent} intensity={active ? 0.8 : 0.18 + player.activity * 0.5} distance={1.4} />
      </group>
    </Float>
  </group>;
}

function IdentifierMark({ id, accent }: { id: string; accent: string }) {
  if (id === "vesper") return <mesh position={[-0.25, 0.37, 0.2]} scale={[0.12, 0.045, 0.025]}><sphereGeometry args={[1, 12, 8]} /><meshBasicMaterial color={accent} /></mesh>;
  if (id === "sugar") return <mesh position={[-0.18, 0.13, 0.18]} rotation={[Math.PI / 2, 0, 0]}><torusGeometry args={[0.08, 0.014, 8, 16]} /><meshBasicMaterial color={accent} /></mesh>;
  if (id === "knuckles") return <mesh position={[-0.34, 0.52, 0.2]} rotation={[0, 0.2, 0.05]}><boxGeometry args={[0.14, 0.012, 0.035]} /><meshBasicMaterial color="#0b0e0c" /></mesh>;
  if (id === "velvet") return <mesh position={[-0.55, 0.16, 0.03]} rotation={[0.1, 0.25, 0.1]}><cylinderGeometry args={[0.006, 0.006, 0.55, 6]} /><meshBasicMaterial color="#e8d6b4" transparent opacity={0.58} /></mesh>;
  if (id === "static") return <Sparkles count={10} scale={[0.72, 0.4, 0.42]} size={0.45} speed={0.12} opacity={0.42} color={accent} />;
  return <group><mesh position={[0.47, 0.45, 0.17]}><sphereGeometry args={[0.012, 8, 6]} /><meshBasicMaterial color="#fff8d8" /></mesh><mesh position={[0.47, 0.45, -0.17]}><sphereGeometry args={[0.012, 8, 6]} /><meshBasicMaterial color="#fff8d8" /></mesh></group>;
}

function InsectLegs({ accent }: { accent: string }) {
  const legs = [-1, 1].flatMap((side) => [0, 1, 2].map((index) => ({ side, index })));
  return <group position={[-0.08, 0.19, 0]}>
    {legs.map(({ side, index }) => {
      const z = (index - 1) * 0.13;
      const x = -0.15 + index * 0.1;
      const angle = side * (0.62 + index * 0.13);
      return <group key={`${side}-${index}`} position={[x, 0, z]} rotation={[0, side * 0.18, angle]}>
        <mesh castShadow><cylinderGeometry args={[0.018, 0.014, 0.38, 7]} /><meshStandardMaterial color="#343b32" roughness={0.7} /></mesh>
        <mesh castShadow position={[0, -0.22, 0]}><cylinderGeometry args={[0.012, 0.008, 0.22, 7]} /><meshStandardMaterial color={accent} roughness={0.55} /></mesh>
      </group>;
    })}
  </group>;
}

/**
 * The “hands” are still insect forelegs: two jointed tibia/tarsi pairs with
 * tiny hooked tips. They reach for the cards/chips on action beats, so the
 * player reads as a fly manipulating a table without ever becoming humanoid.
 */
function InsectCardHands({ player, active, reducedMotion }: { player: FlyPlayer; active: boolean; reducedMotion: boolean }) {
  const left = useRef<THREE.Group>(null);
  const right = useRef<THREE.Group>(null);
  const cards = useRef<THREE.Group>(null);
  const action = player.status.toLowerCase();
  const reaching = active || action.includes("raise") || action.includes("call") || action.includes("check") || action.includes("all-in");
  useFrame(({ clock }) => {
    const phase = reducedMotion ? 0 : clock.elapsedTime;
    const reach = reaching ? 1 : 0;
    const wave = reducedMotion ? 0 : Math.sin(phase * (reaching ? 5.2 : 1.4)) * (reaching ? 0.08 : 0.025);
    if (left.current) {
      left.current.rotation.z = THREE.MathUtils.lerp(left.current.rotation.z, -0.6 - reach * 0.6 + wave, 0.14);
      left.current.rotation.x = THREE.MathUtils.lerp(left.current.rotation.x, 0.18 + reach * 0.45, 0.14);
    }
    if (right.current) {
      right.current.rotation.z = THREE.MathUtils.lerp(right.current.rotation.z, 0.6 + reach * 0.6 - wave, 0.14);
      right.current.rotation.x = THREE.MathUtils.lerp(right.current.rotation.x, 0.18 + reach * 0.45, 0.14);
    }
    if (cards.current) {
      // A reaching beat slides the held pair toward the felt, then returns
      // them to the fly's mouth-side resting position.
      cards.current.position.x = THREE.MathUtils.lerp(cards.current.position.x, 0.44 + reach * 0.34, 0.12);
      cards.current.position.y = THREE.MathUtils.lerp(cards.current.position.y, 0.18 - reach * 0.08, 0.12);
      cards.current.rotation.y = THREE.MathUtils.lerp(cards.current.rotation.y, reach * 0.22, 0.12);
    }
  });
  const cardMaterial = <meshStandardMaterial color="#e9e2d1" roughness={0.72} />;
  return <group position={[0.42, 0.18, 0]}>
    <group ref={left} position={[0.02, 0.04, 0.14]}>
      <mesh castShadow position={[0.11, 0.02, 0]} rotation={[0, 0, -0.2]}><cylinderGeometry args={[0.018, 0.013, 0.22, 7]} /><meshStandardMaterial color="#424a3e" roughness={0.68} /></mesh>
      <mesh castShadow position={[0.23, -0.06, 0]} rotation={[0, 0, 0.9]}><cylinderGeometry args={[0.013, 0.009, 0.18, 7]} /><meshStandardMaterial color={player.accent} roughness={0.56} /></mesh>
      <mesh position={[0.31, -0.13, 0]} rotation={[0, 0, 0.55]}><torusGeometry args={[0.027, 0.008, 6, 10, Math.PI * 1.3]} /><meshStandardMaterial color={player.accent} metalness={0.25} /></mesh>
    </group>
    <group ref={right} position={[0.02, 0.04, -0.14]}>
      <mesh castShadow position={[0.11, 0.02, 0]} rotation={[0, 0, 0.2]}><cylinderGeometry args={[0.018, 0.013, 0.22, 7]} /><meshStandardMaterial color="#424a3e" roughness={0.68} /></mesh>
      <mesh castShadow position={[0.23, -0.06, 0]} rotation={[0, 0, -0.9]}><cylinderGeometry args={[0.013, 0.009, 0.18, 7]} /><meshStandardMaterial color={player.accent} roughness={0.56} /></mesh>
      <mesh position={[0.31, -0.13, 0]} rotation={[0, 0, -0.55]}><torusGeometry args={[0.027, 0.008, 6, 10, Math.PI * 1.3]} /><meshStandardMaterial color={player.accent} metalness={0.25} /></mesh>
    </group>
    <group ref={cards} position={[0.44, 0.18, 0]} rotation={[0, 0, 0.08]}>
      <mesh castShadow position={[0, 0, 0.055]} rotation={[0.03, 0.16, 0.08]}><boxGeometry args={[0.22, 0.025, 0.32]} />{cardMaterial}</mesh>
      <mesh castShadow position={[0.02, 0.008, -0.055]} rotation={[-0.02, 0.16, -0.06]}><boxGeometry args={[0.22, 0.025, 0.32]} />{cardMaterial}</mesh>
    </group>
  </group>;
}

function seatPosition(seat: number): [number, number, number, number] {
  const positions: [number, number, number, number][] = [
    [-3.35, 0, -1.95, 0.46], [-1.25, 0, -3.0, 0.08], [1.25, 0, -3.0, -0.08], [3.35, 0, -1.95, -0.46], [2.95, 0, 1.62, -2.46], [-2.95, 0, 1.62, 2.46],
  ];
  return positions[seat] ?? positions[0];
}
