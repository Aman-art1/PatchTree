import type { PatchNode, Run, RunCreate } from './types';

const BASE = 'http://localhost:8000';

export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${BASE}/health`, { signal: AbortSignal.timeout(3000) });
    return res.ok;
  } catch {
    return false;
  }
}

export async function createRun(payload: RunCreate): Promise<Run> {
  const res = await fetch(`${BASE}/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => res.statusText);
    throw new Error(`POST /runs failed (${res.status}): ${txt}`);
  }
  return res.json();
}

export async function getRun(runId: string): Promise<Run> {
  const res = await fetch(`${BASE}/runs/${runId}`);
  if (!res.ok) throw new Error(`GET /runs/${runId} failed: ${res.status}`);
  return res.json();
}

export async function getTree(runId: string): Promise<PatchNode[]> {
  const res = await fetch(`${BASE}/runs/${runId}/tree`);
  if (!res.ok) throw new Error(`GET /runs/${runId}/tree failed: ${res.status}`);
  return res.json();
}

export async function pollUntilComplete(
  runId: string,
  onUpdate: (run: Run, nodes: PatchNode[]) => void,
  intervalMs = 1500,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const tick = async () => {
      try {
        const [run, nodes] = await Promise.all([getRun(runId), getTree(runId)]);
        onUpdate(run, nodes);
        if (run.status === 'complete' || run.status === 'failed') resolve();
        else setTimeout(tick, intervalMs);
      } catch (e) {
        reject(e);
      }
    };
    tick();
  });
}
