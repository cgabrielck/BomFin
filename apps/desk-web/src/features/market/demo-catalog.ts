/** UI examples only; not a security master, ranking or investment recommendation. */
export const candidates = [
  {
    symbol: 'AAPL',
    id: '11111111-1111-4111-8111-111111111111',
    name: 'Apple',
    tag: '部分報告',
    why: '產品週期與需求變化值得追蹤；先比對公司披露，再核對市場預期。',
    horizon: '波段觀察 · 數週（示例）',
    missing: '缺即時行情與完整事件',
  },
  {
    symbol: 'MSFT',
    id: '22222222-2222-4222-8222-222222222222',
    name: 'Microsoft',
    tag: '初篩',
    why: '雲端業務與資本支出的變化，可能影響未來獲利假設。',
    horizon: '波段觀察 · 數週（示例）',
    missing: '待驗證財務與研究來源',
  },
  {
    symbol: 'NVDA',
    id: '33333333-3333-4333-8333-333333333333',
    name: 'NVIDIA',
    tag: '資料待補',
    why: '產業事件與需求訊號需要交叉核對；有持倉時優先評估變化。',
    horizon: '事件觀察（示例）',
    missing: '事件與價格資料不完整',
  },
] as const;
export type Candidate = (typeof candidates)[number];
export type Scenario = 'sample' | 'offline' | 'missing' | 'empty';
export const findCandidate = (symbol: string) => candidates.find((item) => item.symbol === symbol);
