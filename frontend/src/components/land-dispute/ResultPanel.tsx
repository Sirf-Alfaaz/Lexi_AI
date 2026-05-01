import type { DisputeResultModel } from "./types";

export interface ResultPanelProps {
  result: DisputeResultModel;
}

/** Two-digit style: 00–99, or 100 as three digits */
function formatScoreDisplay(n: number): string {
  const v = Math.max(0, Math.min(100, Math.round(n)));
  if (v >= 100) return "100";
  return String(v).padStart(2, "0");
}

export function ResultPanel({ result }: ResultPanelProps) {
  const {
    scores,
    partyALabel,
    partyBLabel,
    probableOwner,
    confidencePct,
    reasoning,
    legalSteps,
    scoreJustificationA,
    scoreJustificationB,
  } = result;

  return (
    <section className="ld:rounded-2xl ld:border ld:border-teal-500/25 ld:bg-gradient-to-br ld:from-slate-950/90 ld:to-teal-950/40 ld:p-6 ld:shadow-xl ld:backdrop-blur-sm md:ld:p-8 lg:ld:p-10">
      <div className="ld:flex ld:flex-col ld:gap-8 lg:ld:flex-row lg:ld:items-start lg:ld:justify-between lg:ld:gap-6">
        <div className="ld:flex-1">
          <h2 className="ld:text-xl ld:font-semibold ld:text-white md:ld:text-2xl">Dispute resolution summary</h2>
          <p className="ld:mt-2 ld:text-sm ld:leading-relaxed ld:text-slate-400 md:ld:text-base">
            Weighted from document extraction, stamps, and cross-field checks.
          </p>

          <div className="ld:mt-6 ld:grid ld:grid-cols-2 ld:gap-4 md:ld:gap-6">
            <div className="ld:rounded-xl ld:border ld:border-emerald-500/25 ld:bg-emerald-950/30 ld:p-5 md:ld:p-6">
              <p className="ld:line-clamp-2 ld:text-sm ld:font-semibold ld:leading-snug ld:text-emerald-100 md:ld:line-clamp-none md:ld:text-base" title={partyALabel}>
                {partyALabel}
              </p>
              <p className="ld:mt-1 ld:text-xs ld:font-medium ld:uppercase ld:tracking-wide ld:text-emerald-400/80">Score</p>
              <p className="ld:mt-2 ld:text-4xl ld:font-bold ld:tabular-nums ld:tracking-tight ld:text-emerald-200">
                {formatScoreDisplay(scores.partyA)}
              </p>
            </div>
            <div className="ld:rounded-xl ld:border ld:border-violet-500/25 ld:bg-violet-950/30 ld:p-5 md:ld:p-6">
              <p className="ld:line-clamp-2 ld:text-sm ld:font-semibold ld:leading-snug ld:text-violet-100 md:ld:line-clamp-none md:ld:text-base" title={partyBLabel}>
                {partyBLabel}
              </p>
              <p className="ld:mt-1 ld:text-xs ld:font-medium ld:uppercase ld:tracking-wide ld:text-violet-400/80">Score</p>
              <p className="ld:mt-2 ld:text-4xl ld:font-bold ld:tabular-nums ld:tracking-tight ld:text-violet-200">
                {formatScoreDisplay(scores.partyB)}
              </p>
            </div>
          </div>

          <div className="ld:mt-6 ld:rounded-xl ld:border ld:border-white/10 ld:bg-slate-900/50 ld:p-5 md:ld:p-6">
            <p className="ld:text-xs ld:font-semibold ld:uppercase ld:tracking-wider ld:text-slate-500">Most probable owner</p>
            <p className="ld:mt-2 ld:text-2xl ld:font-semibold ld:text-white md:ld:text-3xl">{probableOwner}</p>
            <div className="ld:mt-3 ld:flex ld:items-center ld:gap-3">
              <div className="ld:h-2 ld:flex-1 ld:overflow-hidden ld:rounded-full ld:bg-slate-800">
                <div
                  className="ld:h-full ld:rounded-full ld:bg-gradient-to-r ld:from-teal-500 ld:to-emerald-400 ld:transition-all"
                  style={{ width: `${Math.min(100, Math.max(0, confidencePct))}%` }}
                />
              </div>
              <span className="ld:text-sm ld:font-semibold ld:tabular-nums ld:text-teal-300">{confidencePct}%</span>
            </div>
            <p className="ld:mt-1 ld:text-xs ld:text-slate-500">Model confidence in ownership inference</p>
          </div>
        </div>

        <div className="ld:w-full ld:flex-1 lg:ld:max-w-xl">
          <h3 className="ld:text-base ld:font-semibold ld:text-slate-300 md:ld:text-lg">Reasoning</h3>
          <p className="ld:mt-3 ld:text-sm ld:leading-relaxed ld:text-slate-400 md:ld:text-base">{reasoning}</p>

          <h3 className="ld:mt-8 ld:text-base ld:font-semibold ld:text-slate-300 md:ld:text-lg">Recommended legal steps</h3>
          <ol className="ld:mt-4 ld:list-decimal ld:space-y-3 ld:pl-5 ld:text-sm ld:leading-relaxed ld:text-slate-400 md:ld:text-base">
            {legalSteps.map((step, i) => (
              <li key={i} className="ld:leading-relaxed">
                {step}
              </li>
            ))}
          </ol>

          <h3 className="ld:mt-8 ld:text-base ld:font-semibold ld:text-slate-300 md:ld:text-lg">Score justification</h3>
          <ul className="ld:mt-3 ld:space-y-2 ld:text-sm ld:leading-relaxed ld:text-slate-400 md:ld:text-base">
            <li><span className="ld:font-semibold ld:text-emerald-200">Party A:</span> {scoreJustificationA}</li>
            <li><span className="ld:font-semibold ld:text-violet-200">Party B:</span> {scoreJustificationB}</li>
          </ul>
        </div>
      </div>
    </section>
  );
}
