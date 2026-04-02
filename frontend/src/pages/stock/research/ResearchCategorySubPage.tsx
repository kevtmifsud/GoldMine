import { useState, useCallback } from "react";
import { ResearchDocumentsGrid } from "../../../components/research/ResearchDocumentsGrid";
import { FileUploadDialog } from "../../../components/FileUploadDialog";
import { useStockEntity } from "../StockEntityPage";

interface ResearchCategorySubPageProps {
  title: string;
  docTypeFilter?: string[];
  excludeDocTypes?: string[];
  uploadAccept?: string;
}

export function ResearchCategorySubPage({
  title,
  docTypeFilter,
  excludeDocTypes,
  uploadAccept,
}: ResearchCategorySubPageProps) {
  const { detail } = useStockEntity();
  const [showUpload, setShowUpload] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const handleUploadComplete = useCallback(() => {
    setShowUpload(false);
    setRefreshKey((k) => k + 1);
  }, []);

  return (
    <>
      <ResearchDocumentsGrid
        key={refreshKey}
        entityType={detail.entity_type}
        entityId={detail.entity_id}
        title={title}
        docTypeFilter={docTypeFilter}
        excludeDocTypes={excludeDocTypes}
        onUploadClick={() => setShowUpload(true)}
      />
      {showUpload && (
        <FileUploadDialog
          entityType={detail.entity_type}
          entityId={detail.entity_id}
          onUploadComplete={handleUploadComplete}
          onCancel={() => setShowUpload(false)}
          accept={uploadAccept}
        />
      )}
    </>
  );
}
