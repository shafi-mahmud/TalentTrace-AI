export interface CvExtractionItem {
  upload_id: string;
  file_type: "pdf" | "docx";
  extraction_status: "text_extracted" | "ocr_required" | "extraction_failed";
  text_char_count: number;
  source_unit_count: number;
  ocr_recommended: boolean;
}

export interface CvExtractionResponse {
  status: "processed";
  job_reference: string;
  batch_id: string;
  processed_count: number;
  files: CvExtractionItem[];
}
