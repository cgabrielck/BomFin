import { test, expect } from './fixtures/secure-market';
import type { Page } from '@playwright/test';

/**
 * The research centre in the browser.
 *
 * These tests are about the browser's honesty, not about the API. The
 * research endpoints fail in ways that mean different things to a
 * reader: the model is not configured, the job failed, the audit
 * refused the run, the evidence is missing. A UI that collapses them
 * into one "error" message, or that shows a conclusion without its
 * snapshot and its evidence, is exactly the failure these tests hunt.
 *
 * The fixtures are routed at the network level so each shape can be
 * produced on demand. Nothing here reaches a model provider.
 */

const INSTRUMENT = '11111111-1111-4111-8111-111111111111';
const SNAPSHOT = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const EVIDENCE = '11111111-2222-4333-8444-555555555555';

test.use({ ignoreHTTPSErrors: true, trace: 'off' });

/** The research plane says it is configured and has no reason to refuse. */
function statusBody(configured = true): Record<string, unknown> {
  return { configured, reason: configured ? null : 'LLM_API_KEY 未設定' };
}

/** A job that has not started yet. */
function queuedJob(jobId = 'job-0001'): Record<string, unknown> {
  return {
    job_id: jobId,
    status: 'queued',
    snapshot_id: null,
    role: null,
    instrument_id: INSTRUMENT,
  };
}

/** A finished single-role job with its snapshot, checks and finding. */
function completedJob(jobId = 'job-0001'): Record<string, unknown> {
  return {
    job_id: jobId,
    status: 'completed',
    snapshot_id: SNAPSHOT,
    role: 'discovery',
    instrument_id: INSTRUMENT,
    result: {
      role: 'discovery',
      snapshot_id: SNAPSHOT,
      findings: [
        {
          text: '需求變化仍需獨立核對，現有證據不足以支持方向判斷。',
          evidence_id: EVIDENCE,
        },
      ],
      missing_data: ['公司最新財報尚未進入快照'],
    },
    checks: [
      {
        role: 'discovery',
        execution_result: 'success',
        reasons: [],
        model_version: 'fixture-model',
        prompt_version: 1,
        checked_at: '2026-11-27T00:00:00Z',
        snapshot_id: SNAPSHOT,
      },
    ],
    snapshot: {
      snapshot_id: SNAPSHOT,
      as_of: '2026-11-27T00:00:00Z',
      data_quality: ['bars:complete', 'macro:missing'],
    },
  };
}

/** Put the desk into server mode with a live session. */
async function paired(
  page: Page,
  market: {
    origin: string;
    command: (action: string) => Promise<Record<string, unknown>>;
  },
) {
  await page.goto(market.origin + '/#stock/AAPL');
  await page.getByRole('combobox', { name: '資料模式' }).selectOption('server');
  const { code } = await market.command('pair');
  await page.getByLabel('配對碼', { exact: true }).fill(String(code));
  await page.getByRole('button', { name: '配對登入', exact: true }).click();
  await expect(page.getByRole('button', { name: '登出', exact: true })).toBeVisible();
}

/** Route the three research reads the panel makes on open. */
async function routeReads(
  page: Page,
  overrides: {
    status?: Record<string, unknown>;
    jobs?: Record<string, unknown>;
    statusCode?: number;
    jobsCode?: number;
  } = {},
) {
  await page.route('**/v1/research/status', (route) =>
    route.fulfill({
      status: overrides.statusCode ?? 200,
      json: overrides.status ?? statusBody(),
    }),
  );
  await page.route('**/v1/research/jobs', (route) =>
    route.fulfill({
      status: overrides.jobsCode ?? 200,
      json: overrides.jobs ?? { jobs: [] },
    }),
  );
}

/** Open the research centre tab. */
async function openCentre(page: Page) {
  await page.getByTestId('nav-research').click();
  await expect(page.getByRole('region', { name: '研究中心' })).toBeVisible();
}

test('the research centre opens from the navigation and shows the no-ordering note', async ({
  page,
  market,
}) => {
  await routeReads(page);
  await paired(page, market);
  await openCentre(page);
  // The panel is there, and it says what it will not do.
  await expect(page.getByTestId('research-disclaimer')).toContainText('不會下單');
  await expect(page.getByTestId('research-empty')).toBeVisible();
});

