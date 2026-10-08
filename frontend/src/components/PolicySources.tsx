import { useEffect, useState } from 'react';
import { api } from '../api';

type Clause = { id: string; title: string; text: string; source: string };
export default function PolicySources({ refresh }: { refresh: number }) {
  const [source, setSource] = useState<{ status: string; version: string | null; clauses: Clause[]; message?: string } | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    api<NonNullable<typeof source>>('/policy', { signal: controller.signal }).then(value => { if (!controller.signal.aborted) setSource(value); }).catch(value => { if (!controller.signal.aborted) setError(value instanceof Error ? value.message : 'Policy sources unavailable.'); });
    return () => controller.abort();
  }, [refresh]);
  return <section className="w-evidence" aria-label="Policy sources"><h3>Policy sources</h3>{error ? <p role="alert">{error}</p> : !source ? <p>Loading policy sources…</p> : source.status !== 'active' ? <p>{source.message}</p> : <><p>Synthetic demo policy · {source.version}</p><p>Governing clauses control assessment. An explanation cannot change a claim or grant an exception.</p>{source.clauses.map(clause => <details id={`policy-${clause.id}`} key={clause.id}><summary>{clause.id} · {clause.title}</summary><p style={{ whiteSpace: 'pre-wrap' }}>{clause.text}</p><small>{clause.source} · {source.version}</small></details>)}</>}</section>;
}
