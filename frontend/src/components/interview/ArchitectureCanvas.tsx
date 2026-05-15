"use client";

import { useCallback, useState } from "react";
import ReactFlow, {
  addEdge,
  Background,
  Controls,
  MarkerType,
  type Connection,
  type Edge,
  type Node,
  type NodeTypes,
  useEdgesState,
  useNodesState,
  BackgroundVariant,
  Panel,
} from "reactflow";
import "reactflow/dist/style.css";

// ── Node types ────────────────────────────────────────────────────────────────

const COMPONENTS = [
  { type: "client",    label: "Client",          icon: "💻", color: "#3b82f6" },
  { type: "dns",       label: "DNS",             icon: "🌍", color: "#8b5cf6" },
  { type: "cdn",       label: "CDN",             icon: "⚡", color: "#f59e0b" },
  { type: "lb",        label: "Load Balancer",   icon: "⚖️",  color: "#10b981" },
  { type: "gateway",   label: "API Gateway",     icon: "🚪", color: "#06b6d4" },
  { type: "service",   label: "Service",         icon: "⚙️",  color: "#6366f1" },
  { type: "cache",     label: "Cache",           icon: "🗂️", color: "#f43f5e" },
  { type: "queue",     label: "Message Queue",   icon: "📨", color: "#ec4899" },
  { type: "sqldb",     label: "SQL DB",          icon: "🗄️", color: "#0ea5e9" },
  { type: "nosqldb",   label: "NoSQL DB",        icon: "📦", color: "#84cc16" },
  { type: "storage",   label: "Object Storage",  icon: "🪣", color: "#78716c" },
  { type: "search",    label: "Search",          icon: "🔍", color: "#f97316" },
  { type: "worker",    label: "Worker",          icon: "🔧", color: "#a78bfa" },
];

const COMPONENT_META = Object.fromEntries(COMPONENTS.map((c) => [c.type, c]));

function ArchNode({ data }: { data: { label: string; type: string; nodeColor: string } }) {
  const meta = COMPONENT_META[data.type] ?? { icon: "📦", color: "#71717a" };
  return (
    <div
      className="flex flex-col items-center gap-1 rounded-xl border px-3 py-2 text-center shadow-sm select-none"
      style={{
        borderColor: meta.color + "40",
        backgroundColor: meta.color + "15",
        minWidth: 88,
        maxWidth: 112,
      }}
    >
      <span className="text-xl leading-none">{meta.icon}</span>
      <span className="text-[10px] font-medium text-[#e8e8e8] leading-tight">{data.label}</span>
    </div>
  );
}

const nodeTypes: NodeTypes = { arch: ArchNode };

let nodeIdCounter = 100;

// ── Canvas ────────────────────────────────────────────────────────────────────

export default function ArchitectureCanvas() {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedType, setSelectedType] = useState<string>("service");

  const addNode = useCallback(
    (type: string) => {
      const meta = COMPONENT_META[type];
      const id = `node-${++nodeIdCounter}`;
      const newNode: Node = {
        id,
        type: "arch",
        position: { x: 80 + Math.random() * 300, y: 80 + Math.random() * 200 },
        data: { label: meta.label, type, nodeColor: meta.color },
      };
      setNodes((nds) => [...nds, newNode]);
    },
    [setNodes]
  );

  const onConnect = useCallback(
    (params: Connection) =>
      setEdges((eds) =>
        addEdge(
          {
            ...params,
            animated: true,
            style: { stroke: "#3f3f46", strokeWidth: 2 },
            markerEnd: { type: MarkerType.ArrowClosed, color: "#3f3f46" },
          },
          eds
        )
      ),
    [setEdges]
  );

  const deleteSelected = useCallback(() => {
    setNodes((nds) => nds.filter((n) => !n.selected));
    setEdges((eds) => eds.filter((e) => !e.selected));
  }, [setNodes, setEdges]);

  // Delete key handler
  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Delete" || e.key === "Backspace") deleteSelected();
    },
    [deleteSelected]
  );

  return (
    <div className="flex h-full w-full flex-col" onKeyDown={onKeyDown} tabIndex={0}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        nodeTypes={nodeTypes}
        fitView
        deleteKeyCode={["Delete", "Backspace"]}
        className="flex-1"
        style={{ background: "#0d0d0f" }}
      >
        <Background variant={BackgroundVariant.Dots} color="#27272a" gap={24} size={1} />
        <Controls
          className="!bg-[#111113] !border-[#27272a] !rounded-lg overflow-hidden"
          style={{ filter: "invert(0.9) hue-rotate(180deg)" }}
        />

        {/* Sidebar panel */}
        <Panel position="top-left">
          <div className="rounded-xl border border-[#27272a] bg-[#111113]/95 backdrop-blur-sm p-3 w-[140px]">
            <p className="mb-2 text-[10px] font-medium uppercase tracking-widest text-[#52525b]">
              Components
            </p>
            <div className="space-y-1">
              {COMPONENTS.map((comp) => (
                <button
                  key={comp.type}
                  onClick={() => addNode(comp.type)}
                  className={`w-full flex items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs transition-colors ${
                    selectedType === comp.type
                      ? "bg-[#27272a] text-[#e8e8e8]"
                      : "text-[#71717a] hover:bg-[#1c1c1e] hover:text-[#e8e8e8]"
                  }`}
                  onMouseEnter={() => setSelectedType(comp.type)}
                >
                  <span className="text-sm">{comp.icon}</span>
                  <span className="truncate">{comp.label}</span>
                </button>
              ))}
            </div>
          </div>
        </Panel>

        {/* Hint panel */}
        <Panel position="bottom-right">
          <div className="text-[10px] text-[#52525b] text-right space-y-0.5">
            <div>Click a component to add it</div>
            <div>Drag node handles to connect</div>
            <div>Select + Delete to remove</div>
          </div>
        </Panel>
      </ReactFlow>
    </div>
  );
}
