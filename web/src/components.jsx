export function StatusBadge({ status }) {
  return <span className={`badge ${status}`}>{status.replace("_", " ")}</span>;
}

export function ErrorBox({ error }) {
  if (!error) return null;
  return (
    <div className="error">
      {error.message}
      {error.details?.length > 0 && (
        <ul>{error.details.map((d, i) => <li key={i}>{d.field}: {d.message}</li>)}</ul>
      )}
    </div>
  );
}