test('a research conclusion shows its snapshot, data quality and evidence', async ({
  page,
  market,
}) => {
  await routeReads(page);
  await page.route('**/v1/research/jobs', (route) => {
    if (route.request().method() === 'POST') {
      return route.fulfill({ status: 202, json: queuedJob() });
    }
    return route.fulfill({ json: { jobs: [] } });
  });
  await page.route('**/v1/research/jobs/job-0001', (route) =>
    route.fulfill({ json: completedJob() }),
  );
  await paired(page, market);
  await openCentre(page);
  await page.getByTestId('research-start').click();
  // The job is watched until it settles.
  await expect(page.getByTestId('research-report')).toBeVisible();
  await expect(page.getByTestId('research-report-status')).toContainText('已完成');
  // The snapshot travels with the conclusion.
  await expect(page.getByTestId('research-snapshot-id')).toHaveText(SNAPSHOT);
  await expect(page.getByTestId('research-as-of')).toHaveText('2026-11-27T00:00:00Z');
  await expect(page.getByTestId('research-data-quality')).toContainText('bars:complete');
  // The finding is shown with the evidence it cites.
  await expect(page.getByTestId('research-role-discovery')).toContainText('需求變化');
  await expect(page.getByTestId('research-evidence-discovery-0')).toContainText(
    EVIDENCE,
  );
  // The audit verdicts are readable, not a JSON dump.
  await expect(page.getByTestId('research-checks')).toContainText('審查驗證');
  await expect(page.getByTestId('research-check-success')).toContainText('discovery');
});

test('the raw report is available but folded away', async ({ page, market }) => {
  await routeReads(page);
  await page.route('**/v1/research/jobs', (route) => {
    if (route.request().method() === 'POST')
      return route.fulfill({ status: 202, json: queuedJob() });
    return route.fulfill({ json: { jobs: [] } });
  });
  await page.route('**/v1/research/jobs/job-0001', (route) =>
    route.fulfill({ json: completedJob() }),
  );
  await paired(page, market);
  await openCentre(page);
  await page.getByTestId('research-start').click();
  const raw = page.getByTestId('research-raw');
  await expect(raw).toBeVisible();
  // Folded by default: the summary is not the raw document.
  await expect(raw).not.toHaveAttribute('open', '');
});

test('an unconfigured research plane says so and refuses to start a job', async ({
  page,
  market,
}) => {
  await routeReads(page, { status: statusBody(false) });
  let posted = 0;
  await page.route('**/v1/research/jobs', (route) => {
    if (route.request().method() === 'POST') posted++;
    return route.fulfill({ json: { jobs: [] } });
  });
  await paired(page, market);
  await openCentre(page);
  // The reason travels with the refusal.
  await expect(page.getByTestId('research-unconfigured')).toContainText(
    'LLM_API_KEY 未設定',
  );
  await expect(page.getByTestId('research-unconfigured')).toContainText('明天可連接');
  // The button is disabled, so no job is ever sent.
  await expect(page.getByTestId('research-start')).toBeDisabled();
  expect(posted).toBe(0);
  // The panel is still readable while the model is not connected.
  await expect(page.getByTestId('research-configured')).toContainText('AI 未配置');
});

test('a failed job states that there is no conclusion', async ({ page, market }) => {
  await routeReads(page);
  await page.route('**/v1/research/jobs', (route) => {
    if (route.request().method() === 'POST')
      return route.fulfill({ status: 202, json: queuedJob() });
    return route.fulfill({ json: { jobs: [] } });
  });
  await page.route('**/v1/research/jobs/job-0001', (route) =>
    route.fulfill({
      json: {
        job_id: 'job-0001',
        status: 'failed',
        snapshot_id: null,
        role: 'discovery',
        reason: 'model provider unavailable',
        result: null,
        checks: [],
      },
    }),
  );
  await paired(page, market);
  await openCentre(page);
  await page.getByTestId('research-start').click();
  await expect(page.getByTestId('research-failed')).toBeVisible();
  await expect(page.getByTestId('research-failed')).toContainText(
    'model provider unavailable',
  );
  // A failed job shows no conclusion.
  await expect(page.getByTestId('research-role-discovery')).toHaveCount(0);
});

