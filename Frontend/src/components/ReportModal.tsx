import { useState, useEffect } from 'react';
import { X, Shield, Clock, DollarSign, Percent } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import type { Run } from '../types';
import { getRun } from '../api';

interface Props {
  run: Run;
  onClose: () => void;
}

function ScoreGauge({ score }: { score: number }) {
  const pct = Math.min(100, Math.max(0, score));
  const color = pct >= 80 ? '#10b981' : pct >= 50 ? '#f59e0b' : '#ef4444';
  const r = 40;
  const circ = 2 * Math.PI * r;
  const dash = (pct / 100) * circ;
  return (
    <div className="gauge">
      <svg width="100" height="100" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r={r} fill="none" stroke="#1e293b" strokeWidth="10" />
        <circle
          cx="50" cy="50" r={r} fill="none" stroke={color} strokeWidth="10"
          strokeDasharray={`${dash} ${circ - dash}`}
          strokeLinecap="round"
          transform="rotate(-90 50 50)"
          style={{ transition: 'stroke-dasharray 0.8s ease' }}
        />
        <text x="50" y="55" textAnchor="middle" fill={color} fontSize="16" fontWeight="700">{pct}%</text>
      </svg>
      <div className="gauge__label" style={{ color }}>
        {pct >= 80 ? '✅ PRODUCTION-READY' : pct >= 50 ? '⚠ REVIEW NEEDED' : '❌ HONEST FAILURE'}
      </div>
    </div>
  );
}

export default function ReportModal({ run: initialRun, onClose }: Props) {
  const [run, setRun] = useState<Run>(initialRun);

  useEffect(() => {
    if (!run.confidence_report && run.run_id && !run.run_id.startsWith('mock-')) {
      getRun(run.run_id).then((fresh) => {
        if (fresh && fresh.confidence_report) setRun(fresh);
      }).catch(() => {});
    }
  }, [run.run_id, run.confidence_report]);

  const score = Math.round((run.confidence_score ?? 0) * 100);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal--wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal__header">
          <div className="modal__title-wrap">
            <Shield size={18} className="modal__icon" />
            <h2 className="modal__title">Confidence Report</h2>
          </div>
          <button className="inspector__close" onClick={onClose}><X size={16} /></button>
        </div>

        <div className="report-modal__body">
          <div className="report-modal__sidebar">
            <ScoreGauge score={score} />
            <div className="report-modal__stats">
              {run.total_cost_usd != null && (
                <div className="telemetry__item">
                  <DollarSign size={13} /><span>${run.total_cost_usd.toFixed(4)}</span>
                </div>
              )}
              {run.total_wall_time_seconds != null && (
                <div className="telemetry__item">
                  <Clock size={13} /><span>{run.total_wall_time_seconds.toFixed(1)}s</span>
                </div>
              )}
              {run.confidence_score != null && (
                <div className="telemetry__item telemetry__item--highlight">
                  <Percent size={13} /><span>{score.toFixed(0)}% confidence</span>
                </div>
              )}
              {run.adversarial_runs != null && (
                <div className="telemetry__item">
                  <Shield size={13} />
                  <span>{run.adversarial_survived}/{run.adversarial_runs} attacks survived</span>
                </div>
              )}
              {run.full_suite_result && (
                <div className={`telemetry__item ${run.full_suite_result === 'pass' ? '' : 'telemetry__item--fail'}`}>
                  Full suite: {run.full_suite_result === 'pass' ? '✅ PASS' : '❌ FAIL'}
                </div>
              )}
            </div>
          </div>

          <div className="report-modal__content">
            {run.confidence_report ? (
              <div className="md-report">
                <ReactMarkdown>{run.confidence_report}</ReactMarkdown>
              </div>
            ) : (
              <p className="report-modal__empty">Report not yet available.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
