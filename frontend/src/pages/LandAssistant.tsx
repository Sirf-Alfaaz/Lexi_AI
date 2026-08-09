import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { LandDisputeView, LandModeChooser } from "../components/land-dispute";
import LandMap from "./LandMap";
import type { LandMarker, DisputeRiskLevel } from "./LandMap";
import { API_URL as API_BASE } from "../config";

interface LandAnalysis {
  owner_name?: string | null;
  owner_display?: string | null;
  village?: string | null;
  village_display?: string | null;
  district?: string | null;
  khasra_number?: string | null;
  land_area?: string | null;
  acquisition_authority?: string | null;
  compensation_amount?: string | null;
  possible_legal_issues?: string | null;
  dispute_risk_level?: DisputeRiskLevel;
}

interface BhulekhLookup {
  owner?: string;
  khasra?: string;
  area?: string;
  search_mode?: string;
  pdf_url?: string;
}

interface BhulekhPdfFields {
  pdf_url?: string;
  owner?: string;
  khasra?: string;
  area?: string;
  district?: string;
  tehsil?: string;
  village?: string;
  khata_number?: string;
}

interface BhulekhMatchScore {
  status?: string;
  total_points?: number;
  max_points?: number;
  field_points?: {
    owner?: number;
    khasra?: number;
    area?: number;
  };
  field_match?: {
    owner?: boolean;
    khasra?: boolean;
    area?: boolean;
  };
}



