import { useEffect, useState } from 'react';
import { api, type DemoSession } from '../api';
type Event = { id: string; reportId: string; read: boolean; createdAt: string; payload: { type: string; message?: string; claimGbp?: string; approvedClaimGbp?: string; expenseId?: string; nextAction?: string } };
export default function Inbox({ session, refresh }: { session: DemoSession; refresh: number }) {
  const [rows, setRows] = useState<Event[]>([]), [error, setError] = useState(''), [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    api<{ events: Event[] }>('/inbox', { signal: controller.signal }).then(value => { if (!controller.signal.aborted) setRows(value.events); }).catch(value => { if (!controller.signal.aborted) setError(value instanceof Error ? value.message : 'Inbox unavailable.'); });
    return () => controller.abort();
  }, [refresh, reload, session.profile.id]);
  return <section className="w-inbox" aria-label="Inbox"><h2>Inbox</h2>{error && <p role="alert">{error}</p>}{!rows.length && <p>No inbox events yet.</p>}{rows.map(value => <article key={value.id}><h3>{value.payload.type.replaceAll('_', ' ')}</h3><p>{value.payload.message || (value.payload.claimGbp ? `Submitted GBP ${value.payload.claimGbp}` : 'Review activity recorded.')}</p>{value.payload.approvedClaimGbp && <p>Approved £{value.payload.approvedClaimGbp}</p>}{value.payload.nextAction && <p>{value.payload.nextAction}</p>}{session.persona === 'employee' && <a href={`/?report=${encodeURIComponent(value.reportId)}${value.payload.expenseId ? `&expense=${encodeURIComponent(value.payload.expenseId)}` : ''}`}>Open affected report</a>}<button disabled={value.read} onClick={() => void api(`/inbox/${value.id}`, { method: 'PATCH', csrf: session.csrfToken, body: { read: true } }).then(() => setReload(old => old + 1)).catch(problem => setError(problem instanceof Error ? problem.message : 'Unable to mark read.'))}>{value.read ? 'Read' : 'Mark read'}</button></article>)}</section>;
}
