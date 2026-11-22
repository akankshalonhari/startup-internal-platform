import { useCallback, useEffect, useState } from "react";
import { api } from "./api.js";

const KINDS = ["seed", "plant", "tissue_sample"];
const RELATION_LABEL = {
  female_parent: "female parent of",
  male_parent: "male parent of",
  derived_from: "source of",
};

// Polls a loader every few seconds, so async results (lab jobs created by the
// Pub/Sub consumer) show up without a refresh.
function usePolling(loader, ms = 2000) {
  const [data, setData] = useState([]);
  const [error, setError] = useState(null);
  const refresh = useCallback(() => {
    loader().then(setData).then(() => setError(null)).catch((e) => setError(e.message));
  }, [loader]);
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, ms);
    return () => clearInterval(t);
  }, [refresh, ms]);
  return { data, error, refresh };
}

function RegisterForm({ entities, onCreated }) {
  const [form, setForm] = useState({
    barcode: "",
    kind: "tissue_sample",
    species: "Solanum tuberosum",
    femaleParent: "",
    maleParent: "",
    derivedFrom: "",
  });
  const [status, setStatus] = useState(null);
  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    const parents = [
      form.femaleParent && { parent_id: form.femaleParent, relation: "female_parent" },
      form.maleParent && { parent_id: form.maleParent, relation: "male_parent" },
      form.derivedFrom && { parent_id: form.derivedFrom, relation: "derived_from" },
    ].filter(Boolean);
    try {
      const created = await api.createEntity({
        barcode: form.barcode,
        kind: form.kind,
        species: form.species,
        parents,
      });
      setStatus({ ok: true, text: `Registered ${created.barcode}` });
      setForm({ ...form, barcode: "" });
      onCreated();
    } catch (err) {
      setStatus({ ok: false, text: err.message });
    }
  }

  const parentSelect = (label, field) => (
    <label>
      {label}
      <select value={form[field]} onChange={set(field)}>
        <option value="">None</option>
        {entities.map((e) => (
          <option key={e.id} value={e.id}>
            {e.barcode} ({e.kind})
          </option>
        ))}
      </select>
    </label>
  );

  return (
    <form className="card" onSubmit={submit}>
      <h2>Register a sample</h2>
      <label>
        Barcode
        <input value={form.barcode} onChange={set("barcode")} placeholder="PT-TS-0042" required />
      </label>
      <label>
        Kind
        <select value={form.kind} onChange={set("kind")}>
          {KINDS.map((k) => (
            <option key={k}>{k}</option>
          ))}
        </select>
      </label>
      <label>
        Species
        <input value={form.species} onChange={set("species")} />
      </label>
      {parentSelect("Female parent", "femaleParent")}
      {parentSelect("Male parent", "maleParent")}
      {parentSelect("Derived from", "derivedFrom")}
      <button type="submit">Register</button>
      {status && <p className={status.ok ? "ok" : "err"}>{status.text}</p>}
      <p className="hint">
        Register a <b>tissue_sample</b> and watch its lab job appear a second later: API → Postgres
        outbox → relay → Pub/Sub → scheduler.
      </p>
    </form>
  );
}

function EntityTable({ entities, selectedId, onSelect }) {
  return (
    <div className="card">
      <h2>Entities</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Barcode</th>
              <th>Kind</th>
              <th>Lab job</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {entities.map((e) => (
              <tr key={e.id} className={e.id === selectedId ? "selected" : ""}>
                <td className="mono">{e.barcode}</td>
                <td>{e.kind}</td>
                <td>{e.lab_job_status ?? "—"}</td>
                <td>
                  <button type="button" className="link" onClick={() => onSelect(e.id)}>
                    Pedigree
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PedigreePanel({ entityId, entities }) {
  const [nodes, setNodes] = useState([]);
  const [error, setError] = useState(null);
  useEffect(() => {
    if (!entityId) return;
    let stale = false;
    setNodes([]);
    setError(null);
    api
      .pedigree(entityId)
      .then((n) => !stale && setNodes(n))
      .catch((e) => !stale && setError(e.message));
    return () => {
      stale = true;
    };
  }, [entityId]);

  const root = entities.find((e) => e.id === entityId);
  const barcodeOf = (id) => entities.find((e) => e.id === id)?.barcode ?? id;

  return (
    <div className="card">
      <h2>Pedigree</h2>
      {!entityId && <p className="hint">Pick an entity. Try PT-CH-001 from the seed data.</p>}
      {error && <p className="err">{error}</p>}
      {root && (
        <p>
          Ancestors of <b className="mono">{root.barcode}</b>{" "}
          <span className="hint">(recursive CTE, 5 generations)</span>
        </p>
      )}
      {entityId && nodes.length === 0 && !error && <p className="hint">No recorded parents.</p>}
      <ul className="tree">
        {nodes.map((n) => (
          <li key={`${n.id}-${n.child_id}-${n.relation}`} style={{ marginLeft: (n.depth - 1) * 20 }}>
            <span className="depth">gen {n.depth}</span>
            <span className="mono">{n.barcode}</span> → {RELATION_LABEL[n.relation]}{" "}
            <span className="mono">{barcodeOf(n.child_id)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function LabJobs({ jobs }) {
  return (
    <div className="card">
      <h2>Lab jobs (created by the Pub/Sub consumer)</h2>
      {jobs.length === 0 && <p className="hint">None yet. Register a tissue sample.</p>}
      <ul className="jobs">
        {jobs.map((j) => (
          <li key={j.id}>
            #{j.id} <span className="mono">{j.barcode}</span> · {j.assay} · <b>{j.status}</b>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function App() {
  const entities = usePolling(api.listEntities);
  const jobs = usePolling(api.listLabJobs);
  const [selectedId, setSelectedId] = useState(null);
  const error = entities.error || jobs.error;

  return (
    <main>
      <header>
        <h1>Breeding web app</h1>
        <p>React → FastAPI → Postgres + outbox → Pub/Sub → lab scheduler</p>
      </header>
      {error && <p className="err banner">API unreachable: {error}</p>}
      <div className="grid">
        <RegisterForm entities={entities.data} onCreated={entities.refresh} />
        <EntityTable entities={entities.data} selectedId={selectedId} onSelect={setSelectedId} />
        <PedigreePanel entityId={selectedId} entities={entities.data} />
        <LabJobs jobs={jobs.data} />
      </div>
    </main>
  );
}