export default function LandAssistant() {
  const navigate = useNavigate();

  const [uploading, setUploading] = useState(false);
  const [analysis, setAnalysis] = useState<LandAnalysis | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [bhulekh, setBhulekh] = useState<BhulekhLookup | null>(null);
  const [bhulekhPdf, setBhulekhPdf] = useState<BhulekhPdfFields | null>(null);
  const [bhulekhMatch, setBhulekhMatch] = useState<BhulekhMatchScore | null>(null);
  const [bhulekhError, setBhulekhError] = useState<string | null>(null);

  const [searchDistrict, setSearchDistrict] = useState("");
  const [searchVillage, setSearchVillage] = useState("");
  const [searchKhasra, setSearchKhasra] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const [markers, setMarkers] = useState<LandMarker[]>([]);
  const [landStep, setLandStep] = useState<"menu" | "assistant" | "dispute">("menu");

  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  const handleUpload = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const input = (e.currentTarget.elements.namedItem("landPdf") as HTMLInputElement) || null;
    if (!input || !input.files || input.files.length === 0) {
      setUploadError("Please select a PDF land document.");
      return;
    }
    const file = input.files[0];
    const enteredOwnerInput =
      (e.currentTarget.elements.namedItem("enteredOwnerName") as HTMLInputElement | null)?.value || "";
    const enteredKhasraInput =
      (e.currentTarget.elements.namedItem("enteredKhasraNumber") as HTMLInputElement | null)?.value || "";
    const enteredAreaInput =
      (e.currentTarget.elements.namedItem("enteredLandArea") as HTMLInputElement | null)?.value || "";
    setFileName(file.name);
    const formData = new FormData();
    formData.append("file", file);
    if (enteredOwnerInput.trim()) formData.append("entered_owner_name", enteredOwnerInput.trim());
    if (enteredKhasraInput.trim()) formData.append("entered_khasra_number", enteredKhasraInput.trim());
    if (enteredAreaInput.trim()) formData.append("entered_land_area", enteredAreaInput.trim());

    setUploading(true);
    setUploadError(null);
    setBhulekh(null);
    setBhulekhPdf(null);
    setBhulekhMatch(null);
    setBhulekhError(null);

    try {
      const resp = await fetch(`${API_BASE}/upload-land-document`, {
        method: "POST",
        body: formData,
      });

      if (!resp.ok) {
        const errText = await resp.text();
        throw new Error(errText || "Upload failed");
      }

      const data = await resp.json();
      setAnalysis(data.analysis || null);
      setBhulekh(data.bhulekh || null);
      setBhulekhPdf(data.bhulekh_pdf || null);
      setBhulekhMatch(data.bhulekh_match || null);
      setBhulekhError(data.bhulekh_error || null);

      const coords = data.coordinates;
      if (coords && coords.latitude && coords.longitude) {
        const risk = (data.analysis?.dispute_risk_level || "medium") as DisputeRiskLevel;
        const newMarker: LandMarker = {
          id: data.record_id || "upload-1",
          owner: data.analysis?.owner_display || data.analysis?.owner_name,
          khasra_number: data.analysis?.khasra_number,
          area: data.analysis?.land_area,
          latitude: coords.latitude,
          longitude: coords.longitude,
          dispute_status: risk,
        };
        setMarkers([newMarker]);
      }
    } catch (err: any) {
      setUploadError(err.message || "Failed to upload and analyze document.");
    } finally {
      setUploading(false);
    }
  };

  const handleSearch = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!searchDistrict || !searchVillage || !searchKhasra) {
      setSearchError("Please fill district, village and khasra number.");
      return;
    }
    setSearching(true);
    setSearchError(null);

    try {
      const params = new URLSearchParams({
        district: searchDistrict,
        village: searchVillage,
        khasra_number: searchKhasra,
      });
      const resp = await fetch(`${API_BASE}/land-record?${params.toString()}`);
      if (!resp.ok) {
        const errText = await resp.text();
        throw new Error(errText || "Record not found");
      }
      const rec = await resp.json();

      const marker: LandMarker | null =
        rec.latitude != null && rec.longitude != null
          ? {
              id: rec._id || `${rec.district}-${rec.village}-${rec.khasra_number}`,
              owner: rec.owner_display || rec.owner,
              khasra_number: rec.khasra_number,
              area: rec.area,
              latitude: rec.latitude,
              longitude: rec.longitude,
              dispute_status: (rec.dispute_status || "unknown") as DisputeRiskLevel,
            }
          : null;

      if (marker) {
        setMarkers([marker]);
      } else {
        setMarkers([]);
      }
    } catch (err: any) {
      setSearchError(err.message || "Failed to fetch land record.");
    } finally {
      setSearching(false);
    }
  };

  const currentCenter =
    markers.length > 0 ? ([markers[0].latitude, markers[0].longitude] as [number, number]) : undefined;

  return (
    <div className="land-assistant-immersive" role="main" aria-label="Land Dispute Assistant">
      <button
        type="button"
        className="land-assistant-exit"
        onClick={() => navigate("/")}
        aria-label="Exit Land Dispute Assistant"
        title="Exit"
      >
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden>
          <path d="M18 6L6 18M6 6l12 12" />
        </svg>
      </button>

      <div
        className={
          landStep === "menu"
            ? "land-assistant-immersive-inner land-assistant-immersive-inner--menu"
            : "land-assistant-immersive-inner land-assistant-immersive-inner--workspace"
        }
      >
        {landStep === "menu" ? (
          <LandModeChooser
            onChoose={(mode) => {
              setLandStep(mode);
            }}
          />
        ) : (
          <div className="land-workspace land-workspace--enter">
            <div className="land-workspace-toolbar">
              <button type="button" className="land-back-hub" onClick={() => setLandStep("menu")}>
                ← Mode hub
              </button>
            </div>
            <div className="land-workspace-body">
              {landStep === "dispute" ? (
                <div className="land-dispute-shell land-dispute-shell--expanded">
                  <LandDisputeView />
                </div>
              ) : (
        <div className="content land-content land-content--immersive">
          <h2>🏞️ Land Dispute Assistant (Uttar Pradesh)</h2>
          <p className="land-subtitle">
            Upload land acquisition or registry documents, detect potential disputes using Gemini, and
            visualize the land on an interactive map for Uttar Pradesh.
          </p>

          <div className="land-layout">
            {/* Left column: upload + analysis + search */}
            <div className="card land-left">
              <h3 className="card-title">1. Land Document Upload & AI Dispute Analysis</h3>

              <div className="land-upload-box">
                <form onSubmit={handleUpload} className="land-upload-form">
                  <label className="land-upload-drop">
                    <span className="land-upload-icon">☁</span>
                    <span className="land-upload-text">
                      Drag & drop a land document or <span className="highlight">click to browse</span>
                      <span className="land-upload-subtitle">Supported: PDF (scanned or digital)</span>
                      {fileName && (
                        <span className="land-upload-filename">Selected file: {fileName}</span>
                      )}
                    </span>
                    <input
                      type="file"
                      name="landPdf"
                      accept="application/pdf"
                      className="land-upload-input"
                    />
                  </label>
                  <button type="submit" className="primary-button land-upload-button" disabled={uploading}>
                    {uploading ? "Analyzing..." : "Upload & Analyze"}
                  </button>
                  <div className="land-search-grid">
                    <div className="field">
                      <label>Entered Owner Name (optional)</label>
                      <input
                        type="text"
                        name="enteredOwnerName"
                        placeholder="Compare with Bhulekh owner"
                        className="text-input"
                      />
                    </div>
                    <div className="field">
                      <label>Entered Khasra Number (optional)</label>
                      <input
                        type="text"
                        name="enteredKhasraNumber"
                        placeholder="Compare with Bhulekh khasra"
                        className="text-input"
                      />
                    </div>
                    <div className="field">
                      <label>Entered Land Area (optional)</label>
                      <input
                        type="text"
                        name="enteredLandArea"
                        placeholder="Compare with Bhulekh area"
                        className="text-input"
                      />
                    </div>
                  </div>
                </form>
              </div>

              <div className="land-left-scroll">
                {uploadError && <div className="error-message mt-2">{uploadError}</div>}

                {analysis && (
                  <div className="mt-4 land-analysis">
                    <h4>Extracted Land Details</h4>
                    <dl className="land-details-grid">
                      <div className="field">
                        <dt>Owner Name</dt>
                        <dd>{analysis.owner_display || analysis.owner_name || "—"}</dd>
                      </div>
                      <div className="field">
                        <dt>Village</dt>
                        <dd>{analysis.village_display || analysis.village || "—"}</dd>
                      </div>
                      <div className="field">
                        <dt>District</dt>
                        <dd>{analysis.district || "—"}</dd>
                      </div>
                      <div className="field">
                        <dt>Khasra Number</dt>
                        <dd>{analysis.khasra_number || "—"}</dd>
                      </div>
                      <div className="field">
                        <dt>Land Area</dt>
                        <dd>{analysis.land_area || "—"}</dd>
                      </div>
                      <div className="field">
                        <dt>Acquisition Authority</dt>
                        <dd>{analysis.acquisition_authority || "—"}</dd>
                      </div>
                      <div className="field">
                        <dt>Compensation Amount</dt>
                        <dd>{analysis.compensation_amount || "—"}</dd>
                      </div>
                      <div className="field field-wide">
                        <dt>Possible Legal Issues</dt>
                        <dd>{analysis.possible_legal_issues || "—"}</dd>
                      </div>
                      <div className="field">
                        <dt>Dispute Risk Level</dt>
                        <dd className={`risk-pill risk-${analysis.dispute_risk_level || "medium"}`}>
                          {(analysis.dispute_risk_level || "medium").toUpperCase()}
                        </dd>
                      </div>
                    </dl>
                  </div>
                )}

                {(bhulekh || bhulekhError) && (
                  <div className="mt-4 land-analysis">
                    <h4>UP Bhulekh Website Extraction</h4>
                    {bhulekh && (
                      <dl className="land-details-grid">
                        <div className="field">
                          <dt>Owner Name (Bhulekh)</dt>
                          <dd>{bhulekh.owner || "—"}</dd>
                        </div>
                        <div className="field">
                          <dt>Khasra (Bhulekh)</dt>
                          <dd>{bhulekh.khasra || "—"}</dd>
                        </div>
                        <div className="field">
                          <dt>Area (Bhulekh)</dt>
                          <dd>{bhulekh.area || "—"}</dd>
                        </div>
                        <div className="field">
                          <dt>Search Mode</dt>
                          <dd>{bhulekh.search_mode || "—"}</dd>
                        </div>
                        <div className="field field-wide">
                          <dt>Bhulekh PDF URL</dt>
                          <dd>
                            {bhulekh.pdf_url ? (
                              <a href={bhulekh.pdf_url} target="_blank" rel="noreferrer">
                                Open record PDF
                              </a>
                            ) : (
                              "—"
                            )}
                          </dd>
                        </div>
                      </dl>
                    )}
                    {bhulekhPdf && (
                      <dl className="land-details-grid mt-2">
                        <div className="field">
                          <dt>PDF Owner</dt>
                          <dd>{bhulekhPdf.owner || "—"}</dd>
                        </div>
                        <div className="field">
                          <dt>PDF Khasra</dt>
                          <dd>{bhulekhPdf.khasra || "—"}</dd>
                        </div>
                        <div className="field">
                          <dt>PDF Area</dt>
                          <dd>{bhulekhPdf.area || "—"}</dd>
                        </div>
                      </dl>
                    )}
                    {bhulekhMatch && (
                      <dl className="land-details-grid mt-2">
                        <div className="field">
                          <dt>Match Status</dt>
                          <dd>{bhulekhMatch.status || "—"}</dd>
                        </div>
                        <div className="field">
                          <dt>Total Points</dt>
                          <dd>
                            {(bhulekhMatch.total_points ?? 0)}/{bhulekhMatch.max_points ?? 100}
                          </dd>
                        </div>
                        <div className="field">
                          <dt>Owner Points</dt>
                          <dd>{bhulekhMatch.field_points?.owner ?? 0}</dd>
                        </div>
                        <div className="field">
                          <dt>Khasra Points</dt>
                          <dd>{bhulekhMatch.field_points?.khasra ?? 0}</dd>
                        </div>
                        <div className="field">
                          <dt>Area Points</dt>
                          <dd>{bhulekhMatch.field_points?.area ?? 0}</dd>
                        </div>
                      </dl>
                    )}
                    {bhulekhError && (
                      <div className="error-message mt-2">
                        Bhulekh lookup issue: {bhulekhError}
                      </div>
                    )}
                  </div>
                )}

                <h3 className="card-title mt-6">2. Land Record Search</h3>
                <form onSubmit={handleSearch} className="land-search-grid">
                  <div className="field">
                    <label>District</label>
                    <input
                      type="text"
                      placeholder="e.g. Lucknow"
                      value={searchDistrict}
                      onChange={(e) => setSearchDistrict(e.target.value)}
                      className="text-input"
                    />
                  </div>
                  <div className="field">
                    <label>Village</label>
                    <input
                      type="text"
                      placeholder="Enter village name"
                      value={searchVillage}
                      onChange={(e) => setSearchVillage(e.target.value)}
                      className="text-input"
                    />
                  </div>
                  <div className="field">
                    <label>Khasra Number</label>
                    <input
                      type="text"
                      placeholder="Enter khasra number"
                      value={searchKhasra}
                      onChange={(e) => setSearchKhasra(e.target.value)}
                      className="text-input"
                    />
                  </div>
                  <button
                    type="submit"
                    className="primary-button land-search-button"
                    disabled={searching}
                  >
                    {searching ? "Searching..." : "Search Land Record"}
                  </button>
                </form>

                {searchError && <div className="error-message mt-2">{searchError}</div>}
              </div>
            </div>

            {/* Right column: full-height map */}
            <div className="card land-right">
              <h3 className="card-title">3. Land Location Map & Dispute Zones</h3>
              <div className="land-map-wrapper">
                <LandMap center={currentCenter} markers={markers} />
              </div>
              <div className="mt-2 text-xs text-muted">
                <span className="legend-item">
                  <span className="legend-dot legend-red" /> High risk
                </span>
                <span className="legend-item">
                  <span className="legend-dot legend-yellow" /> Medium risk
                </span>
                <span className="legend-item">
                  <span className="legend-dot legend-green" /> Low risk
                </span>
              </div>
            </div>
          </div>
        </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

