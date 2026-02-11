import { useCallback, useEffect, useState } from "react";
import * as docsApi from "../config/documentsApi";
import type { DocumentListItem, DocumentSearchResult } from "../types/entities";
import { FileUploadDialog } from "./FileUploadDialog";
import "../styles/documents.css";

interface DocumentsPanelProps {
  entityType: string;
  entityId: string;
}

export function DocumentsPanel({ entityType, entityId }: DocumentsPanelProps) {
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [searchResults, setSearchResults] = useState<
    DocumentSearchResult[] | null
  >(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showUpload, setShowUpload] = useState(false);

  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const docs = await docsApi.listDocuments(entityType, entityId);
      setDocuments(docs);
    } catch {
      setError("Failed to load documents");
    } finally {
      setLoading(false);
    }
  }, [entityType, entityId]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  const handleSearch = async () => {
    const q = searchQuery.trim();
    if (!q) {
      setSearchResults(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const results = await docsApi.searchDocuments(q, entityType, entityId);
      setSearchResults(results);
    } catch {
      setError("Search failed");
    } finally {
      setLoading(false);
    }
  };

  const handleClearSearch = () => {
    setSearchQuery("");
    setSearchResults(null);
  };

  const handleSearchKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSearch();
  };

  const handleUploadComplete = () => {
    setShowUpload(false);
    fetchDocuments();
  };

  const isSearch = searchResults !== null;
  const itemCount = isSearch ? searchResults.length : documents.length;

  return (
    <div className="docs-panel">
      <div className="docs-panel__header">
        <h3 className="docs-panel__title">
          Documents
          {!isSearch && (
            <span className="docs-panel__count">({documents.length})</span>
          )}
        </h3>
        <button
          className="docs-panel__upload-btn"
          onClick={() => setShowUpload(true)}
        >
          Upload Document
        </button>
      </div>

      <div className="docs-panel__toolbar">
        <input
          type="text"
          className="docs-panel__search-input"
          placeholder="Search documents..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onKeyDown={handleSearchKeyDown}
        />
        <button className="docs-panel__search-btn" onClick={handleSearch}>
          Search
        </button>
        {isSearch && (
          <button className="docs-panel__clear-btn" onClick={handleClearSearch}>
            Clear
          </button>
        )}
      </div>

      {loading && <div className="docs-panel__loading">Loading...</div>}
      {error && <div className="docs-panel__error">{error}</div>}

      {!loading && !error && itemCount === 0 && (
        <div className="docs-panel__empty">
          {isSearch ? "No matching documents found." : "No documents yet."}
        </div>
      )}

      {!loading && !error && itemCount > 0 && (
        <div className="docs-panel__list">
          {isSearch
            ? searchResults.map((item) => (
                <div key={item.file_id} className="docs-panel__item">
                  <div className="docs-panel__item-header">
                    <span className="docs-panel__item-title">
                      {item.title}
                    </span>
                    <span className="docs-panel__item-type">
                      {item.doc_type}
                    </span>
                  </div>
                  <div className="docs-panel__item-meta">
                    {item.filename}
                    {item.date && <> &middot; {item.date}</>}
                  </div>
                  {item.matching_chunks.length > 0 && (
                    <div className="docs-panel__item-excerpts">
                      {item.matching_chunks.slice(0, 2).map((chunk) => (
                        <div
                          key={chunk.chunk_id}
                          className="docs-panel__item-excerpt"
                        >
                          {chunk.text.slice(0, 200)}
                          {chunk.text.length > 200 ? "..." : ""}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))
            : documents.map((item) => (
                <div key={item.file_id} className="docs-panel__item">
                  <div className="docs-panel__item-header">
                    <span className="docs-panel__item-title">
                      {item.title}
                    </span>
                    <span className="docs-panel__item-type">
                      {item.doc_type}
                    </span>
                  </div>
                  <div className="docs-panel__item-meta">
                    {item.filename}
                    {item.date && <> &middot; {item.date}</>}
                  </div>
                </div>
              ))}
        </div>
      )}

      {showUpload && (
        <FileUploadDialog
          entityType={entityType}
          entityId={entityId}
          onUploadComplete={handleUploadComplete}
          onCancel={() => setShowUpload(false)}
        />
      )}
    </div>
  );
}
