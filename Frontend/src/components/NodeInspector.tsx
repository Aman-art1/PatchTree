import { X, Cpu, DollarSign, Clock } from 'lucide-react';
import type { PatchNode } from '../types';

const BRANCH_LABELS: Record<string, string> = {
  root: 'Root', search: 'Search', stability: 'Stability',
  adversarial: 'Adversarial', full_suite: 'Full Suite',
};
const BRANCH_COLORS: Record<string, string> = {
  root: '#6366f1', search: '#3b82f6', stability: '#10b981',
  adversarial: '#f59e0b', full_suite: '#8b5cf6',
};
const MODEL_SHORT: Record<string, string> = {
  'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B': 'Nano 30B',
  'nvidia/nemotron-3-super-120b-a12b': 'Super 120B',
  'nvidia/Nemotron-Super-70B': 'Super 120B',
  'nvidia/Nemotron-3-Ultra-550b-a55b': 'Ultra 550B',
  'nvidia/Nemotron-Ultra-253B': 'Ultra 550B',
  'none': 'None',
};

function DiffViewer({ diff }: { diff: string }) {
  return (
    <pre className="diff-viewer">
      {diff.split('\n').map((line, i) => {
        const cls = line.startsWith('+') && !line.startsWith('+++')
          ? 'diff-add'
          : line.startsWith('-') && !line.startsWith('---')
            ? 'diff-del'
            : line.startsWith('@@')
              ? 'diff-hunk'
              : 'diff-ctx';
        return <span key={i} className={`diff-line diff-line--${cls}`}>{line}{'\n'}</span>;
      })}
    </pre>
  );
}

interface Props { node: PatchNode; onClose: () => void; }

export default function NodeInspector({ node, onClose }: Props) {
  const color = BRANCH_COLORS[node.branch_type] ?? '#6b7280';
  const modelLabel = MODEL_SHORT[node.model_used] ?? node.model_used;

  return (
    <aside className="inspector">
      <div className="inspector__header" style={{ borderTopColor: color }}>
        <h3 className="inspector__title">{BRANCH_LABELS[node.branch_type]} Node</h3>
        <button className="inspector__close" onClick={onClose}><X size={16} /></button>
      </div>

      <div className="inspector__body">
        {/* badges row */}
        <div className="inspector__row">
          <span className="inspector__label">Test Result</span>
          <span className={`pnode__badge pnode__badge--${node.test_result === 'pass' ? 'pass' : 'fail'}`}>
            {node.test_result.toUpperCase()}
          </span>
        </div>

        <div className="inspector__row">
          <span className="inspector__label">Branch</span>
          <span className="inspector__pill" style={{ background: color + '22', color }}>
            {BRANCH_LABELS[node.branch_type]}
          </span>
        </div>

        {node.model_used && node.model_used !== 'none' && (
          <div className="inspector__row">
            <span className="inspector__label"><Cpu size={11} style={{ marginRight: 3 }} />Model</span>
            <span className="inspector__value">{modelLabel}</span>
          </div>
        )}

        <div className="inspector__metrics">
          {node.tokens_in != null && (
            <div className="metric"><span className="metric__label">Tokens in</span><span className="metric__val">{node.tokens_in}</span></div>
          )}
          {node.tokens_out != null && (
            <div className="metric"><span className="metric__label">Tokens out</span><span className="metric__val">{node.tokens_out}</span></div>
          )}
          {node.estimated_cost_usd != null && (
            <div className="metric"><DollarSign size={11} /><span className="metric__val">${node.estimated_cost_usd.toFixed(4)}</span></div>
          )}
          {node.wall_time_seconds != null && (
            <div className="metric"><Clock size={11} /><span className="metric__val">{node.wall_time_seconds.toFixed(1)}s</span></div>
          )}
        </div>

        {node.branch_type === 'stability' && node.stability_runs != null && (
          <div className="inspector__stab">
            Stability: <strong>{node.stability_passes}/{node.stability_runs}</strong> runs passed
          </div>
        )}

        {node.hypothesis && (
          <div className="inspector__section">
            <div className="inspector__label">Hypothesis</div>
            <p className="inspector__text">{node.hypothesis}</p>
          </div>
        )}

        {node.patch_diff && (
          <div className="inspector__section">
            <div className="inspector__label">Patch Diff</div>
            <DiffViewer diff={node.patch_diff} />
          </div>
        )}

        {node.test_output && (
          <div className="inspector__section">
            <div className="inspector__label">Test Output</div>
            <pre className="inspector__terminal">{node.test_output}</pre>
          </div>
        )}
      </div>
    </aside>
  );
}
