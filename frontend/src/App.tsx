import { useEffect, useState } from 'react';

type Example = { title: string; type: string; merchant: string; amount: string;
  claim: string; excess: string; status: string; explanation: string; lines: string[] };
const examples: Example[] = [
  { title: 'Dinner above the limit', type: 'Dinner', merchant: 'Orchard Table', amount: '62.00',
    claim: '50.00', excess: '12.00', status: 'Adjusted to policy limit',
    explanation: 'The Dinner allowance is £50, including service charges. £12 stays outside the claim.',
    lines: ['Dinner                 GBP 56.00', 'Service charge          GBP 6.00', 'Total                  GBP 62.00'] },
  { title: 'Lunch within the limit', type: 'Lunch', merchant: 'Canal Kitchen', amount: '18.50',
    claim: '18.50', excess: '0.00', status: 'Within the meal limit',
    explanation: 'This Lunch is within the £25 allowance. The full receipt amount can be claimed.',
    lines: ['Lunch                  GBP 18.50', 'Total                  GBP 18.50'] },
  { title: 'Meal type needs clarification', type: 'Not established', merchant: 'Market Cafe', amount: '22.00',
    claim: '—', excess: '—', status: 'Needs information',
    explanation: 'Was this Breakfast, Lunch or Dinner? The amount alone cannot determine the meal type.',
    lines: ['Food and drink         GBP 22.00', 'Total                  GBP 22.00'] },
];

export default function App() {
  const [selected, setSelected] = useState(0);
  const [health, setHealth] = useState('Checking local API…');
  const [showReceipt, setShowReceipt] = useState(true);
  const example = examples[selected];
  useEffect(() => {
    const abort = new AbortController();
    const timer = window.setTimeout(() => abort.abort(), 4000);
    fetch('/api/health', { signal: abort.signal }).then(async response => {
      if (!response.ok) throw new Error('API unavailable');
      const data = await response.json();
      if (data.service !== 'unloop' || data.status !== 'ok') throw new Error('Wrong service');
      setHealth('Local API connected');
    }).catch(() => setHealth('Local API offline — start Flask on port 5001'))
      .finally(() => window.clearTimeout(timer));
    return () => { abort.abort(); window.clearTimeout(timer); };
  }, []);
  const money = (value: string) => value === '—' ? value : '£' + value;
  return <div className="app">
    <header className="topbar"><a className="brand" href="/" aria-label="Unloop home"><span className="brandmark" aria-hidden="true">u</span>unloop</a><span className="preview-tag">Local design preview</span></header>
    <main>
      <div className="page-heading"><div><p className="breadcrumb">Expenses / Example report</p><h1>A clearer path to your claim.</h1><p className="intro">Keep the receipt. See what you can claim. Review it all in one place.</p></div><span className="draft">Example draft</span></div>
      <aside className="preview-note"><strong>Synthetic examples only.</strong> These are expected outcomes, not AI results. Upload, sign-in and saving arrive in the next build phases.</aside>
      <section className="report-context" aria-label="Example report details"><div><span>Report name</span><strong>Leicester client visit</strong></div><div><span>Business purpose</span><strong>Client workshop</strong></div><div><span>Manager</span><strong>manager@example.com</strong></div><div><span>Report currency</span><strong>GBP</strong></div></section>
      <div className="workspace">
        <aside className="examples"><h2>Meal examples</h2><p>Select an example to inspect its expected outcome.</p><div className="example-list">{examples.map((item, index) => <button key={item.title} aria-pressed={selected === index} onClick={() => { setSelected(index); setShowReceipt(true); }}><span className="example-type">{index === 2 ? 'Unclear meal' : item.type}</span><strong>{item.merchant}</strong><span>{money(item.amount)}</span></button>)}</div><button className="upload" disabled>Upload receipt · next phase</button><p className="small">One meal. One restaurant.<br/>One receipt.</p></aside>
        <section className="expense" aria-labelledby="expense-heading">
          <div className="section-heading"><div><p className="small">Expense details</p><h2 id="expense-heading">{example.title}</h2></div><span className={'status ' + (selected === 2 ? 'pending' : '')}>{example.status}</span></div>
          <dl className="facts"><div><dt>Merchant</dt><dd>{example.merchant}</dd></div><div><dt>Receipt date</dt><dd>21 September 2026</dd></div><div><dt>Category</dt><dd>Meals</dd></div><div><dt>Meal type</dt><dd>{example.type}</dd></div></dl>
          <div className="amounts"><div><span>Receipt amount</span><strong>{money(example.amount)}</strong><small>Original amount · GBP</small></div><div className="claim"><span>Claim amount</span><strong>{money(example.claim)}</strong><small>{example.claim === '—' ? 'Meal type needed' : 'After applying the meal allowance'}</small></div></div>
          <div className="explanation" aria-live="polite"><p>{example.explanation}</p><dl><dt>Amount above policy limit</dt><dd>{money(example.excess)}</dd></dl><span className="small">Synthetic policy · {selected === 2 ? 'MEAL-01' : 'MEAL-03 / MEAL-04'}</span></div>
          <div className="travel-fields" aria-label="Travel fields not applicable"><span>Cabin <strong>Not applicable</strong></span><span>Origin / destination <strong>Not applicable</strong></span></div>
          <div className="actions"><p className="small">Your receipt amount always stays separate from your claim.</p><button disabled>Save expense · next phase</button></div>
        </section>
        <aside className="evidence"><div className="section-heading"><h2>Receipt evidence</h2><button className="text-button" onClick={() => setShowReceipt(!showReceipt)} aria-expanded={showReceipt}>{showReceipt ? 'Hide' : 'Show'} receipt</button></div>{showReceipt && <div className="receipt"><p className="synthetic">Synthetic receipt</p><h3>{example.merchant}</h3><p>Leicester, UK<br/>21 September 2026</p><hr/>{example.lines.map(line => <p className="receipt-line" key={line}>{line}</p>)}<hr/><p>Thank you for visiting.</p></div>}<p className="small">The original evidence stays available alongside the expense.</p></aside>
      </div>
      <footer><span>{health}</span><span>No data is saved in this preview.</span></footer>
    </main>
  </div>;
}
