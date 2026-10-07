import { useEffect, useState, type FormEvent } from 'react';
import { ApiError, api, type DemoSession, type Report } from '../api';

type Evidence = {
  id: string; filename: string; mimeType: string; byteSize: number; pageCount: number;
  state: 'queued' | 'processing' | 'validated' | 'failed'; failureCode: string | null;
  sources: string[]; originalUrl: string; job: { attempts: number };
};
type Props = { report: Report; session: DemoSession; source: 'chat' | 'workspace';
  refresh: number; onUploaded: () => void; onError: (error: unknown) => void };
const labels = { queued: 'Queued for validation', processing: 'Validating evidence',
  validated: 'Validated · retained', failed: 'Validation failed' };

export default function EvidencePanel({ report, session, source, refresh, onUploaded, onError }: Props) {
  const [documents, setDocuments] = useState<Evidence[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(source === 'workspace');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (source !== 'workspace') return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function read() {
      try {
        const data = await api<{ documents: Evidence[] }>(`/reports/${report.id}/evidence`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setDocuments(data.documents); setError('');
        if (data.documents.some(item => item.state === 'queued' || item.state === 'processing')) timer = setTimeout(() => void read(), 2000);
      } catch (problem) {
        if (!controller.signal.aborted) {
          setError(problem instanceof Error ? problem.message : 'Evidence is unavailable.');
          if (problem instanceof ApiError && [401, 403].includes(problem.status)) onError(problem);
        }
      } finally { if (!controller.signal.aborted) setLoading(false); }
    }
    void read();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [report.id, source, refresh, reload]);

  function failure(problem: unknown) {
    setError(problem instanceof Error ? problem.message : 'Upload failed. Try again.');
    if (problem instanceof ApiError && [401, 403].includes(problem.status)) onError(problem);
  }

  async function upload(event: FormEvent) {
    event.preventDefault(); setError(''); setNotice('');
    if (files.length < 1 || files.length > 10 || files.some(file => file.size > 10 * 1024 * 1024)) {
      setError('Choose one to ten files, up to 10 MiB each.'); return;
    }
    const body = new FormData(); body.set('source', source);
    files.forEach(file => body.append('files', file));
    setBusy(true);
    try {
      const result = await api<{ documents: { duplicate: boolean }[] }>(`/reports/${report.id}/evidence`, { method: 'POST', csrf: session.csrfToken, body });
      const reused = result.documents.filter(document => document.duplicate).length;
      setNotice(`Evidence saved to “${report.name}”. ${reused ? `${reused} existing document(s) reused. ` : ''}Originals retained; see validation status in the report. No expenses have been extracted.`);
      onUploaded();
    } catch (problem) { failure(problem); } finally { setBusy(false); }
  }

  async function retry(id: string) {
    setBusy(true); setError('');
    try {
      await api(`/documents/${id}/retry`, { method: 'POST', body: {}, csrf: session.csrfToken });
      onUploaded();
    } catch (problem) { failure(problem); } finally { setBusy(false); }
  }

  return <section className="w-evidence" aria-label={`${source === 'chat' ? 'Chat' : 'Workspace'} evidence`}>
    <h3>{source === 'chat' ? 'Attach evidence in chat' : 'Report evidence'}</h3>
    <p className="w-muted">For {report.name}. JPEG, PNG or PDF · 10 MiB/file · ten pages · ten files/batch.</p>
    <form onSubmit={event => void upload(event)}>
      <label htmlFor={`evidence-${source}`}>{source === 'chat' ? 'Chat files' : 'Workspace files'}</label>
      <input id={`evidence-${source}`} type="file" accept="image/jpeg,image/png,application/pdf" multiple disabled={busy} onChange={event => { setFiles(Array.from(event.target.files ?? [])); setNotice(''); }}/>
      <button className="w-primary" disabled={busy || files.length === 0}>{busy ? 'Saving evidence…' : 'Upload evidence'}</button>
    </form>
    {error && <div role="alert"><p>{error}</p>{source === 'workspace' && <button className="w-text-button" onClick={() => setReload(value => value + 1)}>Refresh evidence</button>}</div>}
    {notice && <p role="status" className="w-success">{notice}</p>}
    {source === 'workspace' && <>
      {loading ? <p role="status">Loading evidence…</p> : !error && documents.length === 0 ? <p>No evidence yet. Upload receipts here or in chat.</p> : null}
      <ul className="w-evidence-list">{documents.map(document => <li key={document.id}>
        <strong>{document.filename}</strong><span>{document.pageCount} page(s) · {(document.byteSize / 1024).toFixed(1)} KiB · {document.sources.join(' / ')}</span>
        <p role="status">{labels[document.state]}</p>
        {document.state === 'queued' && <p className="w-muted">Waiting for the validation worker. Your original is already saved.</p>}
        {document.state === 'failed' && <><p className="w-muted">{document.failureCode}. Original retained; retry starts a new validation revision.</p><button className="w-text-button" disabled={busy} onClick={() => void retry(document.id)}>Retry validation</button></>}
        <a href={document.originalUrl}>Download original</a>
      </li>)}</ul>
      <p className="w-muted">Validated means file checks passed. Extraction and expense amounts are not available yet.</p>
    </>}
  </section>;
}
