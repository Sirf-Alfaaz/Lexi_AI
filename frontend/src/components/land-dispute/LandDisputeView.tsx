import { useCallback, useMemo, useState } from "react";
import { ComparisonTable } from "./ComparisonTable";
import { PartyPanel } from "./PartyPanel";
import { ResultPanel } from "./ResultPanel";
import type {
  BhulekhFetchedData,
  BhulekhOfficialParsed,
  ComparisonRow,
  DisputeResultModel,
  ExtractedParcelData,
  UploadedDoc,
} from "./types";
import "./land-dispute.tailwind.css";
import { API_URL as API_BASE } from "../../config";

function newId(): string {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `doc-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function buildComparison(
  a: ExtractedParcelData | null,
  b: ExtractedParcelData | null
): ComparisonRow[] {
  const fields: { key: "owner" | "khasra" | "area"; label: string }[] = [
    { key: "owner", label: "Owner name" },
    { key: "khasra", label: "Khasra number" },
    { key: "area", label: "Land area" },
  ];
  if (!a || !b) {
    return fields.map((f) => ({
      field: f.label,
      valueA:
        f.key === "owner" && a
          ? (a.ownerDisplay || a.owner || "—").trim() || "—"
          : (a?.[f.key] ?? "—"),
      valueB:
        f.key === "owner" && b
          ? (b.ownerDisplay || b.owner || "—").trim() || "—"
          : (b?.[f.key] ?? "—"),
      status: "partial" as const,
    }));
  }
  return fields.map((f) => {
    const va =
      f.key === "owner"
        ? (a.ownerDisplay || a.owner).trim() || "—"
        : String(a[f.key] ?? "").trim();
    const vb =
      f.key === "owner"
        ? (b.ownerDisplay || b.owner).trim() || "—"
        : String(b[f.key] ?? "").trim();
    const match =
      f.key === "owner"
        ? a.owner.trim().toLowerCase() === b.owner.trim().toLowerCase()
        : va.trim().toLowerCase() === vb.trim().toLowerCase();
    return {
      field: f.label,
      valueA: va,
      valueB: vb,
      status: match ? ("match" as const) : ("mismatch" as const),
    };
  });
}

function buildResult(
  a: ExtractedParcelData | null,
  b: ExtractedParcelData | null,
  flagsA: string[],
  flagsB: string[],
  bhulekhA: BhulekhFetchedData | null,
  bhulekhB: BhulekhFetchedData | null,
  bhulekhMatchA: boolean | null,
  bhulekhMatchB: boolean | null,
  officialOwner: string,
  supportDocsA: { houseTax: boolean; electricity: boolean },
  supportDocsB: { houseTax: boolean; electricity: boolean }
): DisputeResultModel {
  const nameA = a?.owner?.trim() || "";
  const nameB = b?.owner?.trim() || "";
  const partyALabel = (a?.ownerDisplay || nameA).trim() || "Party A";
  const partyBLabel = (b?.ownerDisplay || nameB).trim() || "Party B";

  let partyA = 0;
  let partyB = 0;

  if (nameA) {
    partyA = 50;
  }
  if (nameB) {
    partyB = 50;
  }

  if (nameA && nameB) {
    const ownerMatch = nameA.toLowerCase() === nameB.toLowerCase();
    const khasraMatch = (a!.khasra || "").trim() === (b!.khasra || "").trim() && Boolean((a!.khasra || "").trim());
    partyA += ownerMatch ? 8 : 0;
    partyB += ownerMatch ? 8 : 0;
    partyA += khasraMatch ? 5 : -5;
    partyB += khasraMatch ? 5 : -5;
  }

  // Bhulekh owner name comparison is the strongest signal.
  // Use the officialOwner (from parsed PDF) OR the scraper-fetched owner as
  // the ground truth. The scraper owner is available even when PDF parse fails.
  const officialOwnerNorm = normalize(officialOwner || "");
  // Also derive the Bhulekh scraper owner (available even when PDF is not)
  const scraperOwner = normalize(bhulekhA?.owner || bhulekhB?.owner || "");
  // The effective "government truth" owner: prefer PDF-parsed, fallback to scraper
  const govOwner = officialOwnerNorm || scraperOwner;

  // Check which party's owner name matches the government owner
  const govMatchesA = nameA ? checkOwnerMatchesBhulekh(nameA, govOwner) : false;
  const govMatchesB = nameB ? checkOwnerMatchesBhulekh(nameB, govOwner) : false;

  // Apply Bhulekh match bonuses based on owner name match (strongest signal)
  if (govOwner) {
    // Owner name match against official record is the primary Bhulekh signal
    if (govMatchesA && !govMatchesB) {
      partyA += 30;  // Strong bonus for matching official owner
      partyB -= 10;  // Penalty for not matching
    } else if (govMatchesB && !govMatchesA) {
      partyB += 30;
      partyA -= 10;
    } else if (govMatchesA && govMatchesB) {
      // Both match (same owner or substring match) — smaller bonus
      partyA += 15;
      partyB += 15;
    } else {
      // Neither matches — both get a small penalty
      partyA -= 5;
      partyB -= 5;
    }
  } else {
    // No Bhulekh owner available, use the generic bhulekhMatch (khasra/area based)
    if (bhulekhMatchA === true) partyA += 20;
    else if (bhulekhMatchA === false) partyA -= 10;
    if (bhulekhMatchB === true) partyB += 20;
    else if (bhulekhMatchB === false) partyB -= 10;
  }

  if (!bhulekhA) {
    if (supportDocsA.houseTax) partyA += 8;
    if (supportDocsA.electricity) partyA += 8;
  }
  if (!bhulekhB) {
    if (supportDocsB.houseTax) partyB += 8;
    if (supportDocsB.electricity) partyB += 8;
  }

  partyA -= flagsA.length * 12;
  partyB -= flagsB.length * 12;
  partyA = Math.max(0, Math.min(100, partyA));
  partyB = Math.max(0, Math.min(100, partyB));

  let probableOwner = "Undetermined";

  // Determine probable owner: government owner match is the strongest signal
  if (govOwner && (govMatchesA || govMatchesB) && govMatchesA !== govMatchesB) {
    probableOwner = govMatchesA ? partyALabel : partyBLabel;
  }
  if (nameA || nameB) {
    const dispA = (a?.ownerDisplay || nameA).trim();
    const dispB = (b?.ownerDisplay || nameB).trim();
    if (probableOwner === "Undetermined") {
      if (partyA > partyB) probableOwner = dispA || "Undetermined";
      else if (partyB > partyA) probableOwner = dispB || "Undetermined";
      else probableOwner = "Undetermined — scores are tied";
    }
  }

  const hasBoth = Boolean(nameA && nameB);
  const confidencePctBase =
    !nameA && !nameB
      ? 0
      : Math.min(
          96,
          Math.max(0, Math.round(Math.abs(partyA - partyB) * 0.6 + (hasBoth ? 25 : 10)))
        );
  const confidencePct =
    govOwner && probableOwner !== "Undetermined" && (govMatchesA || govMatchesB)
      ? Math.max(confidencePctBase, 92)
      : confidencePctBase;

  const defaultSteps = [
    "Obtain certified copies from the tehsil / DI office for the disputed khasra and linked khatauni.",
    "File or continue proceedings under the relevant state revenue rules; consider survey demarcation (amin report).",
    "Preserve original stamped documents and request forensic examination if stamp fraud is suspected.",
    "Consult local counsel for limitation periods and any pending mutation or acquisition proceedings.",
  ];

  let reasoning: string;
  if (!nameA && !nameB) {
    reasoning = "Upload PDFs for both sides. Scores start at 00 until owner names are extracted from the documents.";
  } else if (nameA && !nameB) {
    reasoning = `Owner identified for Party A (${(a?.ownerDisplay || nameA).trim()}). Upload Party B’s document to compare fields and refine scores.`;
  } else if (!nameA && nameB) {
    reasoning = `Owner identified for Party B (${(b?.ownerDisplay || nameB).trim()}). Upload Party A’s document to compare fields and refine scores.`;
  } else if (govOwner && (govMatchesA || govMatchesB) && govMatchesA !== govMatchesB) {
    reasoning = `Official Bhulekh record owner (${officialOwner || bhulekhA?.owner || bhulekhB?.owner || "unknown"}) matches ${govMatchesA ? "Party A" : "Party B"} more closely. Owner name match against government records is the strongest evidence.`;
  } else if (flagsB.length > flagsA.length) {
    reasoning =
      "Party B’s submissions show more integrity alerts (stamps and dates). Party A’s chain may align better on registry identifiers when khasra variants are treated as adjacent parcels. Automated scoring favors the party with fewer fraud signals and stronger field alignment.";
  } else {
    reasoning =
      "Both parties show named owners; divergence in khasra and area suggests partial overlap or subdivision. Weighting favors the party with fewer forgery flags and closer cadastral match to the extract.";
  }

  const bhulekhBonusA = govOwner
    ? (govMatchesA && !govMatchesB ? "+30" : govMatchesB && !govMatchesA ? "-10" : govMatchesA && govMatchesB ? "+15" : "-5")
    : (bhulekhMatchA === true ? "+20" : bhulekhMatchA === false ? "-10" : "N/A");
  const bhulekhBonusB = govOwner
    ? (govMatchesB && !govMatchesA ? "+30" : govMatchesA && !govMatchesB ? "-10" : govMatchesA && govMatchesB ? "+15" : "-5")
    : (bhulekhMatchB === true ? "+20" : bhulekhMatchB === false ? "-10" : "N/A");

  return {
    scores: { partyA, partyB },
    partyALabel,
    partyBLabel,
    probableOwner,
    confidencePct,
    reasoning,
    legalSteps: defaultSteps,
    scoreJustificationA: [
      `Base ${nameA ? 50 : 0}`,
      govOwner ? `Bhulekh owner match ${bhulekhBonusA}` : (bhulekhA ? `Bhulekh ${bhulekhBonusA}` : "Bhulekh not available"),
      !bhulekhA ? `Support docs +${(supportDocsA.houseTax ? 8 : 0) + (supportDocsA.electricity ? 8 : 0)}` : "Support docs not needed",
      `Forgery penalty -${flagsA.length * 12}`,
    ].join(", "),
    scoreJustificationB: [
      `Base ${nameB ? 50 : 0}`,
      govOwner ? `Bhulekh owner match ${bhulekhBonusB}` : (bhulekhB ? `Bhulekh ${bhulekhBonusB}` : "Bhulekh not available"),
      !bhulekhB ? `Support docs +${(supportDocsB.houseTax ? 8 : 0) + (supportDocsB.electricity ? 8 : 0)}` : "Support docs not needed",
      `Forgery penalty -${flagsB.length * 12}`,
    ].join(", "),
  };
}

interface OcrResponse {
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
  ownership_entries?: { owner?: string; father?: string; share?: string; area_ha?: string }[];
  date?: string;
  stamp_id?: string;
  raw_text?: string | null;
}

function normalize(v: string): string {
  return v.trim().toLowerCase().replace(/\s+/g, " ");
}

function buildForgeryExplanation(flags: string[]): string {
  if (!flags.length) {
    return "No forgery signals detected in rule-based checks for the latest uploaded document.";
  }
  return `Detected ${flags.length} potential integrity issues: ${flags.join(", ")}. Score is reduced per flag.`;
}

function computeBhulekhMatch(extracted: ExtractedParcelData, bhulekh: BhulekhFetchedData): boolean {
  const ownerOk =
    !!normalize(extracted.owner) &&
    !!normalize(bhulekh.owner) &&
    (normalize(extracted.owner) === normalize(bhulekh.owner) ||
      normalize(extracted.owner).includes(normalize(bhulekh.owner)) ||
      normalize(bhulekh.owner).includes(normalize(extracted.owner)));
  const khasraOk =
    !!normalize(extracted.khasra) &&
    !!normalize(bhulekh.khasra) &&
    (normalize(extracted.khasra) === normalize(bhulekh.khasra) ||
      normalize(extracted.khasra).includes(normalize(bhulekh.khasra)) ||
      normalize(bhulekh.khasra).includes(normalize(extracted.khasra)));
  const areaOk =
    !!normalize(extracted.area) &&
    !!normalize(bhulekh.area) &&
    (normalize(extracted.area) === normalize(bhulekh.area) ||
      normalize(extracted.area).includes(normalize(bhulekh.area)) ||
      normalize(bhulekh.area).includes(normalize(extracted.area)));
  // Owner name is the primary signal — khasra/area alone are not sufficient
  // since both parties claim the same plot
  return ownerOk || (khasraOk && areaOk);
}

/** Check if the party's owner name matches the Bhulekh official owner */
function checkOwnerMatchesBhulekh(partyOwner: string, bhulekhOwner: string): boolean {
  const pn = normalize(partyOwner);
  const bn = normalize(bhulekhOwner);
  if (!pn || !bn) return false;
  return pn === bn || pn.includes(bn) || bn.includes(pn);
}

async function runOcrAndForgery(
  file: File,
  onStatus: (msg: string) => void
): Promise<{
  extracted: ExtractedParcelData;
  flags: string[];
  forgeryExplanation: string;
  bhulekhData: BhulekhFetchedData | null;
  bhulekhMatch: boolean | null;
}> {
  onStatus("Running OCR extraction from uploaded document...");
  const fd = new FormData();
  fd.append("file", file);
  const ocrUrl = `${API_BASE}/ocr/document?include_raw_text=true`;
  const ocrRes = await fetch(ocrUrl, { method: "POST", body: fd });
  if (!ocrRes.ok) {
    const msg = await ocrRes.text();
    throw new Error(msg || `OCR failed (${ocrRes.status})`);
  }
  const ocr: OcrResponse = await ocrRes.json();

  const extracted: ExtractedParcelData = {
    owner: (ocr.owner || "").trim(),
    ownerDisplay: (ocr.owner_display || "").trim(),
    father: (ocr.father || "").trim(),
    fatherDisplay: (ocr.father_display || "").trim(),
    khasra: (ocr.khasra || "").trim(),
    area: (ocr.area || "").trim(),
    district: (ocr.district || "").trim(),
    tehsil: (ocr.tehsil || "").trim(),
    village: (ocr.village || "").trim(),
    khata_number: (ocr.khata_number || "").trim(),
    ownership_entries: Array.isArray(ocr.ownership_entries)
      ? ocr.ownership_entries.map((r) => ({
          owner: (r.owner || "").trim(),
          father: (r.father || "").trim(),
          share: (r.share || "").trim(),
          area_ha: (r.area_ha || "").trim(),
        }))
      : undefined,
  };

  let flags: string[] = [];
  onStatus("Running forgery and integrity checks...");
  try {
    const frRes = await fetch(`${API_BASE}/forgery/check`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        document: {
          owner: ocr.owner || "",
          father: ocr.father || "",
          khasra: ocr.khasra || "",
          area: ocr.area || "",
          date: ocr.date || "",
          stamp_id: ocr.stamp_id || "",
          raw_text: ocr.raw_text ?? undefined,
        },
      }),
    });
    if (frRes.ok) {
      const fr = await frRes.json();
      flags = Array.isArray(fr.flags) ? fr.flags : [];
    }
  } catch {
    /* forgery optional */
  }

  onStatus("Primary claimant document processed. Open UP Bhulekh and upload official PDF.");
  return { extracted, flags, forgeryExplanation: buildForgeryExplanation(flags), bhulekhData: null, bhulekhMatch: null };
}

export default function LandDisputeView() {
  const [uploadingA, setUploadingA] = useState(false);
  const [uploadingB, setUploadingB] = useState(false);

  const [docsA, setDocsA] = useState<UploadedDoc[]>([]);
  const [docsB, setDocsB] = useState<UploadedDoc[]>([]);
  const [extractedA, setExtractedA] = useState<ExtractedParcelData | null>(null);
  const [extractedB, setExtractedB] = useState<ExtractedParcelData | null>(null);
  const [flagsA, setFlagsA] = useState<string[]>([]);
  const [flagsB, setFlagsB] = useState<string[]>([]);
  const [errorA, setErrorA] = useState<string | null>(null);
  const [errorB, setErrorB] = useState<string | null>(null);
  const [statusA, setStatusA] = useState<string | null>(null);
  const [statusB, setStatusB] = useState<string | null>(null);
  const [bhulekhA, setBhulekhA] = useState<BhulekhFetchedData | null>(null);
  const [bhulekhB, setBhulekhB] = useState<BhulekhFetchedData | null>(null);
  const [bhulekhMatchA, setBhulekhMatchA] = useState<boolean | null>(null);
  const [bhulekhMatchB, setBhulekhMatchB] = useState<boolean | null>(null);
  const [bhulekhOfficialA, setBhulekhOfficialA] = useState<BhulekhOfficialParsed | null>(null);
  const [bhulekhOfficialB, setBhulekhOfficialB] = useState<BhulekhOfficialParsed | null>(null);
  const [forgeryExplanationA, setForgeryExplanationA] = useState<string>("");
  const [forgeryExplanationB, setForgeryExplanationB] = useState<string>("");
  const [houseTaxDocA, setHouseTaxDocA] = useState<string | null>(null);
  const [houseTaxDocB, setHouseTaxDocB] = useState<string | null>(null);
  const [electricityDocA, setElectricityDocA] = useState<string | null>(null);
  const [electricityDocB, setElectricityDocB] = useState<string | null>(null);
  const [registrationChoice, setRegistrationChoice] = useState<"pending" | "yes" | "no">("pending");
  const [bhulekhFormOpen, setBhulekhFormOpen] = useState(false);
  const [bhulekhVerifying, setBhulekhVerifying] = useState(false);
  const [bhulekhScreenshot, setBhulekhScreenshot] = useState<string | null>(null);
  const [bhulekhForm, setBhulekhForm] = useState({
    district: "",
    tehsil: "",
    village: "",
    fasli_year: "वर्तमान फसली वर्ष",
    search_by: "khasra" as "khasra" | "owner_name",
    khasra: "",
    owner_name: "",
  });
  const [districtOptions, setDistrictOptions] = useState<string[]>([]);
  const [fasliYearOptions, setFasliYearOptions] = useState<string[]>([
    "वर्तमान फसली वर्ष",
    "पिछला फसली वर्ष",
  ]);
  const [tehsilOptions, setTehsilOptions] = useState<string[]>([]);
  const [villageOptions, setVillageOptions] = useState<string[]>([]);

  const loadDistricts = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE}/land-intel/bhulekh/options/districts`);
      if (!resp.ok) return;
      const data = await resp.json();
      setDistrictOptions(Array.isArray(data.districts) ? data.districts : []);
    } catch {
      /* ignore */
    }
  }, []);

  const loadFasliYears = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE}/land-intel/bhulekh/options/fasli-years`);
      if (!resp.ok) return;
      const data = await resp.json();
      const yrs = Array.isArray(data.fasli_years) ? data.fasli_years : [];
      if (yrs.length) setFasliYearOptions(yrs);
    } catch {
      /* ignore */
    }
  }, []);

  const loadTehsils = useCallback(async (district: string, setTehsils: (v: string[]) => void) => {
    if (!district.trim()) return;
    try {
      const resp = await fetch(`${API_BASE}/land-intel/bhulekh/options/tehsils?district=${encodeURIComponent(district)}`);
      if (!resp.ok) return;
      const data = await resp.json();
      setTehsils(Array.isArray(data.tehsils) ? data.tehsils : []);
    } catch {
      /* ignore */
    }
  }, []);

  const loadVillages = useCallback(
    async (district: string, tehsil: string, setVillages: (v: string[]) => void) => {
      if (!district.trim() || !tehsil.trim()) return;
      try {
        const resp = await fetch(
          `${API_BASE}/land-intel/bhulekh/options/villages?district=${encodeURIComponent(district)}&tehsil=${encodeURIComponent(tehsil)}`
        );
        if (!resp.ok) return;
        const data = await resp.json();
        setVillages(Array.isArray(data.villages) ? data.villages : []);
      } catch {
        /* ignore */
      }
    },
    []
  );

  const handleFiles = useCallback((party: "A" | "B", files: FileList | null) => {
    if (!files?.length) return;
    const file = files[files.length - 1];
    const doc: UploadedDoc = {
      id: newId(),
      name: file.name,
      uploadedAt: new Date().toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }),
    };

    const run = async () => {
      if (party === "A") {
        setUploadingA(true);
        setErrorA(null);
        setStatusA("Starting upload...");
        try {
          const { extracted, flags, forgeryExplanation, bhulekhData, bhulekhMatch } = await runOcrAndForgery(file, setStatusA);
          setDocsA((prev) => [...prev, doc]);
          setExtractedA(extracted);
          setFlagsA(flags);
          setForgeryExplanationA(forgeryExplanation);
          setBhulekhA(bhulekhData);
          setBhulekhMatchA(bhulekhMatch);
        } catch (e: unknown) {
          const msg = e instanceof Error ? e.message : "Upload or OCR failed.";
          setErrorA(msg);
        } finally {
          setUploadingA(false);
          setTimeout(() => setStatusA(null), 1200);
        }
      } else {
        setUploadingB(true);
        setErrorB(null);
        setStatusB("Starting upload...");
        try {
          const { extracted, flags, forgeryExplanation, bhulekhData, bhulekhMatch } = await runOcrAndForgery(file, setStatusB);
          setDocsB((prev) => [...prev, doc]);
          setExtractedB(extracted);
          setFlagsB(flags);
          setForgeryExplanationB(forgeryExplanation);
          setBhulekhB(bhulekhData);
          setBhulekhMatchB(bhulekhMatch);
        } catch (e: unknown) {
          const msg = e instanceof Error ? e.message : "Upload or OCR failed.";
          setErrorB(msg);
        } finally {
          setUploadingB(false);
          setTimeout(() => setStatusB(null), 1200);
        }
      }
    };

    void run();
  }, []);

  const comparisonRows = useMemo(() => buildComparison(extractedA, extractedB), [extractedA, extractedB]);
  const requiresBhulekhVerification = registrationChoice === "yes";
  const bhulekhVerifiedReady = !requiresBhulekhVerification || (Boolean(bhulekhA) && Boolean(bhulekhB));
  const officialOwner = useMemo(() => {
    // Prefer the PDF-parsed owner, but fall back to scraper-fetched owner
    const parsed = bhulekhOfficialA || bhulekhOfficialB;
    const pdfOwner = String((parsed?.owner_display || parsed?.owner || "") ?? "").trim();
    if (pdfOwner) return pdfOwner;
    // Fallback: use the scraper owner from Bhulekh website fetch
    return String(bhulekhA?.owner || bhulekhB?.owner || "").trim();
  }, [bhulekhOfficialA, bhulekhOfficialB, bhulekhA, bhulekhB]);
  const result = useMemo(
    () =>
      buildResult(
        extractedA,
        extractedB,
        flagsA,
        flagsB,
        bhulekhA,
        bhulekhB,
        bhulekhMatchA,
        bhulekhMatchB,
        officialOwner,
        { houseTax: !!houseTaxDocA, electricity: !!electricityDocA },
        { houseTax: !!houseTaxDocB, electricity: !!electricityDocB }
      ),
    [
      extractedA,
      extractedB,
      flagsA,
      flagsB,
      bhulekhA,
      bhulekhB,
      bhulekhMatchA,
      bhulekhMatchB,
      officialOwner,
      houseTaxDocA,
      electricityDocA,
      houseTaxDocB,
      electricityDocB,
    ]
  );

  return (
    <div className="land-dispute-view ld:flex ld:min-h-0 ld:flex-1 ld:flex-col ld:gap-5 ld:py-1 md:ld:gap-6">
      <header className="ld:shrink-0 ld:rounded-2xl ld:border ld:border-white/10 ld:bg-slate-900/50 ld:px-6 ld:py-5 ld:backdrop-blur-sm md:ld:px-8 md:ld:py-6">
        <h1 className="ld:text-xl ld:font-semibold ld:tracking-tight ld:text-white md:ld:text-2xl">
          Land dispute dashboard
        </h1>
        <p className="ld:mt-2 ld:text-sm ld:leading-relaxed ld:text-slate-400 md:ld:text-base">
          <span className="ld:font-medium ld:text-teal-200/90">Left: Party A</span>
          <span className="ld:mx-2 ld:text-slate-600">|</span>
          <span className="ld:font-medium ld:text-violet-200/90">Right: Party B</span>
          <span className="ld:mt-2 ld:block ld:font-normal ld:text-slate-400">
            Upload PDFs — fields come from server OCR + rules (not demo data). Poor scans or unusual layouts can still misread text.
          </span>
        </p>
      </header>
      {extractedA && extractedB && registrationChoice === "pending" && (
        <section className="ld:rounded-xl ld:border ld:border-teal-500/30 ld:bg-teal-950/20 ld:px-5 ld:py-4">
          <p className="ld:text-sm ld:text-teal-100">
            Are these lands registered on UP Bhulekh?
          </p>
          <div className="ld:mt-3 ld:flex ld:gap-2">
            <button
              type="button"
              className="ld:rounded-lg ld:bg-teal-600/35 ld:px-3 ld:py-2 ld:text-xs ld:text-teal-100"
              onClick={() => {
                setRegistrationChoice("yes");
                setBhulekhFormOpen(true);
                void loadDistricts();
                void loadFasliYears();
                setBhulekhForm({
                  district: (extractedA.district || "").trim(),
                  tehsil: (extractedA.tehsil || "").trim(),
                  village: (extractedA.village || "").trim(),
                  fasli_year: "वर्तमान फसली वर्ष",
                  search_by: (extractedA.khasra || "").trim() ? "khasra" : "owner_name",
                  khasra: (extractedA.khasra || "").trim(),
                  owner_name: (extractedA.owner || "").trim(),
                });
                void loadTehsils((extractedA.district || "").trim(), setTehsilOptions);
                void loadVillages((extractedA.district || "").trim(), (extractedA.tehsil || "").trim(), setVillageOptions);
              }}
            >
              Yes, registered
            </button>
            <button
              type="button"
              className="ld:rounded-lg ld:bg-amber-600/30 ld:px-3 ld:py-2 ld:text-xs ld:text-amber-100"
              onClick={() => setRegistrationChoice("no")}
            >
              No, not registered
            </button>
          </div>
        </section>
      )}

      {bhulekhFormOpen && registrationChoice === "yes" && extractedA && extractedB && (
        <section className="ld:rounded-xl ld:border ld:border-white/10 ld:bg-slate-900/50 ld:px-5 ld:py-4">
          <div className="ld:flex ld:items-start ld:justify-between ld:gap-4">
            <div>
              <p className="ld:text-sm ld:font-semibold ld:text-white">Enter UP Bhulekh search values</p>
              <p className="ld:mt-1 ld:text-xs ld:text-slate-400">
                This is the shared land parcel for the dispute. Search once on UP Bhulekh, fetch the official PDF, and compare that result against both parties.
              </p>
            </div>
            <button
              type="button"
              className="ld:rounded-lg ld:bg-white/10 ld:px-3 ld:py-2 ld:text-xs ld:text-slate-200 ld:ring-1 ld:ring-white/15"
              onClick={() => setBhulekhFormOpen(false)}
            >
              Close
            </button>
          </div>

          <div className="ld:mt-4 ld:rounded-xl ld:border ld:border-white/10 ld:bg-slate-950/40 ld:p-4">
            <div className="ld:mt-3 ld:grid ld:grid-cols-1 ld:gap-3 md:ld:grid-cols-2">
              <label className="ld:text-xs ld:text-slate-400">
                District (जनपद)
                <select
                  className="ld:mt-1 ld:w-full ld:rounded-lg ld:border ld:border-white/10 ld:bg-slate-950/60 ld:px-3 ld:py-2 ld:text-sm ld:text-white"
                  value={bhulekhForm.district}
                  onChange={(e) => {
                    const v = e.target.value;
                    setBhulekhForm((s) => ({ ...s, district: v, tehsil: "", village: "" }));
                    setTehsilOptions([]);
                    setVillageOptions([]);
                    void loadTehsils(v, setTehsilOptions);
                  }}
                >
                  <option value="">Select district</option>
                  {districtOptions.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>
              </label>
              <label className="ld:text-xs ld:text-slate-400">
                Tehsil (तहसील)
                <select
                  className="ld:mt-1 ld:w-full ld:rounded-lg ld:border ld:border-white/10 ld:bg-slate-950/60 ld:px-3 ld:py-2 ld:text-sm ld:text-white"
                  value={bhulekhForm.tehsil}
                  onChange={(e) => {
                    const v = e.target.value;
                    setBhulekhForm((s) => ({ ...s, tehsil: v, village: "" }));
                    void loadVillages(bhulekhForm.district, v, setVillageOptions);
                  }}
                >
                  <option value="">Select tehsil</option>
                  {tehsilOptions.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </label>
              <label className="ld:text-xs ld:text-slate-400">
                Village (ग्राम)
                <select
                  className="ld:mt-1 ld:w-full ld:rounded-lg ld:border ld:border-white/10 ld:bg-slate-950/60 ld:px-3 ld:py-2 ld:text-sm ld:text-white"
                  value={bhulekhForm.village}
                  onChange={(e) => setBhulekhForm((s) => ({ ...s, village: e.target.value }))}
                >
                  <option value="">Select village</option>
                  {villageOptions.map((v) => (
                    <option key={v} value={v}>
                      {v}
                    </option>
                  ))}
                </select>
              </label>
              <label className="ld:text-xs ld:text-slate-400">
                Fasli year
                <select
                  className="ld:mt-1 ld:w-full ld:rounded-lg ld:border ld:border-white/10 ld:bg-slate-950/60 ld:px-3 ld:py-2 ld:text-sm ld:text-white"
                  value={bhulekhForm.fasli_year}
                  onChange={(e) => setBhulekhForm((s) => ({ ...s, fasli_year: e.target.value }))}
                >
                  {fasliYearOptions.map((y) => (
                    <option key={y} value={y}>
                      {y}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="ld:mt-3 ld:flex ld:flex-wrap ld:items-center ld:gap-2">
              <span className="ld:text-xs ld:text-slate-400">Search by</span>
              <button
                type="button"
                className={`ld:rounded-lg ld:px-3 ld:py-1.5 ld:text-xs ld:ring-1 ${
                  bhulekhForm.search_by === "khasra"
                    ? "ld:bg-teal-600/35 ld:text-teal-100 ld:ring-teal-500/40"
                    : "ld:bg-white/5 ld:text-slate-200 ld:ring-white/10"
                }`}
                onClick={() => setBhulekhForm((s) => ({ ...s, search_by: "khasra" }))}
              >
                Khasra/Gata
              </button>
              <button
                type="button"
                className={`ld:rounded-lg ld:px-3 ld:py-1.5 ld:text-xs ld:ring-1 ${
                  bhulekhForm.search_by === "owner_name"
                    ? "ld:bg-teal-600/35 ld:text-teal-100 ld:ring-teal-500/40"
                    : "ld:bg-white/5 ld:text-slate-200 ld:ring-white/10"
                }`}
                onClick={() => setBhulekhForm((s) => ({ ...s, search_by: "owner_name" }))}
              >
                Khatedar name
              </button>
            </div>

            {bhulekhForm.search_by === "khasra" ? (
              <label className="ld:mt-3 ld:block ld:text-xs ld:text-slate-400">
                Khasra/Gata number
                <input
                  className="ld:mt-1 ld:w-full ld:rounded-lg ld:border ld:border-white/10 ld:bg-slate-950/60 ld:px-3 ld:py-2 ld:text-sm ld:text-white"
                  value={bhulekhForm.khasra}
                  onChange={(e) => setBhulekhForm((s) => ({ ...s, khasra: e.target.value }))}
                />
              </label>
            ) : (
              <label className="ld:mt-3 ld:block ld:text-xs ld:text-slate-400">
                Khatedar name
                <input
                  className="ld:mt-1 ld:w-full ld:rounded-lg ld:border ld:border-white/10 ld:bg-slate-950/60 ld:px-3 ld:py-2 ld:text-sm ld:text-white"
                  value={bhulekhForm.owner_name}
                  onChange={(e) => setBhulekhForm((s) => ({ ...s, owner_name: e.target.value }))}
                />
              </label>
            )}
          </div>

          <div className="ld:mt-4 ld:flex ld:flex-wrap ld:items-center ld:justify-between ld:gap-3">
            <button
              type="button"
              className="ld:rounded-lg ld:bg-teal-600/35 ld:px-4 ld:py-2 ld:text-xs ld:text-teal-100 ld:ring-1 ld:ring-teal-500/40"
              disabled={bhulekhVerifying}
              onClick={async () => {
                const norm = (v?: string) => (v ?? "").trim();
                const location = {
                  district: norm(bhulekhForm.district),
                  tehsil: norm(bhulekhForm.tehsil),
                  village: norm(bhulekhForm.village),
                  fasli_year: norm(bhulekhForm.fasli_year),
                };

                try {
                  const khasraChosen = norm(bhulekhForm.khasra);
                  const ownerChosen = norm(bhulekhForm.owner_name);

                  if (!location.district || !location.tehsil || !location.village) {
                    const msg = "Please select District, Tehsil, and Village before verifying.";
                    setErrorA(msg);
                    setErrorB(msg);
                    return;
                  }

                  if (!khasraChosen && !ownerChosen) {
                    const msg = "Enter either Khasra/Gata or Khatedar name before verifying.";
                    setErrorA(msg);
                    setErrorB(msg);
                    return;
                  }

                  setBhulekhVerifying(true);
                  setBhulekhScreenshot(null);
                  setStatusA("🔍 Opening UP Bhulekh portal — watch the Chrome window...");
                  setStatusB("🔍 Automating search on UP Bhulekh...");
                  setErrorA(null);
                  setErrorB(null);

                  const resp = await fetch(`${API_BASE}/land-intel/bhulekh/verify`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                      district: location.district,
                      tehsil: location.tehsil,
                      village: location.village,
                      fasli_year: location.fasli_year,
                      khasra: bhulekhForm.search_by === "khasra" ? khasraChosen : "",
                      owner_name: bhulekhForm.search_by === "owner_name" ? ownerChosen : "",
                      force_refresh: true,
                    }),
                  });

                  if (!resp.ok) {
                    const msg = await resp.text();
                    throw new Error(msg || "Bhulekh verification failed");
                  }

                  const payload = await resp.json();
                  const r = payload?.result || {};
                  const parsed = payload?.official_pdf_parsed || null;
                  const screenshotData = payload?.screenshot_b64 || "";

                  if (screenshotData) {
                    setBhulekhScreenshot(screenshotData);
                  }

                  const bh: BhulekhFetchedData = {
                    owner: (r.owner || "").trim(),
                    khasra: (r.khasra || "").trim(),
                    area: (r.area || "").trim(),
                    search_mode: (r.search_mode || "").trim(),
                    source: "scraper",
                  };

                  setBhulekhA(bh);
                  setBhulekhB(bh);
                  setBhulekhOfficialA(parsed);
                  setBhulekhOfficialB(parsed);

                  if (parsed && (parsed.owner || parsed.khasra || parsed.area)) {
                    setBhulekhMatchA(
                      computeBhulekhMatch(extractedA as ExtractedParcelData, {
                        owner: String(parsed.owner || ""),
                        khasra: String(parsed.khasra || ""),
                        area: String(parsed.area || ""),
                        search_mode: "official_pdf",
                        source: "scraper",
                      })
                    );
                    setBhulekhMatchB(
                      computeBhulekhMatch(extractedB as ExtractedParcelData, {
                        owner: String(parsed.owner || ""),
                        khasra: String(parsed.khasra || ""),
                        area: String(parsed.area || ""),
                        search_mode: "official_pdf",
                        source: "scraper",
                      })
                    );
                  } else {
                    setBhulekhMatchA(computeBhulekhMatch(extractedA as ExtractedParcelData, bh));
                    setBhulekhMatchB(computeBhulekhMatch(extractedB as ExtractedParcelData, bh));
                  }

                  // Re-run forgery checks with Bhulekh data for both parties
                  const bhulekhOwnerStr = bh.owner || "";
                  const bhulekhKhasraStr = bh.khasra || "";
                  const bhulekhAreaStr = bh.area || "";

                  // Re-check Party A's document against Bhulekh
                  if (extractedA) {
                    try {
                      const frResA = await fetch(`${API_BASE}/forgery/check`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                          document: {
                            owner: extractedA.owner || "",
                            father: extractedA.father || "",
                            khasra: extractedA.khasra || "",
                            area: extractedA.area || "",
                            date: "",
                            stamp_id: "",
                          },
                          bhulekh: {
                            owner_name: bhulekhOwnerStr,
                            khasra: bhulekhKhasraStr,
                            area: bhulekhAreaStr,
                          },
                          other_owners_same_khasra: extractedB ? [extractedB.owner] : [],
                        }),
                      });
                      if (frResA.ok) {
                        const frA = await frResA.json();
                        const newFlagsA = Array.isArray(frA.flags) ? frA.flags : [];
                        if (newFlagsA.length > 0) {
                          setFlagsA(newFlagsA);
                          setForgeryExplanationA(buildForgeryExplanation(newFlagsA));
                        }
                      }
                    } catch { /* forgery re-check optional */ }
                  }

                  // Re-check Party B's document against Bhulekh
                  if (extractedB) {
                    try {
                      const frResB = await fetch(`${API_BASE}/forgery/check`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                          document: {
                            owner: extractedB.owner || "",
                            father: extractedB.father || "",
                            khasra: extractedB.khasra || "",
                            area: extractedB.area || "",
                            date: "",
                            stamp_id: "",
                          },
                          bhulekh: {
                            owner_name: bhulekhOwnerStr,
                            khasra: bhulekhKhasraStr,
                            area: bhulekhAreaStr,
                          },
                          other_owners_same_khasra: extractedA ? [extractedA.owner] : [],
                        }),
                      });
                      if (frResB.ok) {
                        const frB = await frResB.json();
                        const newFlagsB = Array.isArray(frB.flags) ? frB.flags : [];
                        if (newFlagsB.length > 0) {
                          setFlagsB(newFlagsB);
                          setForgeryExplanationB(buildForgeryExplanation(newFlagsB));
                        }
                      }
                    } catch { /* forgery re-check optional */ }
                  }

                  setStatusA("✅ Bhulekh verification complete!");
                  setStatusB("✅ Bhulekh verification complete!");
                  setTimeout(() => {
                    setStatusA(null);
                    setStatusB(null);
                  }, 3000);
                } catch (e) {
                  const msg = e instanceof Error ? e.message : "Bhulekh verification failed.";
                  setErrorA(msg);
                  setErrorB(msg);
                } finally {
                  setBhulekhVerifying(false);
                }
              }}
            >
              {bhulekhVerifying ? (
                <span className="ld:flex ld:items-center ld:gap-2">
                  <svg className="ld:h-4 ld:w-4 ld:animate-spin" viewBox="0 0 24 24" fill="none">
                    <circle className="ld:opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="ld:opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Scraping UP Bhulekh… watch the Chrome window
                </span>
              ) : (
                "Verify from Bhulekh"
              )}
            </button>
          </div>
        </section>
      )}

      {bhulekhScreenshot && (
        <section className="ld:rounded-xl ld:border ld:border-teal-500/30 ld:bg-slate-900/60 ld:p-5 ld:backdrop-blur-sm">
          <div className="ld:flex ld:items-center ld:justify-between ld:mb-3">
            <h3 className="ld:text-sm ld:font-semibold ld:text-teal-100">
              📸 UP Bhulekh — Official Record Screenshot
            </h3>
            <button
              type="button"
              className="ld:text-xs ld:text-slate-400 hover:ld:text-white"
              onClick={() => setBhulekhScreenshot(null)}
            >
              Dismiss
            </button>
          </div>
          <div className="ld:rounded-lg ld:overflow-hidden ld:border ld:border-white/10">
            <img
              src={`data:image/png;base64,${bhulekhScreenshot}`}
              alt="UP Bhulekh search result"
              className="ld:w-full ld:h-auto"
            />
          </div>
          {bhulekhA && (
            <div className="ld:mt-3 ld:grid ld:grid-cols-1 ld:gap-2 md:ld:grid-cols-3">
              <div className="ld:rounded-lg ld:bg-teal-950/40 ld:p-3 ld:border ld:border-teal-500/20">
                <p className="ld:text-[10px] ld:uppercase ld:tracking-wider ld:text-teal-300/70">Official Owner</p>
                <p className="ld:mt-1 ld:text-sm ld:font-medium ld:text-white">{bhulekhA.owner || "—"}</p>
              </div>
              <div className="ld:rounded-lg ld:bg-teal-950/40 ld:p-3 ld:border ld:border-teal-500/20">
                <p className="ld:text-[10px] ld:uppercase ld:tracking-wider ld:text-teal-300/70">Khasra / Gata</p>
                <p className="ld:mt-1 ld:text-sm ld:font-medium ld:text-white">{bhulekhA.khasra || "—"}</p>
              </div>
              <div className="ld:rounded-lg ld:bg-teal-950/40 ld:p-3 ld:border ld:border-teal-500/20">
                <p className="ld:text-[10px] ld:uppercase ld:tracking-wider ld:text-teal-300/70">Area</p>
                <p className="ld:mt-1 ld:text-sm ld:font-medium ld:text-white">{bhulekhA.area || "—"}</p>
              </div>
            </div>
          )}
        </section>
      )}

      <section className="land-dispute-split" aria-label="Party A and Party B document uploads">
        <div className="land-dispute-split__col">
          <PartyPanel
            partyLabel="Party A"
            accent="emerald"
            documents={docsA}
            extracted={extractedA}
            flags={flagsA}
            onSelectFiles={(files) => handleFiles("A", files)}
            uploading={uploadingA}
            uploadError={errorA}
            processingStatus={statusA}
            bhulekhData={bhulekhA}
            bhulekhMatch={bhulekhMatchA}
            bhulekhOfficialParsed={bhulekhOfficialA}
            forgeryExplanation={forgeryExplanationA}
            onSelectHouseTax={(files) => {
              if (!files?.length) return;
              setHouseTaxDocA(files[files.length - 1].name);
            }}
            onSelectElectricity={(files) => {
              if (!files?.length) return;
              setElectricityDocA(files[files.length - 1].name);
            }}
            houseTaxFileName={houseTaxDocA}
            electricityFileName={electricityDocA}
            needsSupportingDocs={registrationChoice === "no" && !bhulekhA}
          />
        </div>
        <div className="land-dispute-split__col">
          <PartyPanel
            partyLabel="Party B"
            accent="violet"
            documents={docsB}
            extracted={extractedB}
            flags={flagsB}
            onSelectFiles={(files) => handleFiles("B", files)}
            uploading={uploadingB}
            uploadError={errorB}
            processingStatus={statusB}
            bhulekhData={bhulekhB}
            bhulekhMatch={bhulekhMatchB}
            bhulekhOfficialParsed={bhulekhOfficialB}
            forgeryExplanation={forgeryExplanationB}
            onSelectHouseTax={(files) => {
              if (!files?.length) return;
              setHouseTaxDocB(files[files.length - 1].name);
            }}
            onSelectElectricity={(files) => {
              if (!files?.length) return;
              setElectricityDocB(files[files.length - 1].name);
            }}
            houseTaxFileName={houseTaxDocB}
            electricityFileName={electricityDocB}
            needsSupportingDocs={registrationChoice === "no" && !bhulekhB}
          />
        </div>
      </section>

      <div className="ld:shrink-0 ld:overflow-y-auto ld:space-y-6 ld:pt-2 md:ld:space-y-8">
        <ComparisonTable rows={comparisonRows} />
        {bhulekhVerifiedReady ? (
          <ResultPanel result={result} />
        ) : (
          <section className="ld:rounded-2xl ld:border ld:border-amber-500/35 ld:bg-amber-950/20 ld:p-6 ld:text-sm ld:text-amber-100">
            Please complete UP Bhulekh verification for both parties before viewing the final score.
          </section>
        )}
      </div>
    </div>
  );
}
