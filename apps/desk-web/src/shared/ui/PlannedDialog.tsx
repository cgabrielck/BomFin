import { useEffect, useRef } from 'react';

export function PlannedDialog({ name, onClose }: { name: string | null; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (name) ref.current?.showModal();
    else ref.current?.close();
  }, [name]);
  return (
    <dialog ref={ref} onClose={onClose} aria-labelledby="planned-title">
      <h2 id="planned-title">{name} · 尚未接入</h2>
      <p>這個入口只展示未來功能位置，目前不會啟動研究、讀取帳戶或執行交易。</p>
      <form method="dialog">
        <button className="button">明白，返回工作台</button>
      </form>
    </dialog>
  );
}
