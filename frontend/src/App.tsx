import { useEffect, useRef, useState } from 'react';
import { ApiError, api, loadSession, type DemoSession, type Persona, type Report } from './api';
import AstraIntake from './components/AstraIntake';
import ReportList from './components/ReportList';
import ReportWorkspace from './components/ReportWorkspace';
import SyntheticPreview from './SyntheticPreview';
import './workspace.css';

export default function App() {
  return new URLSearchParams(window.location.search).has('preview') ? <SyntheticPreview /> : <Workspace />;
}

function Workspace() {
  const [session, setSession] = useState<DemoSession | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const [selected, setSelected] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [opening, setOpening] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [error, setError] = useState('');
  const [expired, setExpired] = useState(false);
  const [intakeKey, setIntakeKey] = useState(0);
  const [showInbox, setShowInbox] = useState(false);
  const [evidenceRefresh, setEvidenceRefresh] = useState(0);
  const epoch = useRef(0);
  const readSequence = useRef(0);

  const clearPrivateState = () => {
    epoch.current += 1; readSequence.current += 1;
    setReports([]); setSelected(null); setOpening(false); setShowInbox(false); setIntakeKey(value => value + 1);
  };

  function failure(problem: unknown) {
    const message = problem instanceof Error ? problem.message : 'The request failed. Try again.';
    setError(message);
    if (problem instanceof ApiError && problem.status === 401) {
      clearPrivateState(); setSession(null); setExpired(true); setLoading(false);
    } else if (problem instanceof ApiError && problem.code === 'employee_required') {
      clearPrivateState();
      api<DemoSession>('/session').then(setSession).catch(failure);
    }
  }

  async function restart() {
    setLoading(true); setError('');
    try { setSession(await api<DemoSession>('/session', { method: 'POST', body: {} })); setExpired(false); }
    catch (problem) { failure(problem); } finally { setLoading(false); }
  }

  useEffect(() => {
    let cancelled = false;
    loadSession().then(value => { if (!cancelled) { setSession(value); setLoading(false); } })
      .catch(problem => { if (!cancelled) { failure(problem); setLoading(false); } });
    return () => { cancelled = true; };
  }, []);

  async function openReport(id: string) {
    const generation = epoch.current, requestNumber = ++readSequence.current;
    setOpening(true); setSelected(null); setError('');
    try {
      const report = await api<Report>(`/reports/${id}`);
      if (generation === epoch.current && requestNumber === readSequence.current) {
        setSelected(report); window.history.replaceState({}, '', `?report=${report.id}`);
      }
    } catch (problem) { if (generation === epoch.current) failure(problem); }
    finally { if (generation === epoch.current && requestNumber === readSequence.current) setOpening(false); }
  }

  useEffect(() => {
    if (!session) return;
    if (session.persona !== 'employee') { setLoading(false); return; }
    const controller = new AbortController(), generation = epoch.current;
    setLoading(true);
    api<{ reports: Report[] }>('/reports', { signal: controller.signal }).then(data => {
      if (controller.signal.aborted || generation !== epoch.current) return;
      setReports(data.reports);
      const requested = new URLSearchParams(window.location.search).get('report');
      const first = data.reports.find(report => report.id === requested) ?? data.reports[0];
      if (first) void openReport(first.id);
    }).catch(problem => { if (!controller.signal.aborted && generation === epoch.current) failure(problem); })
      .finally(() => { if (!controller.signal.aborted && generation === epoch.current) setLoading(false); });
    return () => { controller.abort(); };
  }, [session?.profile.id, session?.persona]);

  async function switchPersona(persona: Persona) {
    if (!session || session.persona === persona) return;
    clearPrivateState(); setSwitching(true); setError(''); window.history.replaceState({}, '', '/');
    try { setSession(await api<DemoSession>('/session/persona', { method: 'PATCH', csrf: session.csrfToken, body: { persona } })); }
    catch (problem) { failure(problem); } finally { setSwitching(false); }
  }

  const generation = epoch.current;
  function saved(report: Report) {
    if (generation !== epoch.current) return;
    readSequence.current += 1; setOpening(false);
    setReports(previous => [report, ...previous.filter(item => item.id !== report.id)]);
    setSelected(report); setError(''); window.history.replaceState({}, '', `?report=${report.id}`);
  }

  return <div className="w-app">
    <header className="w-topbar"><a className="brand" href="/" aria-label="Unloop home"><span className="brandmark" aria-hidden="true">u</span>unloop</a>
      <div className="w-personas" role="group" aria-label="Demo persona">{(['employee', 'manager'] as Persona[]).map(persona => <button key={persona} aria-pressed={session?.persona === persona} disabled={!session || switching} onClick={() => void switchPersona(persona)}>{persona === 'employee' ? 'Employee' : 'Manager'}</button>)}</div>
      <button className="w-inbox-button" disabled={!session || switching} onClick={() => setShowInbox(value => !value)} aria-expanded={showInbox}>Inbox</button>
    </header>
    <main className="w-main">
      <div className="w-page-heading"><div><h1>{session?.persona === 'manager' ? 'Manager workspace' : 'Prepare your next report.'}</h1><p>One place to start, review and return to your expenses.</p></div>
        {session && <p className="w-identity">{session.profile.displayName}{session.persona === 'employee' && <span>Grade {session.profile.grade} · fixed demo profile</span>}</p>}
      </div>
      <p className="w-session-note">Demo workspace. {session ? `Reports are available in this browser session until ${new Date(session.expiresAt).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })}.` : 'Reports stay private to your demo session.'}</p>
      {error && <div className="w-error" role="alert"><p>{error}</p>{!expired && <button className="w-text-button" onClick={() => window.location.reload()}>Reload workspace</button>}</div>}
      {!session ? <section className="w-unavailable">{loading ? <p role="status">Opening your workspace…</p> : expired ? <><h2>Start a new demo session</h2><p>The previous session is no longer accessible. A new session starts with an empty workspace.</p><button className="w-primary" onClick={() => void restart()}>Start new demo session</button></> : <><h2>Workspace unavailable</h2><p>Restore the API and report storage, then reload this page.</p><button className="w-primary" onClick={() => window.location.reload()}>Try again</button></>}</section> : switching ? <p role="status">Switching persona…</p> : session.persona === 'manager' ?
        <section className="w-manager-empty"><span className="w-draft-badge">Manager inbox</span><h2>No submitted reports</h2><p>Employee drafts stay private. Submission and manager review are not available yet.</p></section> :
        <div className="w-layout"><ReportList reports={reports} selectedId={selected?.id} loading={loading} onSelect={id => void openReport(id)} onNew={() => { readSequence.current += 1; setSelected(null); setOpening(false); setIntakeKey(value => value + 1); window.history.replaceState({}, '', '/'); }}/>
          <AstraIntake key={`${session.profile.id}:${intakeKey}`} session={session} report={selected} refresh={evidenceRefresh} onUploaded={() => setEvidenceRefresh(value => value + 1)} onSaved={saved} onError={problem => { if (generation === epoch.current) failure(problem); }}/>
          <ReportWorkspace report={selected} loading={opening} session={session} refresh={evidenceRefresh} onUploaded={() => setEvidenceRefresh(value => value + 1)} onError={failure}/></div>}
      {showInbox && <section className="w-inbox" aria-label="Inbox"><h2>Inbox</h2><p>No inbox events yet. Submission and review will add events here when available.</p></section>}
      <footer className="w-footer"><span>{session ? 'Demo workspace' : 'Unloop demo'}</span><a href="/?preview=1">View synthetic Meal preview</a></footer>
    </main>
  </div>;
}
