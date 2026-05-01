import type { ComparisonRow } from "./types";

export interface ComparisonTableProps {
  rows: ComparisonRow[];
}

function rowBg(status: ComparisonRow["status"]): string {
  switch (status) {
    case "match":
      return "ld:bg-emerald-950/35";
    case "mismatch":
      return "ld:bg-red-950/40";
    case "partial":
      return "ld:bg-amber-950/30";
    default:
      return "ld:bg-slate-900/30";
  }
}

function cellText(status: ComparisonRow["status"], isValue: boolean): string {
  if (status === "match") return isValue ? "ld:text-emerald-200" : "ld:text-emerald-100";
  if (status === "mismatch") return isValue ? "ld:text-red-200" : "ld:text-red-100";
  return "ld:text-amber-100";
}

export function ComparisonTable({ rows }: ComparisonTableProps) {
  return (
    <section className="ld:overflow-hidden ld:rounded-2xl ld:border ld:border-white/10 ld:bg-slate-950/60 ld:shadow-xl ld:backdrop-blur-sm">
      <div className="ld:border-b ld:border-white/10 ld:px-6 ld:py-5 md:ld:px-8 md:ld:py-6">
        <h2 className="ld:text-lg ld:font-semibold ld:text-white md:ld:text-xl">Field comparison</h2>
        <p className="ld:mt-2 ld:text-sm ld:leading-relaxed ld:text-slate-400 md:ld:text-base">
          Matches are highlighted in green; mismatches in red; partial overlap in amber.
        </p>
      </div>
      <div className="ld:overflow-x-auto">
        <table className="ld:w-full ld:border-collapse ld:text-left ld:text-sm md:ld:text-base">
          <thead>
            <tr className="ld:border-b ld:border-white/10 ld:bg-slate-900/80">
              <th className="ld:px-5 ld:py-4 ld:font-semibold ld:text-slate-300 md:ld:px-6 md:ld:py-5">Field</th>
              <th className="ld:px-5 ld:py-4 ld:font-semibold ld:text-emerald-200/90 md:ld:px-6 md:ld:py-5">Party A</th>
              <th className="ld:px-5 ld:py-4 ld:font-semibold ld:text-violet-200/90 md:ld:px-6 md:ld:py-5">Party B</th>
              <th className="ld:px-5 ld:py-4 ld:font-semibold ld:text-slate-400 md:ld:px-6 md:ld:py-5">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.field} className={`ld:border-b ld:border-white/5 ${rowBg(row.status)}`}>
                <td className="ld:px-5 ld:py-4 ld:font-medium ld:text-slate-200 md:ld:px-6 md:ld:py-5">{row.field}</td>
                <td className={`ld:px-5 ld:py-4 ld:font-mono ld:text-xs sm:ld:text-sm md:ld:text-base ${cellText(row.status, true)}`}>
                  {row.valueA}
                </td>
                <td className={`ld:px-5 ld:py-4 ld:font-mono ld:text-xs sm:ld:text-sm md:ld:text-base ${cellText(row.status, true)}`}>
                  {row.valueB}
                </td>
                <td className="ld:px-5 ld:py-4 md:ld:px-6 md:ld:py-5">
                  <span
                    className={`ld:inline-flex ld:rounded-full ld:px-2.5 ld:py-0.5 ld:text-xs ld:font-semibold ld:uppercase ld:tracking-wide ${
                      row.status === "match"
                        ? "ld:bg-emerald-500/25 ld:text-emerald-200"
                        : row.status === "mismatch"
                          ? "ld:bg-red-500/25 ld:text-red-200"
                          : "ld:bg-amber-500/20 ld:text-amber-200"
                    }`}
                  >
                    {row.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
