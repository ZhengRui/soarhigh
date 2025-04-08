import React, { useState, useEffect, useRef } from 'react';
import {
  Upload,
  Image as ImageIcon,
  X,
  Loader2,
  Save,
  ArrowUp,
  Check,
} from 'lucide-react';
import Image from 'next/image';
import toast from 'react-hot-toast';
import {
  getBatchUploadSignedUrls,
  uploadFilesToSignedUrls,
  deleteFilesFromCloud,
  listMeetingMedia,
  MediaFile,
  BatchUploadUrlResponse,
  MediaFileList,
} from '@/utils/alicloud';

// We can use the MediaIF interface from our interfaces.ts file

type MediaFormProps = {
  meetingId: string;
};

const MAX_IMAGES = 10;
const MAX_FILENAME_LENGTH = 15;

// Helper function to truncate filename while preserving extension
const truncateFilename = (filename: string): string => {
  const lastDotIndex = filename.lastIndexOf('.');
  if (lastDotIndex === -1)
    return filename.length > MAX_FILENAME_LENGTH
      ? `${filename.substring(0, MAX_FILENAME_LENGTH)}...`
      : filename;

  const name = filename.substring(0, lastDotIndex);
  const extension = filename.substring(lastDotIndex);

  if (name.length <= MAX_FILENAME_LENGTH) return filename;

  return `${name.substring(0, MAX_FILENAME_LENGTH)}...${extension}`;
};

// Type to store pending upload info
type PendingUpload = {
  file: File;
  fileId: string;
};

