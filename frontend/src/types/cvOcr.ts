export interface CvOcrItem {
  upload_id: string;
  ocr_status: "ocr_extracted" | "ocr_failed";
  text_char_count: number;
  page_count: number;
  ocr_page_count: number;
}

export interface CvOcrResponse {
  status: "processed";
  job_reference: string;
  batch_id: string;
  attempted_count: number;
  files: CvOcrItem[];
}
