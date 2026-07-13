// Exportação client-side para CSV (bônus 7.7) — sem depender do backend.

export function downloadCsv(filename: string, rows: (string | number)[][]): void {
  const body = rows
    .map((r) => r.map((c) => (typeof c === "number" ? String(c) : `"${String(c).replace(/"/g, '""')}"`)).join(","))
    .join("\n");
  const blob = new Blob([body], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
