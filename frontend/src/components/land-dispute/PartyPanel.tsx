import { useRef } from "react";
import type { BhulekhFetchedData, BhulekhOfficialParsed, ExtractedParcelData, UploadedDoc } from "./types";

const flagStyles: Record<string, string> = {
  Mismatch: "ld:bg-amber-500/15 ld:text-amber-200 ld:border-amber-500/35",
  "Stamp Fraud": "ld:bg-red-500/20 ld:text-red-200 ld:border-red-500/40",
  "Signature Anomaly": "ld:bg-orange-500/15 ld:text-orange-200 ld:border-orange-500/35",
  "Date Inconsistency": "ld:bg-rose-500/15 ld:text-rose-200 ld:border-rose-500/35",
  "Date Anomaly": "ld:bg-orange-500/15 ld:text-orange-200 ld:border-orange-500/35",
  "Ownership Mismatch": "ld:bg-amber-500/15 ld:text-amber-200 ld:border-amber-500/35",
  "Duplicate Khasra With Multiple Owners": "ld:bg-purple-500/15 ld:text-purple-200 ld:border-purple-500/35",
  "Missing Required Fields": "ld:bg-slate-500/20 ld:text-slate-200 ld:border-slate-500/35",
  "Invalid Document Structure": "ld:bg-slate-500/20 ld:text-slate-200 ld:border-slate-500/35",
};

function flagClass(flag: string): string {
  return flagStyles[flag] ?? "ld:bg-slate-500/20 ld:text-slate-200 ld:border-slate-500/35";
}

export interface PartyPanelProps {
  partyLabel: string;
  accent: "emerald" | "violet";
  documents: UploadedDoc[];
  extracted: ExtractedParcelData | null;
  flags: string[];
  onSelectFiles: (files: FileList | null) => void;
  uploading?: boolean;
  uploadError?: string | null;
  processingStatus?: string | null;
  bhulekhData?: BhulekhFetchedData | null;
  bhulekhMatch?: boolean | null;
  bhulekhOfficialParsed?: BhulekhOfficialParsed | null;
  forgeryExplanation?: string;
  onSelectOfficialRecord?: (files: FileList | null) => void;
  onSelectHouseTax?: (files: FileList | null) => void;
  onSelectElectricity?: (files: FileList | null) => void;
  houseTaxFileName?: string | null;
  electricityFileName?: string | null;
  needsSupportingDocs?: boolean;
}

