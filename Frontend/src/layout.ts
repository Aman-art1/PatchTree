import dagre from 'dagre';
import type { PatchNode } from './types';

export const NODE_W = 210;
export const NODE_H = 95;

export function computeLayout(nodes: PatchNode[]): Map<string, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: 'TB', ranksep: 70, nodesep: 30, marginx: 40, marginy: 40 });
  g.setDefaultEdgeLabel(() => ({}));

  for (const n of nodes) g.setNode(n.node_id, { width: NODE_W, height: NODE_H });
  for (const n of nodes) {
    if (n.parent_node_id) g.setEdge(n.parent_node_id, n.node_id);
  }

  dagre.layout(g);

  const pos = new Map<string, { x: number; y: number }>();
  for (const n of nodes) {
    const { x, y } = g.node(n.node_id);
    pos.set(n.node_id, { x: x - NODE_W / 2, y: y - NODE_H / 2 });
  }
  return pos;
}
