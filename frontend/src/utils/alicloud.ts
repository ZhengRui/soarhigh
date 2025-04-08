import { requestTemplate, responseHandlerTemplate } from './requestTemplate';

/**
 * Media file and upload response types
 */
export interface MediaFile {
  filename: string;
  url: string;
  fileKey: string;
  uploadedAt: string;
}

export interface MediaFileList {
  items: MediaFile[];
}

export interface UploadUrlResponse {
  uploadUrl: string;
  fileKey: string;
  fileUrl: string;
}

export interface BatchUploadUrlResponse {
  items: UploadUrlResponse[];
}

const apiEndpoint = process.env.NEXT_PUBLIC_API_ENDPOINT;

/**
 * List all media files for a meeting
 * @param meetingId - The ID of the meeting
 * @returns List of media files in the bucket
 */
export const listMeetingMedia = requestTemplate(
  (meetingId: string) => {
    return {
      url: `${apiEndpoint}/meetings/${meetingId}/media`,
      method: 'GET',
      headers: new Headers({
        Accept: 'application/json',
      }),
    };
  },
  responseHandlerTemplate,
  null,
  true, // Require authentication
  true
);

/**
 * Get batch signed URLs for uploading media to AliCloud OSS
 * @param meetingId - The ID of the meeting
 * @param items - Array of file information for uploading
 * @returns Batch of signed URL info for direct uploads
 */
export const getBatchUploadSignedUrls = requestTemplate(
  (meetingId: string, items: { filename: string; contentType: string }[]) => {
    return {
      url: `${apiEndpoint}/meetings/${meetingId}/media/get-upload-url`,
      method: 'POST',
      headers: new Headers({
        'Content-Type': 'application/json',
        Accept: 'application/json',
      }),
      body: JSON.stringify({
        items,
      }),
    };
  },
  responseHandlerTemplate,
  null,
  true // Require authentication
);

/**
 * Upload multiple files concurrently to their pre-signed URLs
 * @param files - Array of files with their signed URLs and callbacks
 * @returns Promise resolving when all uploads complete
 */
export const uploadFilesToSignedUrls = async (
  files: {
    file: File;
    uploadUrl: string;
    onProgress?: (progress: number) => void;
  }[]
): Promise<boolean[]> => {
  return Promise.all(
    files.map(({ file, uploadUrl, onProgress }) =>
      uploadFileToSignedUrl(file, uploadUrl, onProgress)
    )
  );
};

/**
 * Upload a file directly to a pre-signed URL
 * @param file - The file to upload
 * @param uploadUrl - The pre-signed URL for upload
 * @param onProgress - Optional callback for progress updates
 * @returns Promise resolving to true if upload is successful
 */
export const uploadFileToSignedUrl = async (
  file: File,
  uploadUrl: string,
  onProgress?: (progress: number) => void
): Promise<boolean> => {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();

    // Set up progress tracking
    if (onProgress) {
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          const percentComplete = Math.round(
            (event.loaded / event.total) * 100
          );
          onProgress(percentComplete);
        }
      };
    }

    xhr.open('PUT', uploadUrl);
    xhr.setRequestHeader('Content-Type', file.type);

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(true);
      } else {
        reject(new Error(`Upload failed with status: ${xhr.status}`));
      }
    };

    xhr.onerror = () => reject(new Error('Upload failed'));
    xhr.send(file);
  });
};

/**
 * Delete multiple files from AliCloud OSS
 * @param meetingId - The ID of the meeting
 * @param fileKeys - The keys (paths) of the files to delete
 * @returns Promise resolving to true if deletion is successful
 */
export const deleteFilesFromCloud = requestTemplate(
  (meetingId: string, fileKeys: string[]) => {
    return {
      url: `${apiEndpoint}/meetings/${meetingId}/media`,
      method: 'DELETE',
      headers: new Headers({
        Accept: 'application/json',
        'Content-Type': 'application/json',
      }),
      body: JSON.stringify({ fileKeys }),
    };
  },
  responseHandlerTemplate,
  null,
  true // Require authentication
);
