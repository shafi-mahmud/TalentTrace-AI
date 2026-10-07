export interface CvUploadItem {
  upload_id: string;
  file_type: "pdf" | "docx";
  size_bytes: number;
}

export interface CvUploadResponse {
  status: "uploaded";
  job_reference: string;
  batch_id: string;
  accepted_count: number;
  files: CvUploadItem[];
}