export function PartyPanel({
  partyLabel,
  accent,
  documents,
  extracted,
  flags,
  onSelectFiles,
  uploading = false,
  uploadError = null,
  processingStatus = null,
  bhulekhData = null,
  bhulekhMatch = null,
  bhulekhOfficialParsed = null,
  forgeryExplanation = "",
  onSelectHouseTax,
  onSelectElectricity,
  houseTaxFileName = null,
  electricityFileName = null,
  needsSupportingDocs = false,
}: PartyPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const taxRef = useRef<HTMLInputElement>(null);
  const elecRef = useRef<HTMLInputElement>(null);

  const shell =
    accent === "emerald"
      ? "ld:border-emerald-500/35 ld:bg-gradient-to-br ld:from-emerald-950/50 ld:to-slate-950/80 ld:shadow-emerald-900/20"
      : "ld:border-violet-500/35 ld:bg-gradient-to-br ld:from-violet-950/50 ld:to-slate-950/80 ld:shadow-violet-900/20";

  const chip =
    accent === "emerald"
      ? "ld:bg-emerald-500/20 ld:text-emerald-200 ld:border-emerald-500/30"
      : "ld:bg-violet-500/20 ld:text-violet-200 ld:border-violet-500/30";

  return (
    <section
      className={`land-party-panel ld:flex ld:flex-col ld:rounded-2xl ld:border ld:backdrop-blur-sm ld:shadow-xl ${shell}`}
      aria-labelledby={`party-heading-${partyLabel.replace(/\s/g, "")}`}
    >
      <header className="ld:flex ld:shrink-0 ld:items-center ld:justify-between ld:gap-3 ld:border-b ld:border-white/10 ld:px-5 ld:py-4">
        <div className="ld:flex ld:items-center ld:gap-3">
          <span
            className={`ld:inline-flex ld:items-center ld:rounded-full ld:border ld:px-3 ld:py-1 ld:text-xs ld:font-semibold ld:uppercase ld:tracking-wide ${chip}`}
          >
            {partyLabel}
          </span>
          <h2
            id={`party-heading-${partyLabel.replace(/\s/g, "")}`}
            className="ld:line-clamp-2 ld:text-lg ld:font-semibold ld:leading-snug ld:text-white ld:tracking-tight sm:ld:line-clamp-none"
            title={extracted?.owner?.trim() || undefined}
          >
            {(extracted?.ownerDisplay || extracted?.owner || "").trim() || "Submitted records"}
          </h2>
        </div>
        <div className="ld:flex ld:items-center ld:gap-2">
          <input
            ref={inputRef}
            type="file"
            accept="application/pdf,.pdf"
            className="ld:hidden"
            multiple
            onChange={(e) => {
              onSelectFiles(e.target.files);
              e.target.value = "";
            }}
          />
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={uploading}
            className="ld:inline-flex ld:items-center ld:gap-2 ld:rounded-xl ld:bg-white/10 ld:px-4 ld:py-2.5 ld:text-sm ld:font-medium ld:text-white ld:ring-1 ld:ring-white/15 ld:transition hover:ld:bg-white/15 focus-visible:ld:outline focus-visible:ld:outline-2 focus-visible:ld:outline-offset-2 focus-visible:ld:outline-teal-400 disabled:ld:opacity-50"
          >
            <svg className="ld:h-4 ld:w-4 ld:opacity-90" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
            </svg>
            {uploading ? "Processing…" : "Upload document"}
          </button>
        </div>
      </header>

      <div className="land-party-panel__body ld:flex ld:flex-col ld:gap-4 ld:p-5">
        {uploadError && (
          <div className="ld:rounded-xl ld:border ld:border-red-500/40 ld:bg-red-950/40 ld:px-3 ld:py-2 ld:text-sm ld:text-red-200">
            {uploadError}
          </div>
        )}
        {(uploading || processingStatus) && (
          <div className="ld:rounded-xl ld:border ld:border-teal-500/30 ld:bg-teal-950/25 ld:px-3 ld:py-2 ld:text-sm ld:text-teal-100">
            {processingStatus || "Processing..."}
          </div>
        )}
        <div>
          <h3 className="ld:mb-2 ld:text-xs ld:font-semibold ld:uppercase ld:tracking-wider ld:text-slate-400">
            Documents ({documents.length})
          </h3>
          {documents.length === 0 ? (
            <p className="ld:rounded-xl ld:border ld:border-dashed ld:border-white/15 ld:bg-slate-950/40 ld:px-4 ld:py-10 ld:text-center ld:text-sm ld:leading-relaxed ld:text-slate-500 ld:min-h-[140px] ld:flex ld:items-center ld:justify-center">
              No files yet. Upload PDF land records to extract party data.
            </p>
          ) : (
            <ul className="ld:space-y-2">
              {documents.map((doc) => (
                <li
                  key={doc.id}
                  className="ld:flex ld:items-center ld:justify-between ld:gap-3 ld:rounded-xl ld:border ld:border-white/10 ld:bg-slate-900/50 ld:px-3 ld:py-2.5"
                >
                  <div className="ld:flex ld:min-w-0 ld:items-center ld:gap-2">
                    <span className="ld:flex ld:h-8 ld:w-8 ld:shrink-0 ld:items-center ld:justify-center ld:rounded-lg ld:bg-white/5">
                      <svg className="ld:h-4 ld:w-4 ld:text-slate-300" fill="currentColor" viewBox="0 0 24 24" aria-hidden>
                        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" />
                      </svg>
                    </span>
                    <div className="ld:min-w-0">
                      <p className="ld:truncate ld:text-sm ld:font-medium ld:text-slate-100">{doc.name}</p>
                      <p className="ld:text-xs ld:text-slate-500">{doc.uploadedAt}</p>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="ld:rounded-xl ld:border ld:border-white/10 ld:bg-slate-950/50 ld:p-4">
          <h3 className="ld:mb-3 ld:text-xs ld:font-semibold ld:uppercase ld:tracking-wider ld:text-slate-400">
            Extracted data
          </h3>
          {extracted ? (
            <dl className="ld:grid ld:grid-cols-1 ld:gap-3 ld:sm:grid-cols-2 lg:ld:grid-cols-3">
              {(extracted.district || extracted.tehsil || extracted.village || extracted.khata_number) && (
                <div className="ld:sm:col-span-2 lg:ld:col-span-3">
                  <dt className="ld:text-xs ld:text-slate-500">Location (Bhulekh / खतौनी)</dt>
                  <dd className="ld:mt-0.5 ld:text-sm ld:font-medium ld:text-slate-200">
                    {[extracted.district, extracted.tehsil, extracted.village].filter(Boolean).join(" · ")}
                    {extracted.khata_number ? ` · खाता ${extracted.khata_number}` : ""}
                  </dd>
                </div>
              )}
              {extracted.ownership_entries && extracted.ownership_entries.length > 0 ? (
                <div className="ld:sm:col-span-2 lg:ld:col-span-3">
                  <dt className="ld:text-xs ld:text-slate-500">Co-owners & land division (खतौनी)</dt>
                  <dd className="ld:mt-2 ld:overflow-x-auto">
                    <table className="ld:w-full ld:border-collapse ld:text-left ld:text-sm">
                      <thead>
                        <tr className="ld:border-b ld:border-white/10 ld:text-xs ld:font-semibold ld:text-slate-400">
                          <th className="ld:py-1.5 ld:pr-3 ld:font-medium">Owner</th>
                          <th className="ld:py-1.5 ld:pr-3 ld:font-medium">Father / guardian</th>
                          <th className="ld:py-1.5 ld:pr-3 ld:font-medium">Share (हिस्सा)</th>
                          <th className="ld:py-1.5 ld:pr-0 ld:font-medium">Area (हे०)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {extracted.ownership_entries.map((row, i) => (
                          <tr key={i} className="ld:border-b ld:border-white/5 ld:text-white">
                            <td className="ld:py-2 ld:pr-3 ld:align-top ld:font-medium">{row.owner.trim() || "—"}</td>
                            <td className="ld:py-2 ld:pr-3 ld:align-top ld:text-slate-200">{row.father.trim() || "—"}</td>
                            <td className="ld:py-2 ld:pr-3 ld:align-top ld:font-mono ld:text-teal-100">
                              {row.share.trim() || "—"}
                            </td>
                            <td className="ld:py-2 ld:align-top ld:font-mono ld:text-slate-100">
                              {row.area_ha.trim() ? `${row.area_ha.trim()} ha` : "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </dd>
                </div>
              ) : (
                <>
                  <div>
                    <dt className="ld:text-xs ld:text-slate-500">Owner</dt>
                    <dd className="ld:mt-0.5 ld:text-sm ld:font-medium ld:text-white">
                      {(extracted.ownerDisplay || extracted.owner).trim() || "—"}
                    </dd>
                  </div>
                  {(extracted.father || extracted.fatherDisplay) && (
                    <div>
                      <dt className="ld:text-xs ld:text-slate-500">Father</dt>
                      <dd className="ld:mt-0.5 ld:text-sm ld:font-medium ld:text-white">
                        {(extracted.fatherDisplay || extracted.father).trim() || "—"}
                      </dd>
                    </div>
                  )}
                </>
              )}
              <div>
                <dt className="ld:text-xs ld:text-slate-500">Khasra</dt>
                <dd className="ld:mt-0.5 ld:text-sm ld:font-medium ld:text-teal-100">{extracted.khasra}</dd>
              </div>
              <div>
                <dt className="ld:text-xs ld:text-slate-500">
                  {extracted.ownership_entries && extracted.ownership_entries.length > 0
                    ? "Total area (गाटे का कुल)"
                    : "Area"}
                </dt>
                <dd className="ld:mt-0.5 ld:text-sm ld:font-medium ld:text-white">{extracted.area}</dd>
              </div>
            </dl>
          ) : (
            <div className="ld:rounded-lg ld:border ld:border-dashed ld:border-white/10 ld:bg-slate-950/30 ld:px-4 ld:py-8 ld:text-center ld:text-sm ld:text-slate-500">
              Upload a document to populate owner, khasra, and area.
            </div>
          )}
        </div>

        <div>
          <h3 className="ld:mb-2 ld:text-xs ld:font-semibold ld:uppercase ld:tracking-wider ld:text-slate-400">
            Official verification
          </h3>
          <p className="ld:text-xs ld:leading-relaxed ld:text-slate-400">
            After both parties upload documents, the app asks whether the land is registered on UP Bhulekh and verifies from there.
          </p>
          {needsSupportingDocs && (
            <div className="ld:mt-3 ld:rounded-xl ld:border ld:border-amber-500/35 ld:bg-amber-950/20 ld:p-3">
              <p className="ld:text-xs ld:text-amber-200">
                Official Bhulekh registration not available. Upload both documents: House Tax Receipt and Electricity Bill.
              </p>
              <div className="ld:mt-2 ld:flex ld:flex-wrap ld:gap-2">
                <input
                  ref={taxRef}
                  type="file"
                  accept="application/pdf,.pdf,image/*"
                  className="ld:hidden"
                  onChange={(e) => {
                    onSelectHouseTax?.(e.target.files);
                    e.target.value = "";
                  }}
                />
                <button
                  type="button"
                  onClick={() => taxRef.current?.click()}
                  className="ld:inline-flex ld:items-center ld:rounded-xl ld:bg-white/10 ld:px-3 ld:py-2 ld:text-xs ld:text-white ld:ring-1 ld:ring-white/15"
                >
                  Upload House Tax Receipt
                </button>
                <input
                  ref={elecRef}
                  type="file"
                  accept="application/pdf,.pdf,image/*"
                  className="ld:hidden"
                  onChange={(e) => {
                    onSelectElectricity?.(e.target.files);
                    e.target.value = "";
                  }}
                />
                <button
                  type="button"
                  onClick={() => elecRef.current?.click()}
                  className="ld:inline-flex ld:items-center ld:rounded-xl ld:bg-white/10 ld:px-3 ld:py-2 ld:text-xs ld:text-white ld:ring-1 ld:ring-white/15"
                >
                  Upload Electricity Bill
                </button>
              </div>
              {(houseTaxFileName || electricityFileName) && (
                <p className="ld:mt-1 ld:text-xs ld:text-slate-300">
                  {houseTaxFileName ? `House Tax: ${houseTaxFileName}` : "House Tax: missing"} |{" "}
                  {electricityFileName ? `Electricity: ${electricityFileName}` : "Electricity: missing"}
                </p>
              )}
            </div>
          )}
        </div>

        <div>
          <h3 className="ld:mb-2 ld:text-xs ld:font-semibold ld:uppercase ld:tracking-wider ld:text-slate-400">
            UP Bhulekh website fetch
          </h3>
          {bhulekhData ? (
            <dl className="ld:grid ld:grid-cols-1 ld:gap-2 ld:sm:grid-cols-2">
              <div>
                <dt className="ld:text-xs ld:text-slate-500">Owner (Bhulekh)</dt>
                <dd className="ld:text-sm ld:text-slate-200">{bhulekhData.owner || "—"}</dd>
              </div>
              <div>
                <dt className="ld:text-xs ld:text-slate-500">Khasra (Bhulekh)</dt>
                <dd className="ld:text-sm ld:text-slate-200">{bhulekhData.khasra || "—"}</dd>
              </div>
              <div>
                <dt className="ld:text-xs ld:text-slate-500">Area (Bhulekh)</dt>
                <dd className="ld:text-sm ld:text-slate-200">{bhulekhData.area || "—"}</dd>
              </div>
              <div>
                <dt className="ld:text-xs ld:text-slate-500">Search mode</dt>
                <dd className="ld:text-sm ld:text-slate-200">{bhulekhData.search_mode || "—"}</dd>
              </div>
              <div className="ld:sm:col-span-2">
                <dt className="ld:text-xs ld:text-slate-500">Bhulekh match</dt>
                <dd className="ld:text-sm ld:text-slate-200">
                  {bhulekhMatch === null ? "Not available" : bhulekhMatch ? "Matched with uploaded document" : "Mismatch with uploaded document"}
                </dd>
              </div>
            </dl>
          ) : (
            <p className="ld:text-sm ld:text-slate-500">No Bhulekh fetch details yet.</p>
          )}
        </div>

        <div className="ld:rounded-xl ld:border ld:border-white/10 ld:bg-slate-950/50 ld:p-4">
          <h3 className="ld:mb-3 ld:text-xs ld:font-semibold ld:uppercase ld:tracking-wider ld:text-slate-400">
            Official Bhulekh PDF (parsed)
          </h3>
          {bhulekhOfficialParsed ? (
            <div className="ld:space-y-3">
              <dl className="ld:grid ld:grid-cols-1 ld:gap-3 ld:sm:grid-cols-2 lg:ld:grid-cols-3">
                {(bhulekhOfficialParsed.district || bhulekhOfficialParsed.tehsil || bhulekhOfficialParsed.village || bhulekhOfficialParsed.khata_number) && (
                  <div className="ld:sm:col-span-2 lg:ld:col-span-3">
                    <dt className="ld:text-xs ld:text-slate-500">Location (official)</dt>
                    <dd className="ld:mt-0.5 ld:text-sm ld:font-medium ld:text-slate-200">
                      {[bhulekhOfficialParsed.district, bhulekhOfficialParsed.tehsil, bhulekhOfficialParsed.village].filter(Boolean).join(" · ")}
                      {bhulekhOfficialParsed.khata_number ? ` · खाता ${bhulekhOfficialParsed.khata_number}` : ""}
                    </dd>
                  </div>
                )}
                <div>
                  <dt className="ld:text-xs ld:text-slate-500">Khasra (official)</dt>
                  <dd className="ld:mt-0.5 ld:text-sm ld:font-medium ld:text-teal-100">
                    {(bhulekhOfficialParsed.khasra || "").trim() || "—"}
                  </dd>
                </div>
                <div>
                  <dt className="ld:text-xs ld:text-slate-500">Total area (official)</dt>
                  <dd className="ld:mt-0.5 ld:text-sm ld:font-medium ld:text-white">
                    {(bhulekhOfficialParsed.area || "").trim() || "—"}
                  </dd>
                </div>
                <div>
                  <dt className="ld:text-xs ld:text-slate-500">Owners (official)</dt>
                  <dd className="ld:mt-0.5 ld:text-sm ld:font-medium ld:text-white">
                    {(bhulekhOfficialParsed.owner_display || bhulekhOfficialParsed.owner || "").trim() || "—"}
                  </dd>
                </div>
              </dl>

              {Array.isArray(bhulekhOfficialParsed.ownership_entries) && bhulekhOfficialParsed.ownership_entries.length > 0 && (
                <div>
                  <p className="ld:text-xs ld:text-slate-500">Co-owners table (official)</p>
                  <div className="ld:mt-2 ld:overflow-x-auto">
                    <table className="ld:w-full ld:border-collapse ld:text-left ld:text-sm">
                      <thead>
                        <tr className="ld:border-b ld:border-white/10 ld:text-xs ld:font-semibold ld:text-slate-400">
                          <th className="ld:py-1.5 ld:pr-3 ld:font-medium">Owner</th>
                          <th className="ld:py-1.5 ld:pr-3 ld:font-medium">Father / guardian</th>
                          <th className="ld:py-1.5 ld:pr-3 ld:font-medium">Share (हिस्सा)</th>
                          <th className="ld:py-1.5 ld:pr-0 ld:font-medium">Area (हे०)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {bhulekhOfficialParsed.ownership_entries.map((row, i) => (
                          <tr key={i} className="ld:border-b ld:border-white/5 ld:text-white">
                            <td className="ld:py-2 ld:pr-3 ld:align-top ld:font-medium">{(row.owner || "").trim() || "—"}</td>
                            <td className="ld:py-2 ld:pr-3 ld:align-top ld:text-slate-200">{(row.father || "").trim() || "—"}</td>
                            <td className="ld:py-2 ld:pr-3 ld:align-top ld:font-mono ld:text-teal-100">{(row.share || "").trim() || "—"}</td>
                            <td className="ld:py-2 ld:align-top ld:font-mono ld:text-slate-100">
                              {(row.area_ha || "").trim() ? `${String(row.area_ha).trim()} ha` : "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <p className="ld:text-sm ld:text-slate-500">
              Official PDF could not be fetched/parsed yet. (This appears once Bhulekh verification succeeds and provides a PDF.)
            </p>
          )}
        </div>

        <div>
          <h3 className="ld:mb-2 ld:text-xs ld:font-semibold ld:uppercase ld:tracking-wider ld:text-slate-400">
            Forgery & integrity flags
          </h3>
          {flags.length === 0 ? (
            <p className="ld:text-sm ld:text-slate-500">No flags for the latest document.</p>
          ) : (
            <div className="ld:flex ld:flex-wrap ld:gap-2">
              {flags.map((flag) => (
                <span
                  key={flag}
                  className={`ld:inline-flex ld:items-center ld:rounded-full ld:border ld:px-3 ld:py-1 ld:text-xs ld:font-medium ${flagClass(flag)}`}
                >
                  {flag}
                </span>
              ))}
            </div>
          )}
          {forgeryExplanation && (
            <p className="ld:mt-2 ld:text-xs ld:leading-relaxed ld:text-slate-400">{forgeryExplanation}</p>
          )}
        </div>
      </div>
    </section>
  );
}
