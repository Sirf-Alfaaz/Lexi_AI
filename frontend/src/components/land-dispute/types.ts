/** Legacy demo labels; server may return any string from /forgery/check */
export type ForgeryFlag = "Mismatch" | "Stamp Fraud" | "Signature Anomaly" | "Date Inconsistency";

/** One co-owner row from UP Khatauni (नाम / पिता, हिस्सा, क्षेत्रफल) */
export interface OwnershipEntryRow {
  owner: string;
  father: string;
  share: string;
  area_ha: string;
}

export interface ExtractedParcelData {
  /** Native script from OCR (e.g. Devanagari) */
  owner: string;
  /** Romanized + (native) when Hindi; prefer for display */
  ownerDisplay: string;
  father: string;
  fatherDisplay: string;
  khasra: string;
  /** Total gata area (गाटे का कुल क्षेत्रफल) when present */
  area: string;
  /** Per-row co-owners with share + area when parsed from Khatauni */
  ownership_entries?: OwnershipEntryRow[];
  /** From UP Khatauni header when detected */
  district?: string;
  tehsil?: string;
  village?: string;
  khata_number?: string;
}

export interface UploadedDoc {
  id: string;
  name: string;
  uploadedAt: string;
}

export interface BhulekhFetchedData {
  owner: string;
  khasra: string;
  area: string;
  search_mode?: string;
  source?: "manual_bhulekh_pdf" | "scraper";
}

export interface BhulekhOfficialParsed {
  owner?: string;
  owner_display?: string;
  father?: string;
  father_display?: string;
  khasra?: string;
  area?: string;
  district?: string;
  tehsil?: string;
  village?: string;
  khata_number?: string;
  ownership_entries?: OwnershipEntryRow[];
  date?: string;
  stamp_id?: string;
}

export interface PartyPanelModel {
  partyKey: "A" | "B";
  title: string;
  accent: "emerald" | "violet";
  documents: UploadedDoc[];
  extracted: ExtractedParcelData | null;
  flags: string[];
}

export type ComparisonStatus = "match" | "mismatch" | "partial";

export interface ComparisonRow {
  field: string;
  valueA: string;
  valueB: string;
  status: ComparisonStatus;
}

export interface DisputeResultModel {
  scores: { partyA: number; partyB: number };
  /** "Party A" until owner is extracted from PDF, then owner name */
  partyALabel: string;
  /** "Party B" until owner is extracted from PDF, then owner name */
  partyBLabel: string;
  probableOwner: string;
  confidencePct: number;
  reasoning: string;
  legalSteps: string[];
  scoreJustificationA: string;
  scoreJustificationB: string;
}
