import { useEffect, useState } from 'react';
import { api, type DemoSession, type Report } from '../api';

type Connection = { configured: boolean; status: string; account: string | null };
type Window = { reportFingerprint: string; windowStart: string; windowEndExclusive: string; maxMessages: number; maxFiles: number; permissionMinutes: number };
type Scan = { id: string; state: string; scanned: number; imported: number; skipped: number; truncated: boolean; failureCode: string | null };
const callbackMessages: Record<string, string> = { connected: 'Gmail connected. Authorize a report scan separately.', consent_denied: 'Google permission was denied. Upload manually or try connecting again.', wrong_account: 'Only aban.hackathon@gmail.com is supported in this demo.', state_invalid: 'Connection permission expired or was already used. Connect again.', session_or_persona_changed: 'Session or persona changed. Return to Employee and connect again.', revoked: 'Google access expired or was revoked. Reconnect.', refresh_missing: 'Offline access was not granted. Reconnect with consent.' };

export default function GmailPanel({ report, session, onImported, onError }: { report: Report; session: DemoSession; onImported: () => void; onError: (error: unknown) => void }) {
  const [connection, setConnection] = useState<Connection | null>(null);
  const [window, setWindow] = useState<Window | null>(null);
  const [scans, setScans] = useState<Scan[]>([]);
  const [busy, setBusy] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState(callbackMessages[new URLSearchParams(globalThis.window.location.search).get('gmail') ?? ''] ?? '');
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const load = async () => {
      try {
        const [status, data] = await Promise.all([api<Connection>('/gmail', { signal: controller.signal }), api<{ scans: Scan[] }>(`/reports/${report.id}/gmail-scans`, { signal: controller.signal })]);
        if (controller.signal.aborted) return;
        setConnection(status); setScans(data.scans);
        if (data.scans.some(scan => scan.state === 'queued' || scan.state === 'processing')) {
          onImported(); timer = setTimeout(load, 2000);
        } else { onImported(); }
        if (status.configured) setWindow(await api<Window>(`/reports/${report.id}/gmail-window`, { signal: controller.signal }));
      } catch (problem) { if (!controller.signal.aborted) { setError(problem instanceof Error ? problem.message : 'Cannot load Gmail state.'); onError(problem); } }
    };
    void load();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [report.id, busy]);
  const command = async (action: () => Promise<void>) => {
    setBusy(true); setError('');
    try { await action(); } catch (problem) { setError(problem instanceof Error ? problem.message : 'Gmail failed.'); onError(problem); } finally { setBusy(false); }
  };
  return <section className="w-evidence" aria-label="Gmail evidence">
    <h3>Optional Gmail evidence</h3>
    <p>Google read-only permission can read broadly. Unloop searches only the separately authorized report window. No send, modify or continuous monitoring.</p>
    <p>Demo mailbox: aban.hackathon@gmail.com. Manual uploads work independently.</p>
    {notice && <p role="status">{notice}</p>}{error && <p role="alert">{error}</p>}
    {!connection ? <p role="status">Loading Gmail status…</p> : !connection.configured ? <p>Gmail is not configured. Use manual uploads; no mailbox is connected or scanned.</p> : <>
      <p>{connection.status === 'connected' ? `Connected: ${connection.account}` : connection.status === 'reconnect_required' ? 'Google access needs reconnection.' : 'Gmail disconnected.'}</p>
      <button disabled={busy} onClick={() => void command(async () => { const result = await api<{ authorizationUrl: string }>('/gmail/connect', { method: 'POST', body: {}, csrf: session.csrfToken }); globalThis.window.location.assign(result.authorizationUrl); })}>{connection.status === 'connected' ? 'Reconnect Gmail' : 'Connect Gmail'}</button>
      {connection.status === 'connected' && <button disabled={busy} onClick={() => void command(async () => { const result = await api<{ providerRevocation: string }>('/gmail/disconnect', { method: 'POST', body: {}, csrf: session.csrfToken }); setNotice(`Credentials removed; future scans stopped. Imported originals remain retained. ${result.providerRevocation === 'revocation_failed' ? 'Provider revocation failed; remove permission in Google account settings.' : ''}`); })}>Disconnect Gmail</button>}
      {window && <div>
        <p>Scan {window.windowStart.slice(0, 10)} through {new Date(new Date(window.windowEndExclusive).getTime() - 86400000).toISOString().slice(0, 10)} (UTC): 90-day booking lookback and seven days after report end. Up to 15 messages, ten files, 40 MiB; each file up to 10 MiB/ten pages. Permission expires after 20 minutes.</p>
        <label><input type="checkbox" checked={confirmed} disabled={busy || connection.status !== 'connected'} onChange={event => setConfirmed(event.target.checked)}/> Authorize one bounded scan for this report. Arrival dates are not expense dates; all imported evidence requires review.</label>
        <button disabled={busy || !confirmed || connection.status !== 'connected'} onClick={() => void command(async () => { await api(`/reports/${report.id}/gmail-scans`, { method: 'POST', csrf: session.csrfToken, body: { confirmed: true, reportFingerprint: window.reportFingerprint } }); setConfirmed(false); setNotice('Scan queued. A running worker is required; progress is retained on reload.'); })}>Scan authorized window</button>
      </div>}
    </>}
    {scans.map(scan => <div key={scan.id}><p>{scan.state}: {scan.scanned} messages checked, {scan.imported} files retained, {scan.skipped} skipped. {scan.truncated && 'Search/file limits reached; results are incomplete.'} {scan.failureCode && `Outcome: ${scan.failureCode.replaceAll('_', ' ')}.`}</p>{['failed', 'partial'].includes(scan.state) && <button disabled={busy} onClick={() => void command(async () => { await api(`/gmail-scans/${scan.id}/retry`, { method: 'POST', body: {}, csrf: session.csrfToken }); })}>Retry within consent</button>}</div>)}
    <p>Body-only/unsupported receipts may need manual upload. Imported bytes stay in this demo database until explicit owner cleanup; disconnect deletes credentials, not retained evidence. No expenses are extracted yet.</p>
  </section>;
}