test('a refused audit is not shown as a conclusion', async ({ page, market }) => {
  await routeReads(page);
  await page.route('**/v1/research/jobs', (route) => {
    if (route.request().method() === 'POST')
      return route.fulfill({ status: 202, json: queuedJob() });
    return route.fulfill({ json: { jobs: [] } });
  });
  await page.route('**/v1/research/jobs/job-0001', (route) =>
    route.fulfill({
      json: {
        ...completedJob(),
        checks: [
          {
            role: 'discovery',
            execution_result: 'snapshot_reference_broken',
            reasons: [
              'evidence ids not in snapshot: 11111111-2222-4333-8444-555555555555',
            ],
            model_version: 'fixture-model',
            checked_at: '2026-11-27T00:00:00Z',
          },
        ],
      },
    }),
  );
  await paired(page, market);
  await openCentre(page);
  await page.getByTestId('research-start').click();
  await expect(page.getByTestId('research-rejected')).toBeVisible();
  await expect(page.getByTestId('research-rejected')).toContainText(
    'snapshot_reference_broken',
  );
});

test('a job with no snapshot says that there is no citable evidence', async ({
  page,
  market,
}) => {
  await routeReads(page);
  await page.route('**/v1/research/jobs', (route) => {
    if (route.request().method() === 'POST')
      return route.fulfill({ status: 202, json: queuedJob() });
    return route.fulfill({ json: { jobs: [] } });
  });
  await page.route('**/v1/research/jobs/job-0001', (route) =>
    route.fulfill({
      json: {
        job_id: 'job-0001',
        status: 'running',
        snapshot_id: null,
        role: 'discovery',
        result: null,
        checks: [],
      },
    }),
  );
  await paired(page, market);
  await openCentre(page);
  await page.getByTestId('research-start').click();
  await expect(page.getByTestId('research-no-snapshot')).toBeVisible();
  await expect(page.getByTestId('research-no-snapshot')).toContainText(
    '沒有快照就沒有可引用的證據',
  );
});

test('a 503 from the research plane states the reason instead of a report', async ({
  page,
  market,
}) => {
  await routeReads(page, {
    statusCode: 503,
    status: { detail: '研究模型尚未設定' },
  });
  await paired(page, market);
  await openCentre(page);
  await expect(page.getByTestId('research-unavailable')).toContainText(
    '研究模型尚未設定',
  );
  // No conclusion is invented to fill the gap.
  await expect(page.getByTestId('research-report')).toHaveCount(0);
});

test('a refused research request ends the session through the existing expiry path', async ({
  page,
  market,
}) => {
  await routeReads(page, { statusCode: 401 });
  await paired(page, market);
  await openCentre(page);
  // A refusal is a session matter, so it takes the same path a refused
  // market request takes: the desk is signed out and says why.
  await expect(page.getByRole('button', { name: '登出', exact: true })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: '登入行情工作台' })).toBeVisible();
  await expect(page.getByText('登入已失效')).toBeVisible();
});

test('the demo desk says research is not connected and invents no numbers', async ({
  page,
}) => {
  await page.goto('/#stock/AAPL');
  await page.getByTestId('nav-research').click();
  await expect(page.getByTestId('research-demo')).toBeVisible();
  await expect(page.getByTestId('research-demo-note')).toContainText(
    '不會造出任何數字',
  );
  // Nothing pretends to be a conclusion.
  await expect(page.getByTestId('research-report')).toHaveCount(0);
  await expect(page.getByTestId('research-snapshot-id')).toHaveCount(0);
});

test('the stock detail offers a real research entry for that instrument', async ({
  page,
  market,
}) => {
  await routeReads(page);
  await paired(page, market);
  await page.getByTestId('nav-stock').click();
  const entry = page.getByTestId('research-entry');
  await expect(entry).toBeVisible();
  await expect(entry).toContainText('AAPL');
  await entry.locator('summary').click();
  // The same shared panel appears, with the instrument in scope.
  await expect(page.getByTestId('research-instrument')).toContainText('AAPL');
  await expect(page.getByTestId('research-start')).toBeEnabled();
});

test('changing the instrument clears the report that belonged to the old one', async ({
  page,
  market,
}) => {
  await routeReads(page);
  await page.route('**/v1/research/jobs', (route) => {
    if (route.request().method() === 'POST')
      return route.fulfill({ status: 202, json: queuedJob() });
    return route.fulfill({ json: { jobs: [] } });
  });
  await page.route('**/v1/research/jobs/job-0001', (route) =>
    route.fulfill({ json: completedJob() }),
  );
  await paired(page, market);
  await openCentre(page);
  await page.getByTestId('research-start').click();
  await expect(page.getByTestId('research-report')).toBeVisible();
  // A different instrument must not keep showing the old conclusion.
  await page.getByTestId('nav-stock').click();
  await page.locator('.stock-pick', { hasText: 'MSFT' }).click();
  await page.getByTestId('nav-research').click();
  await expect(page.getByTestId('research-report')).toHaveCount(0);
});
