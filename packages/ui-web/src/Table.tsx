export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => React.ReactNode;
}

/** Section 9.11 point 6: a real table component, never a raw <table> on a page. */
export function Table<T extends { id: string }>({
  columns,
  rows,
  emptyMessage,
  caption,
}: {
  columns: Column<T>[];
  rows: T[];
  emptyMessage: string;
  caption?: string;
}) {
  if (rows.length === 0) {
    return (
      <div className="rounded-card bg-surface-0 p-10 text-center text-ink-muted">{emptyMessage}</div>
    );
  }
  return (
    <div className="overflow-x-auto rounded-card border border-outline">
      <table className="w-full text-left text-sm">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead className="sticky top-0 bg-surface-2 text-ink-muted">
          <tr>
            {columns.map((c) => (
              <th key={c.key} scope="col" className="px-4 py-3 font-medium">
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-t border-outline odd:bg-surface-0 even:bg-surface-1">
              {columns.map((c) => (
                <td key={c.key} className="px-4 py-3 text-ink">
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
