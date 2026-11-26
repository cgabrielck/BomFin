import { useQuery } from '@tanstack/react-query';
import { fetchDemoAccount } from '../../shared/transport/market';

export function AccountSummary() {
  const account = useQuery({
    queryKey: ['demo-account'],
    queryFn: ({ signal }) => fetchDemoAccount(signal),
  });
  return (
    <div className="aside-panel">
      <h3>帳戶摘要</h3>
      <span className="pill gray">{account.isPending ? '帳戶摘要載入中' : '帳戶未接入'}</span>
      <p className="tiny">
        沒有讀取券商帳戶；資金、持倉與損益保持未知。這個區塊不會阻塞選股或行情。
      </p>
      {account.isError && (
        <p role="status" className="tiny">
          示範帳戶回應失敗，其他區塊仍可使用。
        </p>
      )}
    </div>
  );
}
