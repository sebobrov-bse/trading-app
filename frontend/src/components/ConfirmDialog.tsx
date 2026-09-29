import { useEffect, useRef } from 'react';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  return (
    <dialog ref={ref} className="confirm-dialog" onCancel={onCancel}>
      <h3>{title}</h3>
      <p>{message}</p>
      <div className="confirm-actions">
        <button type="button" onClick={onCancel} className="btn-secondary">
          {cancelLabel}
        </button>
        <button type="button" onClick={onConfirm} className="btn-danger">
          {confirmLabel}
        </button>
      </div>
    </dialog>
  );
}