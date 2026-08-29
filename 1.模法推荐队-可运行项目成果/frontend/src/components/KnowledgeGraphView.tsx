import React, { useMemo, useRef, useEffect, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import type { GraphNeighborhood, GraphNode } from '../types';

interface KnowledgeGraphViewProps {
  graph: GraphNeighborhood | null;
  modelName: string;
  loading: boolean;
  error: string | null;
  /** Optional: node ids on the demand→model match path to highlight. */
  pathNodeIds?: string[];
  /** Optional: human-readable summary of the matched path. */
  pathSummary?: string;
  /** Optional: error message when path matching fails (non-blocking). */
  pathError?: string | null;
  /** Optional: node id currently drilled into. */
  drillNode?: string | null;
  /** Optional: drilldown sub-graph data. */
  drillData?: GraphNeighborhood | null;
  /** Optional: drilldown loading state. */
  drillLoading?: boolean;
  /** Callback to drill into a node. */
  onDrillDown?: (nodeId: string) => void;
  /** Callback to reset drilldown and return to the full neighborhood. */
  onResetDrill?: () => void;
}

const NODE_COLORS: Record<string, string> = {
  model: '#3b82f6',
  scenario: '#10b981',
  stage: '#f59e0b',
  segment: '#8b5cf6',
  capability: '#ef4444',
  tag: '#6b7280',
  field: '#06b6d4',
  output: '#ec4899',
  composition: '#14b8a6',
};

const NODE_LABELS: Record<string, string> = {
  model: '模型',
  scenario: '场景',
  stage: '阶段',
  segment: '客群',
  capability: '能力',
  tag: '标签',
  field: '输入',
  output: '输出',
  composition: '组合',
};

const EDGE_LABELS: Record<string, string> = {
  applies_to: '适用于',
  belongs_to_stage: '所属阶段',
  targets_segment: '目标客群',
  has_capability: '具备能力',
  has_tag: '标签',
  requires: '需要输入',
  optional_requires: '可选输入',
  outputs: '输出',
  can_feed: '可衔接',
};

interface FGNode {
  id: string;
  name: string;
  node_type: string;
  color: string;
  val: number;
  isPath: boolean;
  x?: number;
  y?: number;
}

interface FGLink {
  source: string | FGNode;
  target: string | FGNode;
  relation_type: string;
  weight: number;
  isPath: boolean;
}

const KnowledgeGraphView: React.FC<KnowledgeGraphViewProps> = ({
  graph,
  modelName,
  loading,
  error,
  pathNodeIds,
  pathSummary,
  pathError,
  drillNode,
  drillData,
  drillLoading,
  onDrillDown,
  onResetDrill,
}) => {
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [containerSize, setContainerSize] = useState({ width: 600, height: 400 });
  const containerRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<any>(null);

  // Track container size for responsive canvas
  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        if (width > 0 && height > 0) {
          setContainerSize({ width: Math.floor(width), height: Math.floor(height) });
        }
      }
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  const graphData = useMemo<{ nodes: FGNode[]; links: FGLink[] }>(() => {
    // When drilling into a node, show the drilldown sub-graph; otherwise show the full model neighborhood.
    const activeGraph = drillData ?? graph;
    if (!activeGraph) return { nodes: [], links: [] };
    const pathSet = new Set(pathNodeIds ?? []);
    const nodes: FGNode[] = activeGraph.nodes.map((n) => ({
      id: n.node_id,
      name: n.name,
      node_type: n.node_type,
      color: NODE_COLORS[n.node_type] ?? '#9ca3af',
      val: pathSet.has(n.node_id) ? 6 : 3,
      isPath: pathSet.has(n.node_id),
    }));
    const nodeIds = new Set(activeGraph.nodes.map((n) => n.node_id));
    const links: FGLink[] = activeGraph.edges
      .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
      .map((e) => ({
        source: e.source,
        target: e.target,
        relation_type: e.relation_type,
        weight: e.weight,
        isPath: pathSet.has(e.source) && pathSet.has(e.target),
      }));
    return { nodes, links };
  }, [graph, drillData, pathNodeIds]);

  const activeGraph = drillData ?? graph;

  const nodeById = useMemo(() => {
    const map = new Map<string, GraphNode>();
    activeGraph?.nodes.forEach((n) => map.set(n.node_id, n));
    return map;
  }, [activeGraph]);

  const relatedEdges = useMemo(() => {
    if (!selectedNode || !activeGraph) return [];
    return activeGraph.edges.filter(
      (e) => e.source === selectedNode.node_id || e.target === selectedNode.node_id
    );
  }, [selectedNode, activeGraph]);

  // Auto zoom to fit after data loads
  useEffect(() => {
    if (fgRef.current && graphData.nodes.length > 0) {
      const timer = setTimeout(() => {
        fgRef.current?.zoomToFit(400, 60);
      }, 200);
      return () => clearTimeout(timer);
    }
  }, [graphData]);

  if (loading) {
    return (
      <div className="card knowledge-graph-view">
        <h3 className="card-title">知识图谱：{modelName}</h3>
        <div className="graph-state">正在加载图谱上下文...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card knowledge-graph-view">
        <h3 className="card-title">知识图谱：{modelName}</h3>
        <div className="graph-state graph-error">{error}</div>
      </div>
    );
  }

  if (!graph || graph.nodes.length === 0) {
    return null;
  }

  const hasPathHighlight = pathNodeIds && pathNodeIds.length > 0;
  const isDrilling = !!drillNode && !!drillData;
  const displayNodeCount = isDrilling ? (drillData?.nodes.length ?? 0) : graph.nodes.length;
  const displayEdgeCount = isDrilling ? (drillData?.edges.length ?? 0) : graph.edges.length;
  const drilledNodeName = drillNode ? (graph.nodes.find((n) => n.node_id === drillNode)?.name ?? drillNode) : '';

  return (
    <div className="card knowledge-graph-view">
      <div className="graph-header">
        <div>
          <h3 className="card-title">知识图谱：{modelName}</h3>
          <div className="graph-subtitle">
            {isDrilling
              ? `下钻：${drilledNodeName}（${displayNodeCount} 节点 / ${displayEdgeCount} 关系）`
              : `${displayNodeCount} 节点 / ${displayEdgeCount} 关系`}
            {hasPathHighlight ? ` / 路径高亮 ${pathNodeIds!.length} 节点` : ''}
          </div>
        </div>
        <div className="graph-header-actions">
          {isDrilling && onResetDrill && (
            <button
              type="button"
              className="btn btn-secondary btn-small"
              onClick={onResetDrill}
            >
              返回完整子图
            </button>
          )}
          <button
            type="button"
            className="btn btn-secondary btn-small"
            onClick={() => fgRef.current?.zoomToFit(400, 60)}
          >
            适应视图
          </button>
        </div>
      </div>

      {hasPathHighlight && pathSummary && (
        <div className="graph-path-summary">
          <span className="graph-path-icon">路径</span>
          {pathSummary}
        </div>
      )}
      {pathError && (
        <div className="graph-path-error">{pathError}</div>
      )}

      <div className="graph-legend">
        {Object.entries(NODE_COLORS).map(([type, color]) => (
          <span key={type} className="graph-legend-item">
            <span className="graph-legend-dot" style={{ background: color }} />
            {NODE_LABELS[type] ?? type}
          </span>
        ))}
      </div>

      <div className="force-graph-container" ref={containerRef}>
        <ForceGraph2D
          ref={fgRef}
          graphData={graphData}
          width={containerSize.width}
          height={containerSize.height}
          nodeRelSize={4}
          nodeColor={(node: FGNode) => node.color}
          nodeVal={(node: FGNode) => node.val}
          linkColor={(link: FGLink) => (link.isPath ? '#f59e0b' : '#d1d5db')}
          linkWidth={(link: FGLink) => (link.isPath ? 2.5 : 1)}
          linkDirectionalArrowLength={3}
          linkDirectionalArrowRelPos={0.5}
          cooldownTicks={100}
          onNodeClick={(node: FGNode) => {
            const original = nodeById.get(node.id);
            if (original) setSelectedNode(original);
          }}
          nodeCanvasObject={(node: FGNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
            const radius = Math.max(2, node.val);
            ctx.beginPath();
            ctx.arc(node.x ?? 0, node.y ?? 0, radius, 0, 2 * Math.PI);
            ctx.fillStyle = node.color;
            ctx.fill();
            ctx.strokeStyle = node.isPath ? '#f59e0b' : '#ffffff';
            ctx.lineWidth = node.isPath ? 2.5 : 0.8;
            ctx.stroke();
            if (globalScale >= 1.1) {
              const label = node.name;
              const fontSize = 4 / globalScale;
              ctx.font = `${fontSize}px sans-serif`;
              ctx.textAlign = 'center';
              ctx.textBaseline = 'middle';
              ctx.fillStyle = '#1f2937';
              ctx.fillText(label, node.x ?? 0, (node.y ?? 0) + radius + fontSize);
            }
          }}
        />
      </div>

      {selectedNode && (
        <div className="graph-inspector">
          <div className="graph-inspector-title">
            {NODE_LABELS[selectedNode.node_type] ?? selectedNode.node_type}：{selectedNode.name}
          </div>
          <div className="graph-node-meta">
            <span>{selectedNode.node_id}</span>
            <span>{NODE_LABELS[selectedNode.node_type] ?? selectedNode.node_type}</span>
          </div>
          {onDrillDown && drillNode !== selectedNode.node_id && (
            <button
              type="button"
              className="btn btn-secondary btn-small graph-drill-btn"
              onClick={() => onDrillDown(selectedNode.node_id)}
              disabled={drillLoading}
            >
              {drillLoading ? '下钻中...' : '聚焦此节点邻居'}
            </button>
          )}
          <div className="graph-edge-list">
            {relatedEdges.length === 0 ? (
              <div className="graph-state">当前节点暂无直接关系</div>
            ) : (
              relatedEdges.slice(0, 12).map((edge) => (
                <div key={edge.edge_id} className="graph-edge-row">
                  <span className="graph-edge-node">
                    {nodeById.get(edge.source)?.name ?? edge.source}
                  </span>
                  <span className="graph-edge-relation">
                    {EDGE_LABELS[edge.relation_type] ?? edge.relation_type}
                  </span>
                  <span className="graph-edge-node">
                    {nodeById.get(edge.target)?.name ?? edge.target}
                  </span>
                  <span className="graph-edge-weight">{edge.weight >= 0.7 ? '强关系' : edge.weight >= 0.4 ? '中关系' : '弱关系'}</span>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default KnowledgeGraphView;
