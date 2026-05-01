import "./land-dispute.tailwind.css";

export type LandModeChoice = "assistant" | "dispute";

interface LandModeChooserProps {
  onChoose: (mode: LandModeChoice) => void;
}

export function LandModeChooser({ onChoose }: LandModeChooserProps) {
  return (
    <div
      className="land-mode-chooser ld:relative ld:z-[5] ld:flex ld:h-full ld:min-h-0 ld:w-full ld:flex-col ld:items-center ld:justify-center ld:px-4 ld:py-6 md:ld:px-10"
      role="dialog"
      aria-modal="true"
      aria-labelledby="land-mode-title"
    >
      <div className="land-chooser-head ld:mb-8 ld:max-w-3xl ld:text-center">
        <p className="ld:mb-2 ld:text-sm ld:font-medium ld:uppercase ld:tracking-[0.2em] ld:text-teal-300/90">
          Land assistant
        </p>
        <h1
          id="land-mode-title"
          className="ld:bg-gradient-to-r ld:from-white ld:via-teal-100 ld:to-cyan-200 ld:bg-clip-text ld:text-3xl ld:font-bold ld:tracking-tight ld:text-transparent md:ld:text-4xl lg:ld:text-5xl"
        >
          How do you want to proceed?
        </h1>
        <p className="ld:mt-3 ld:text-base ld:text-slate-400 md:ld:text-lg">
          Pick an experience — you can return here anytime from the workspace.
        </p>
      </div>

      <div className="land-chooser-grid ld:grid ld:w-full ld:max-w-6xl ld:grid-cols-1 ld:gap-6 md:ld:grid-cols-2 md:ld:gap-8 lg:ld:gap-10">
        <button
          type="button"
          onClick={() => onChoose("assistant")}
          className="land-chooser-card land-chooser-card--map ld:group ld:relative ld:flex ld:min-h-[260px] ld:flex-col ld:items-start ld:justify-between ld:overflow-hidden ld:rounded-3xl ld:border ld:p-8 ld:text-left ld:transition-all ld:duration-300 md:ld:min-h-[320px] lg:ld:min-h-[360px] lg:ld:p-10"
        >
          <span className="land-chooser-glow land-chooser-glow--teal" aria-hidden />
          <div className="ld:relative">
            <span className="land-chooser-icon land-chooser-icon--teal">
              <svg className="ld:h-10 ld:w-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
              </svg>
            </span>
            <h2 className="ld:mt-6 ld:text-2xl ld:font-bold ld:text-white md:ld:text-3xl">Document &amp; map</h2>
            <p className="ld:mt-3 ld:max-w-sm ld:text-sm ld:leading-relaxed ld:text-slate-400 md:ld:text-base">
              Upload PDFs, run AI analysis, search records, and view the parcel on an interactive map.
            </p>
          </div>
          <span className="land-chooser-cta land-chooser-cta--teal ld:relative ld:inline-flex ld:items-center ld:gap-2">
            Open workspace
            <svg className="ld:h-5 ld:w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
            </svg>
          </span>
        </button>

        <button
          type="button"
          onClick={() => onChoose("dispute")}
          className="land-chooser-card land-chooser-card--dispute ld:group ld:relative ld:flex ld:min-h-[260px] ld:flex-col ld:items-start ld:justify-between ld:overflow-hidden ld:rounded-3xl ld:border ld:p-8 ld:text-left ld:transition-all ld:duration-300 md:ld:min-h-[320px] lg:ld:min-h-[360px] lg:ld:p-10"
        >
          <span className="land-chooser-glow land-chooser-glow--violet" aria-hidden />
          <div className="ld:relative">
            <span className="land-chooser-icon land-chooser-icon--violet">
              <svg className="ld:h-10 ld:w-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
              </svg>
            </span>
            <h2 className="ld:mt-6 ld:text-2xl ld:font-bold ld:text-white md:ld:text-3xl">Land dispute</h2>
            <p className="ld:mt-3 ld:max-w-sm ld:text-sm ld:leading-relaxed ld:text-slate-400 md:ld:text-base">
              Party A &amp; B side by side, comparison table, scores, and recommended legal steps.
            </p>
          </div>
          <span className="land-chooser-cta land-chooser-cta--violet ld:relative ld:inline-flex ld:items-center ld:gap-2">
            Open dashboard
            <svg className="ld:h-5 ld:w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
            </svg>
          </span>
        </button>
      </div>
    </div>
  );
}
