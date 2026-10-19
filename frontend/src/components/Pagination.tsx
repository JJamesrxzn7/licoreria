import { useEffect, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

export const PAGE_SIZE = 25;

export function usePagination<T>(items: readonly T[], resetKey?: string | number) {
  const [page, setPage] = useState(1);
  const pageCount = Math.max(1, Math.ceil(items.length / PAGE_SIZE));

  useEffect(() => {
    setPage(1);
  }, [resetKey]);

  useEffect(() => {
    setPage(currentPage => Math.min(currentPage, pageCount));
  }, [pageCount]);

  const firstItem = items.length === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const lastItem = Math.min(page * PAGE_SIZE, items.length);

  return {
    page,
    pageCount,
    pageItems: items.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    firstItem,
    lastItem,
    setPage,
  };
}

type PaginationControlsProps = {
  page: number;
  pageCount: number;
  firstItem: number;
  lastItem: number;
  totalItems: number;
  onPageChange: (page: number) => void;
};

export function PaginationControls({
  page,
  pageCount,
  firstItem,
  lastItem,
  totalItems,
  onPageChange,
}: PaginationControlsProps) {
  if (pageCount <= 1) return null;

  return (
    <nav className="pagination-controls" aria-label="Paginación de la tabla">
      <span className="pagination-summary">Mostrando {firstItem}–{lastItem} de {totalItems}</span>
      <div className="pagination-buttons">
        <button type="button" className="pagination-button" onClick={() => onPageChange(page - 1)} disabled={page <= 1} aria-label="Página anterior">
          <ChevronLeft size={16} /> Anterior
        </button>
        <span className="pagination-page">Página {page} de {pageCount}</span>
        <button type="button" className="pagination-button" onClick={() => onPageChange(page + 1)} disabled={page >= pageCount} aria-label="Página siguiente">
          Siguiente <ChevronRight size={16} />
        </button>
      </div>
    </nav>
  );
}
