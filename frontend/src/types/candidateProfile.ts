export interface CandidateSourceReference {
  kind: "page" | "block";
  number: number;
  method: "digital" | "ocr";
  block_type: "paragraph" | "table_cell" | null;
}
export interface CandidateAttribute { value: string; source: CandidateSourceReference }
export interface CandidateContact {
  candidate_name: CandidateAttribute | null;
  emails: CandidateAttribute[];
  phones: CandidateAttribute[];
  links: CandidateAttribute[];
  location: CandidateAttribute | null;
}
export interface CandidateEducation {
  institution: CandidateAttribute | null;
  qualification: CandidateAttribute | null;
  field_of_study: CandidateAttribute | null;
  date_or_period: CandidateAttribute | null;
}
export interface CandidateWorkHistory {
  employer: CandidateAttribute | null;
  role_title: CandidateAttribute | null;
  date_or_period: CandidateAttribute | null;
  location: CandidateAttribute | null;
  responsibilities_or_achievements: CandidateAttribute[];
}
export interface CandidateQualifications {
  education: CandidateEducation[];
  work_history: CandidateWorkHistory[];
  skills: CandidateAttribute[];
}
export interface CandidateProfile {
  upload_id: string;
  parsing_status: "parsed" | "source_unavailable" | "parsing_failed";
  contact: CandidateContact | null;
  qualifications: CandidateQualifications | null;
}
export interface CandidateProfilesResponse {
  status: "processed";
  job_reference: string;
  batch_id: string;
  processed_count: number;
  candidates: CandidateProfile[];
}