export function MediaForm({ meetingId }: MediaFormProps) {
  const [existingImages, setExistingImages] = useState<MediaFile[]>([]);
  const [pendingUploads, setPendingUploads] = useState<PendingUpload[]>([]);
  const [previewUrls, setPreviewUrls] = useState<{ [fileId: string]: string }>(
    {}
  );
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [uploadProgress, setUploadProgress] = useState<{
    [key: string]: number;
  }>({});
  const originalImagesRef = useRef<MediaFile[]>([]);

  // Fetch existing images directly from the bucket
  useEffect(() => {
    const fetchImages = async () => {
      setIsLoading(true);
      try {
        const response = await listMeetingMedia(meetingId);
        setExistingImages(response.items);
        originalImagesRef.current = [...response.items];
      } catch (error) {
        console.error('Error fetching images:', error);
        toast.error('Failed to load existing images');
      } finally {
        setIsLoading(false);
      }
    };

    fetchImages();
  }, [meetingId]);

  // Handle file selection - only stage them locally
  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    // Check if adding these files would exceed the MAX_IMAGES limit
    const totalCount = existingImages.length + pendingUploads.length;
    if (totalCount + files.length > MAX_IMAGES) {
      toast.error(
        `Can only upload up to ${MAX_IMAGES} images (currently have ${totalCount})`
      );
      return;
    }

    // Stage each file for upload
    const newPendingUploads = [...pendingUploads];
    const newPreviewUrls = { ...previewUrls };

    // Create file previews
    Array.from(files).forEach((file) => {
      // Validate file type
      const fileExtension = file.name.split('.').pop()?.toLowerCase() || '';
      if (!['jpg', 'jpeg', 'png', 'gif'].includes(fileExtension)) {
        toast.error(`File "${file.name}" is not a supported image format`);
        return;
      }

      // Check for duplicate filenames
      if (
        existingImages.some((img) => img.filename === file.name) ||
        newPendingUploads.some((upload) => upload.file.name === file.name)
      ) {
        toast.error(`A file named "${file.name}" already exists`);
        return;
      }

      // Create a unique ID for this file
      const fileId = `temp-${Date.now()}-${file.name}`;

      // Store both file and its ID
      newPendingUploads.push({
        file,
        fileId,
      });

      // Create a preview URL
      const previewUrl = URL.createObjectURL(file);
      newPreviewUrls[fileId] = previewUrl;
    });

    setPendingUploads(newPendingUploads);
    setPreviewUrls(newPreviewUrls);

    // Reset file input
    event.target.value = '';
  };

  // Handle deletion of existing images
  const handleDeleteImage = (image: MediaFile) => {
    setExistingImages((prev) =>
      prev.filter((img) => img.fileKey !== image.fileKey)
    );
  };

  // Handle removal of pending upload (not yet uploaded)
  const handleRemovePendingUpload = (index: number) => {
    setPendingUploads((prev) => {
      const newUploads = [...prev];
      const fileId = newUploads[index].fileId;

      // Revoke the preview URL to free memory
      URL.revokeObjectURL(previewUrls[fileId] || '');

      // Remove the file from pending uploads
      newUploads.splice(index, 1);
      return newUploads;
    });
  };

  // Handle form submission - process all pending uploads and deletions
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    try {
      // 1. Calculate files to delete based on our local state
      const filesToDelete = originalImagesRef.current.filter(
        (originalFile: MediaFile) =>
          !existingImages.some((img) => img.fileKey === originalFile.fileKey)
      );

      // 2. Delete files in batch if any need to be deleted
      if (filesToDelete.length > 0) {
        const fileKeys = filesToDelete.map((file: MediaFile) => file.fileKey);
        await deleteFilesFromCloud(meetingId, fileKeys);
      }

      // 3. Process uploads in batch
      if (pendingUploads.length > 0) {
        // Create request items for batch URL generation
        const uploadItems = pendingUploads.map(({ file }, i) => {
          setUploadProgress((prev) => ({ ...prev, [`progress-${i}`]: 0 }));
          return {
            filename: file.name,
            contentType: file.type,
          };
        });

        // Get all signed URLs in a single request
        const uploadData: BatchUploadUrlResponse =
          await getBatchUploadSignedUrls(meetingId, uploadItems);

        // Prepare upload tasks with progress callbacks
        const uploadTasks = uploadData.items.map((urlData, i) => ({
          file: pendingUploads[i].file,
          uploadUrl: urlData.uploadUrl,
          onProgress: (progress: number) => {
            setUploadProgress((prev) => ({
              ...prev,
              [`progress-${i}`]: progress,
            }));
          },
        }));

        // Upload all files concurrently
        await uploadFilesToSignedUrls(uploadTasks);
      }

      // 4. Refresh images from the bucket
      const updatedImages: MediaFileList = await listMeetingMedia(meetingId);

      // 5. Clean up and reset state
      Object.values(previewUrls).forEach((url) => URL.revokeObjectURL(url));
      setPendingUploads([]);
      setPreviewUrls({});
      setExistingImages(updatedImages.items);
      originalImagesRef.current = [...updatedImages.items];

      toast.success('Media updated successfully');
    } catch (error) {
      console.error('Save error:', error);
      toast.error('Failed to update media');
    } finally {
      setIsSubmitting(false);
      setUploadProgress({});
    }
  };

  return (
    <form onSubmit={handleSubmit} className='py-6 px-8 pb-14'>
      <div className='border-b pb-4 mb-6'>
        <h2 className='text-2xl font-semibold text-gray-800 flex items-center'>
          <ImageIcon className='w-5 h-5 mr-2 text-indigo-500' />
          Meeting Media
        </h2>
        <p className='text-sm text-gray-600 mt-1'>
          Upload up to {MAX_IMAGES} images for this meeting. Images will be
          displayed on the meeting card.
        </p>
      </div>

      {/* Image Upload Area */}
      <div className='mb-6'>
        <label
          htmlFor='image-upload'
          className='flex flex-col items-center justify-center w-full h-32 border-2 border-dashed rounded-lg cursor-pointer bg-gray-50 hover:bg-gray-100 transition-colors border-gray-300'
        >
          <div className='flex flex-col items-center justify-center pt-5 pb-6'>
            <>
              <Upload className='w-8 h-8 text-gray-400 mb-2' />
              <p className='mb-1 text-sm text-gray-500'>
                <span className='font-semibold'>Click to upload</span> or drag
                and drop
              </p>
              <p className='text-xs text-gray-500'>
                PNG, JPG, or GIF (max {MAX_IMAGES} images)
              </p>
            </>
          </div>
          <input
            id='image-upload'
            type='file'
            className='hidden'
            accept='image/png,image/jpeg,image/jpg,image/gif'
            multiple
            onChange={handleFileSelect}
            disabled={
              isSubmitting ||
              existingImages.length + pendingUploads.length >= MAX_IMAGES
            }
          />
        </label>
      </div>

      {/* Image Gallery */}
      <div className='mb-10'>
        <h4 className='text-sm font-medium text-gray-700 mb-2'>
          Images ({existingImages.length + pendingUploads.length}/{MAX_IMAGES})
        </h4>
        <div className='grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4'>
          {/* Existing images */}
          {existingImages.map((image) => {
            return (
              <div
                key={image.fileKey}
                className='relative group border border-gray-200 rounded-lg overflow-hidden'
              >
                <div
                  className='aspect-w-1 aspect-h-1 w-full'
                  style={{ height: '200px' }}
                >
                  <div className='relative w-full h-full'>
                    <Image
                      src={image.url}
                      alt={image.filename}
                      fill
                      className='object-cover'
                      sizes='(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 25vw'
                    />
                  </div>
                </div>
                {/* Delete button in top-right corner */}
                <div className='absolute top-2 right-2 z-10'>
                  <button
                    type='button'
                    onClick={() => handleDeleteImage(image)}
                    className='p-1.5 bg-red-500 text-white rounded-full hover:bg-red-600 focus:outline-none shadow-md opacity-90 hover:opacity-100 transition-opacity'
                    title='Delete image'
                  >
                    <X className='w-4 h-4' />
                  </button>
                </div>

                <div className='absolute bottom-0 left-0 right-0 bg-black bg-opacity-50 px-2 py-1 flex items-center justify-between'>
                  <p
                    className='text-xs text-white truncate mr-2'
                    title={image.filename}
                  >
                    {truncateFilename(image.filename)}
                  </p>
                  <div className='p-0.5 bg-green-500 text-white rounded-full shadow-sm'>
                    <Check className='w-3 h-3' />
                  </div>
                </div>
              </div>
            );
          })}

          {/* Pending uploads with previews */}
          {pendingUploads.map(({ file, fileId }, index) => {
            const previewUrl = previewUrls[fileId] || '';
            const progress = uploadProgress[`progress-${index}`] || 0;
            const isUploading = isSubmitting && progress >= 0 && progress < 100;

            return (
              <div
                key={fileId}
                className='relative group border border-gray-200 rounded-lg overflow-hidden'
              >
                <div
                  className='aspect-w-1 aspect-h-1 w-full'
                  style={{ height: '200px' }}
                >
                  {previewUrl && (
                    <div className='relative w-full h-full'>
                      <Image
                        src={previewUrl}
                        alt={file.name}
                        fill
                        className={`object-cover ${isUploading ? 'opacity-70' : ''}`}
                        sizes='(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 25vw'
                      />
                    </div>
                  )}

                  {/* Progress circle overlay */}
                  {isUploading && (
                    <div className='absolute inset-0 flex items-center justify-center'>
                      <div className='relative h-16 w-16'>
                        <svg className='h-full w-full' viewBox='0 0 100 100'>
                          {/* Background circle */}
                          <circle
                            className='text-gray-300'
                            strokeWidth='8'
                            stroke='currentColor'
                            fill='transparent'
                            r='45'
                            cx='50'
                            cy='50'
                          />
                          {/* Progress circle */}
                          <circle
                            className='text-blue-600'
                            strokeWidth='8'
                            strokeLinecap='round'
                            stroke='currentColor'
                            fill='transparent'
                            r='45'
                            cx='50'
                            cy='50'
                            strokeDasharray={`${2 * Math.PI * 45}`}
                            strokeDashoffset={`${2 * Math.PI * 45 * (1 - progress / 100)}`}
                          />
                        </svg>
                        <div className='absolute inset-0 flex items-center justify-center text-sm font-medium text-blue-600'>
                          {Math.round(progress)}%
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {/* Delete button in top-right corner */}
                <div className='absolute top-2 right-2 z-10'>
                  <button
                    type='button'
                    onClick={() => handleRemovePendingUpload(index)}
                    className='p-1.5 bg-red-500 text-white rounded-full hover:bg-red-600 focus:outline-none shadow-md opacity-90 hover:opacity-100 transition-opacity'
                    title='Remove from queue'
                  >
                    <X className='w-4 h-4' />
                  </button>
                </div>

                <div className='absolute bottom-0 left-0 right-0 bg-black bg-opacity-50 px-2 py-1 flex items-center justify-between'>
                  <p
                    className='text-xs text-white truncate mr-2'
                    title={file.name}
                  >
                    {truncateFilename(file.name)}
                  </p>
                  <div className='p-0.5 bg-amber-500 text-white rounded-full shadow-sm'>
                    {isUploading ? (
                      <Loader2 className='w-3 h-3 animate-spin' />
                    ) : (
                      <ArrowUp className='w-3 h-3' />
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Loading state */}
        {isLoading && (
          <div className='flex flex-col items-center justify-center py-8 mb-10 bg-gray-50 rounded-lg border border-gray-200'>
            <Loader2 className='w-12 h-12 text-gray-300 mb-2 animate-spin' />
            <p className='text-sm text-gray-500'>Loading images...</p>
          </div>
        )}

        {/* Empty state */}
        {!isLoading &&
          existingImages.length === 0 &&
          pendingUploads.length === 0 && (
            <div className='flex flex-col items-center justify-center py-8 mb-10 bg-gray-50 rounded-lg border border-gray-200'>
              <ImageIcon className='w-12 h-12 text-gray-300 mb-2' />
              <p className='text-sm text-gray-500'>No images uploaded yet</p>
            </div>
          )}
      </div>

      {/* Submit Button */}
      <div className='pt-6 border-t'>
        <button
          type='submit'
          disabled={isSubmitting}
          className='w-full flex items-center justify-center gap-2 py-2 px-4 border border-transparent rounded-md text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed'
        >
          {isSubmitting ? (
            <Loader2 className='w-4 h-4 animate-spin' />
          ) : (
            <Save className='w-4 h-4' />
          )}
          Save Media
        </button>
      </div>
    </form>
  );
}
