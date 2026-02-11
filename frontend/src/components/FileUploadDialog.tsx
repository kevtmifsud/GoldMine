import { useRef, useState } from "react";
import * as docsApi from "../config/documentsApi";
import "../styles/documents.css";

interface FileUploadDialogProps {
  entityType: string;
  entityId: string;
  onUploadComplete: () => void;
  onCancel: () => void;
}

export function FileUploadDialog({
  entityType,
  entityId,
  onUploadComplete,
  onCancel,
}: FileUploadDialogProps) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [date, setDate] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const files = fileRef.current?.files;
    if (!files || files.length === 0) {
      setError("Please select a file");
      return;
    }

    const file = files[0];
    setUploading(true);
    setError(null);

    try {
      await docsApi.uploadDocument(
        file,
        entityType,
        entityId,
        title || file.name,
        description,
        date
      );
      onUploadComplete();
    } catch {
      setError("Upload failed. Please try again.");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="upload-dialog__overlay" onClick={onCancel}>
      <div className="upload-dialog" onClick={(e) => e.stopPropagation()}>
        <h3 className="upload-dialog__title">Upload Document</h3>
        <form onSubmit={handleSubmit}>
          <div className="upload-dialog__field">
            <label htmlFor="upload-file">File</label>
            <input
              id="upload-file"
              type="file"
              className="upload-dialog__file-input"
              ref={fileRef}
              accept=".txt,.csv,.pdf,.mp3"
            />
          </div>
          <div className="upload-dialog__field">
            <label htmlFor="upload-title">Title</label>
            <input
              id="upload-title"
              type="text"
              className="upload-dialog__input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Document title (optional)"
            />
          </div>
          <div className="upload-dialog__field">
            <label htmlFor="upload-description">Description</label>
            <input
              id="upload-description"
              type="text"
              className="upload-dialog__input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Brief description"
            />
          </div>
          <div className="upload-dialog__field">
            <label htmlFor="upload-date">Date</label>
            <input
              id="upload-date"
              type="date"
              className="upload-dialog__input"
              value={date}
              onChange={(e) => setDate(e.target.value)}
            />
          </div>

          {error && <div className="upload-dialog__error">{error}</div>}

          <div className="upload-dialog__actions">
            <button
              type="button"
              className="upload-dialog__btn upload-dialog__btn--cancel"
              onClick={onCancel}
              disabled={uploading}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="upload-dialog__btn upload-dialog__btn--upload"
              disabled={uploading}
            >
              {uploading ? "Uploading..." : "Upload"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
